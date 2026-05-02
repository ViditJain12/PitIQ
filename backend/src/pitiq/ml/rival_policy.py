"""Rival pit-decision classifier (Phase 4.5.1).

Trains an XGBClassifier to predict whether a driver will pit on the following
lap given current race state + driver style features.

Label construction
------------------
pitted_next_lap = 1 if the next lap (same driver, same race) has a different
Stint number than the current lap.  Pit/out laps are already dropped by the
data cleaning pipeline (IsAccurate=False), so a Stint change reliably indicates
a pit stop occurred between the current and next observed lap.

Class imbalance
---------------
~3.3% of laps have pitted_next_lap=1.  scale_pos_weight = n_stay / n_pit is
passed directly to XGBClassifier.  No SMOTE or resampling.

Calibration
-----------
XGBoost probabilities are calibrated with isotonic regression (CalibratedClassifierCV,
cv='prefit') on the validation set.  In the GridRaceEnv rivals will SAMPLE from
the calibrated probability — not argmax — so calibrated probabilities matter.

Inference (production)
----------------------
predict_pit_probability(driver, circuit, compound, tire_age, ...) → float [0-1]
  - Loads model once (lru_cache).
  - Joins driver style features from driver_styles.parquet.
  - Aligns feature matrix to the column order saved during training.
  - circuit must be the full EventName string (e.g. "Bahrain Grand Prix").

CLI:
    python -m pitiq.ml.rival_policy --train
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from functools import lru_cache
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
import xgboost as xgb

try:
    import joblib
except ImportError:
    import pickle as joblib  # type: ignore[no-redef]

from pitiq.ml.compound_constants import COMPOUND_CLIFF_LAP
from pitiq.features.split import TEST_RACES, VAL_RACES

logger = logging.getLogger(__name__)

_REPO_ROOT    = Path(__file__).parents[4]
_FEATURES_DIR = _REPO_ROOT / "data" / "features"
_MODELS_DIR   = _REPO_ROOT / "models"
_FIGURES_DIR  = _MODELS_DIR / "figures"

_MODEL_PATH = _MODELS_DIR / "rival_pit_policy.pkl"
_META_PATH  = _MODELS_DIR / "rival_pit_policy_meta.json"


class _CalibratedPitModel:
    """XGBClassifier + isotonic regression calibrator.

    Wraps the fitted XGBoost model and an IsotonicRegression calibrator trained
    on the val set so that predict_proba() returns calibrated probabilities.
    sklearn 1.8 dropped cv='prefit' from CalibratedClassifierCV; this is the
    equivalent without the API dependency.
    """

    def __init__(
        self,
        base_model: xgb.XGBClassifier,
        iso_reg: IsotonicRegression,
    ) -> None:
        self.base_model = base_model
        self.iso_reg    = iso_reg

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        raw = self.base_model.predict_proba(X)[:, 1]
        cal = self.iso_reg.predict(raw)
        # Clip to [0.001, 0.95] so rivals are never fully deterministic.
        # Prevents hard-coding of "ZHO always pits on lap 25" into PPO policy
        # and preserves episode diversity during Phase 5 RL training.
        cal = np.clip(cal, 0.001, 0.95)
        return np.column_stack([1 - cal, cal])

# ── Feature definitions ───────────────────────────────────────────────────────

NUMERIC_FEATURES = [
    "tire_age",
    "laps_past_cliff",
    "fuel_load_estimate",
    "laps_remaining",
    "position",
    "stint_number",
    "track_temp",
]

BINARY_FEATURES = ["is_wet"]

CATEGORICAL_FEATURES = ["EventName", "Compound"]

STYLE_FEATURES = [
    "pace_trend_soft",
    "pace_trend_medium",
    "pace_trend_hard",
    "cornering_aggression",
    "throttle_smoothness",
    "wet_skill_delta",
    "tire_saving_coef",
    "overall_pace_rank",
    "sector_relative_s1",
    "sector_relative_s2",
    "sector_relative_s3",
]

TARGET = "pitted_next_lap"

# Threshold for secondary precision/recall report
DECISION_THRESHOLD = 0.3


# ── Data preparation ──────────────────────────────────────────────────────────

def _build_training_data() -> pd.DataFrame:
    """Load lap features, build pit label, compute laps_past_cliff, join styles."""
    laps = pd.read_parquet(_FEATURES_DIR / "lap_features.parquet")
    styles = pd.read_parquet(_FEATURES_DIR / "driver_styles.parquet")

    laps = laps.sort_values(
        ["Driver", "Year", "RoundNumber", "LapNumber"]
    ).reset_index(drop=True)

    # pitted_next_lap: 1 when the next available lap (same driver, same race)
    # has a different Stint number.  Pit/out laps are already absent from the
    # dataset (IsAccurate=False filter in Phase 1.3), so a Stint change
    # reliably marks the lap just before a pit stop.
    laps["_next_stint"] = laps.groupby(
        ["Driver", "Year", "RoundNumber"]
    )["Stint"].shift(-1)
    laps[TARGET] = (
        (laps["_next_stint"] != laps["Stint"]) & laps["_next_stint"].notna()
    ).astype(int)

    # Drop last lap of each driver-race (no following lap → no valid label)
    laps = laps[laps["_next_stint"].notna()].copy()
    laps.drop(columns=["_next_stint"], inplace=True)

    # laps_past_cliff: how many laps the current tyre is past its performance cliff
    cliff_map = {k: float(v) for k, v in COMPOUND_CLIFF_LAP.items()}
    laps["cliff_lap"] = laps["Compound"].map(cliff_map).fillna(30.0)
    laps["laps_past_cliff"] = (laps["tire_age"] - laps["cliff_lap"]).clip(lower=0.0)
    laps.drop(columns=["cliff_lap"], inplace=True)

    # Join driver style features (Driver is the index of styles)
    laps = laps.join(styles, on="Driver", how="left")

    logger.info(
        "Dataset: %d rows | pit=1: %d (%.2f%%)",
        len(laps),
        laps[TARGET].sum(),
        laps[TARGET].mean() * 100,
    )
    return laps


def _make_feature_matrix(
    df: pd.DataFrame,
    expected_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Build the feature matrix from a labeled dataframe.

    If expected_columns is provided (val/test at training time, or inference),
    the output is aligned to that column order: missing dummies are zero-filled,
    extra columns are dropped.
    """
    X = df[NUMERIC_FEATURES + BINARY_FEATURES + STYLE_FEATURES].copy()
    X[BINARY_FEATURES] = X[BINARY_FEATURES].astype(float)

    for col in CATEGORICAL_FEATURES:
        dummies = pd.get_dummies(df[col], prefix=col, dtype=float)
        X = pd.concat([X, dummies], axis=1)

    if expected_columns is not None:
        for c in expected_columns:
            if c not in X.columns:
                X[c] = 0.0
        X = X[expected_columns]

    return X


def _split_dataset(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply the same race-based split as Phase 3 (TEST_RACES / VAL_RACES)."""
    race_key = list(zip(df["Year"], df["RoundNumber"]))
    test_mask  = pd.Series([k in TEST_RACES  for k in race_key], index=df.index)
    val_mask   = pd.Series([k in VAL_RACES   for k in race_key], index=df.index)
    train_mask = ~test_mask & ~val_mask

    return df[train_mask].copy(), df[val_mask].copy(), df[test_mask].copy()


# ── Training ──────────────────────────────────────────────────────────────────

def train() -> dict:
    """Train the rival pit-decision classifier and save artifacts.

    Returns a metrics dict with AUC-ROC and precision/recall on the test set.
    """
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)
    _FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Data ───────────────────────────────────────────────────────────────
    data = _build_training_data()
    train_df, val_df, test_df = _split_dataset(data)

    logger.info(
        "Split: train=%d  val=%d  test=%d",
        len(train_df), len(val_df), len(test_df),
    )

    y_train = train_df[TARGET].values
    y_val   = val_df[TARGET].values
    y_test  = test_df[TARGET].values

    # ── 2. Feature matrices ───────────────────────────────────────────────────
    X_train = _make_feature_matrix(train_df)
    feature_columns = list(X_train.columns)

    X_val  = _make_feature_matrix(val_df,  feature_columns)
    X_test = _make_feature_matrix(test_df, feature_columns)

    logger.info("Feature count: %d", len(feature_columns))

    # ── 3. Class imbalance ────────────────────────────────────────────────────
    n_stay = int((y_train == 0).sum())
    n_pit  = int((y_train == 1).sum())
    scale_pos_weight = n_stay / n_pit
    logger.info(
        "Train pit rate: %d stay / %d pit  →  scale_pos_weight=%.1f",
        n_stay, n_pit, scale_pos_weight,
    )

    # ── 4. XGBClassifier with early stopping ──────────────────────────────────
    base_model = xgb.XGBClassifier(
        n_estimators=1000,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        scale_pos_weight=scale_pos_weight,
        eval_metric="auc",
        early_stopping_rounds=50,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )

    base_model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=100,
    )

    best_n = base_model.best_iteration
    logger.info("Early stopping: best_iteration=%d", best_n)

    # ── 5. Reliability diagram before calibration ─────────────────────────────
    val_probs_raw = base_model.predict_proba(X_val)[:, 1]
    fraction_pos, mean_pred = calibration_curve(
        y_val, val_probs_raw, n_bins=10, strategy="uniform"
    )

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    ax.plot(mean_pred, fraction_pos, "b-o", label="Before calibration")

    # ── 6. Calibration (isotonic regression on val set) ───────────────────────
    iso_reg = IsotonicRegression(out_of_bounds="clip")
    iso_reg.fit(val_probs_raw, y_val)
    calibrated_model = _CalibratedPitModel(base_model, iso_reg)

    val_probs_cal = calibrated_model.predict_proba(X_val)[:, 1]
    frac_pos_cal, mean_pred_cal = calibration_curve(
        y_val, val_probs_cal, n_bins=10, strategy="uniform"
    )
    ax.plot(mean_pred_cal, frac_pos_cal, "r-o", label="After calibration")
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of positives")
    ax.set_title("Pit decision: reliability diagram (val set)")
    ax.legend()
    cal_path = _FIGURES_DIR / "rival_pit_calibration.png"
    fig.savefig(cal_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved reliability diagram → %s", cal_path)

    # ── 7. Test-set metrics ───────────────────────────────────────────────────
    test_probs = calibrated_model.predict_proba(X_test)[:, 1]
    auc_roc    = roc_auc_score(y_test, test_probs)
    avg_prec   = average_precision_score(y_test, test_probs)

    test_preds_030 = (test_probs >= DECISION_THRESHOLD).astype(int)
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_test, test_preds_030, average="binary", zero_division=0
    )

    logger.info("Test AUC-ROC : %.4f", auc_roc)
    logger.info("Test Avg-Prec: %.4f", avg_prec)
    logger.info(
        "Test @threshold=%.2f  precision=%.3f  recall=%.3f  f1=%.3f",
        DECISION_THRESHOLD, prec, rec, f1,
    )

    # ── 8. Feature importance ─────────────────────────────────────────────────
    importances = pd.Series(
        base_model.feature_importances_, index=feature_columns
    ).sort_values(ascending=False)

    top_n = 30
    fig, ax = plt.subplots(figsize=(8, 8))
    importances.head(top_n).sort_values().plot.barh(ax=ax)
    ax.set_title(f"Rival pit policy: top {top_n} feature importances (gain)")
    ax.set_xlabel("Importance score")
    fi_path = _FIGURES_DIR / "rival_pit_feature_importance.png"
    fig.savefig(fi_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved feature importance → %s", fi_path)

    # Style feature ranks
    style_ranks = {
        f: int(np.where(importances.index == f)[0][0]) + 1
        for f in STYLE_FEATURES
        if f in importances.index
    }
    logger.info("Style feature ranks in top-%d importance list:", len(importances))
    for feat, rank in sorted(style_ranks.items(), key=lambda x: x[1]):
        logger.info("  rank %3d  %s  (importance=%.5f)", rank, feat, importances[feat])

    # ── 9. Domain sanity checks ───────────────────────────────────────────────
    sanity_results = _run_sanity_checks(calibrated_model, feature_columns, data)

    # ── 10. Save ──────────────────────────────────────────────────────────────
    joblib.dump((calibrated_model, feature_columns), _MODEL_PATH)
    logger.info("Saved model → %s", _MODEL_PATH)

    meta = {
        "auc_roc_test":             round(auc_roc, 4),
        "avg_precision_test":       round(avg_prec, 4),
        "precision_at_030":         round(float(prec), 4),
        "recall_at_030":            round(float(rec), 4),
        "f1_at_030":                round(float(f1), 4),
        "n_train":                  len(train_df),
        "n_val":                    len(val_df),
        "n_test":                   len(test_df),
        "n_pit_train":              n_pit,
        "n_stay_train":             n_stay,
        "scale_pos_weight":         round(scale_pos_weight, 2),
        "best_iteration":           best_n,
        "decision_threshold":       DECISION_THRESHOLD,
        "n_features":               len(feature_columns),
        "style_feature_ranks":      style_ranks,
        "sanity_checks":            sanity_results,
    }
    _META_PATH.write_text(json.dumps(meta, indent=2))
    logger.info("Saved metadata → %s", _META_PATH)

    return meta


# ── Domain sanity checks ──────────────────────────────────────────────────────

def _run_sanity_checks(
    model: _CalibratedPitModel,
    feature_columns: list[str],
    full_data: pd.DataFrame,
) -> dict:
    """Run 4 directional sanity checks; return results dict."""

    def _prob(
        driver: str,
        circuit: str,
        compound: str,
        tire_age: int,
        laps_remaining: int,
        position: int,
        stint_number: int,
        fuel_estimate: float,
        is_wet: bool,
        track_temp: float,
        styles: pd.DataFrame,
    ) -> float:
        cliff_lap = float(COMPOUND_CLIFF_LAP.get(compound, 30))
        row: dict = {
            "tire_age":          float(tire_age),
            "laps_past_cliff":   max(0.0, float(tire_age) - cliff_lap),
            "fuel_load_estimate": float(fuel_estimate),
            "laps_remaining":    float(laps_remaining),
            "position":          float(position),
            "stint_number":      float(stint_number),
            "track_temp":        float(track_temp),
            "is_wet":            float(is_wet),
            "EventName":         circuit,
            "Compound":          compound,
        }
        for f in STYLE_FEATURES:
            row[f] = styles.loc[driver, f] if driver in styles.index else np.nan

        df_row = pd.DataFrame([row])
        X = _make_feature_matrix(df_row, feature_columns)
        return float(model.predict_proba(X)[0, 1])

    styles = pd.read_parquet(_FEATURES_DIR / "driver_styles.parquet")

    results: dict = {}

    # Base scenario shared across checks
    base = dict(
        circuit="Bahrain Grand Prix",
        compound="MEDIUM",
        tire_age=25,
        laps_remaining=30,
        position=5,
        stint_number=1,
        fuel_estimate=65.0,
        is_wet=False,
        track_temp=38.0,
    )

    # Check 1: VER (tire saver) vs ZHO (higher tire_saving_coef → pushes harder)
    prob_ver = _prob("VER", **base, styles=styles)
    prob_zho = _prob("ZHO", **base, styles=styles)
    check1_pass = prob_ver < prob_zho
    results["check1_ver_vs_zho"] = {
        "description": "VER pit prob < ZHO at tire_age=25 Bahrain (VER is tire saver)",
        "prob_VER": round(prob_ver, 4),
        "prob_ZHO": round(prob_zho, 4),
        "passed": check1_pass,
    }
    logger.info(
        "Sanity 1 (VER vs ZHO)  VER=%.4f  ZHO=%.4f  %s",
        prob_ver, prob_zho, "PASS ✓" if check1_pass else "FAIL ✗",
    )

    # Check 2: high tire_age vs low tire_age, same driver/compound
    prob_fresh = _prob("VER", **{**base, "tire_age": 5},  styles=styles)
    prob_old   = _prob("VER", **{**base, "tire_age": 35}, styles=styles)
    check2_pass = prob_old > prob_fresh
    results["check2_tire_age"] = {
        "description": "tire_age=35 has higher pit prob than tire_age=5 (same driver/compound)",
        "prob_age5":  round(prob_fresh, 4),
        "prob_age35": round(prob_old, 4),
        "passed": check2_pass,
    }
    logger.info(
        "Sanity 2 (tire age)  age5=%.4f  age35=%.4f  %s",
        prob_fresh, prob_old, "PASS ✓" if check2_pass else "FAIL ✗",
    )

    # Check 3: laps_remaining=5 vs 30, same driver
    prob_late  = _prob("VER", **{**base, "laps_remaining": 5},  styles=styles)
    prob_early = _prob("VER", **{**base, "laps_remaining": 30}, styles=styles)
    check3_pass = prob_late < prob_early
    results["check3_laps_remaining"] = {
        "description": "laps_remaining=5 has lower pit prob than laps_remaining=30 (too late to pit)",
        "prob_5lap":  round(prob_late, 4),
        "prob_30lap": round(prob_early, 4),
        "passed": check3_pass,
    }
    logger.info(
        "Sanity 3 (laps remaining)  5lap=%.4f  30lap=%.4f  %s",
        prob_late, prob_early, "PASS ✓" if check3_pass else "FAIL ✗",
    )

    # Check 4: Monaco vs Bahrain, same race state
    prob_bahrain = _prob("VER", **base,                                      styles=styles)
    prob_monaco  = _prob("VER", **{**base, "circuit": "Monaco Grand Prix"},  styles=styles)
    check4_pass = prob_monaco < prob_bahrain
    results["check4_monaco_vs_bahrain"] = {
        "description": "Monaco has lower pit prob than Bahrain (teams avoid pitting at Monaco)",
        "prob_Bahrain": round(prob_bahrain, 4),
        "prob_Monaco":  round(prob_monaco, 4),
        "passed": check4_pass,
    }
    logger.info(
        "Sanity 4 (Monaco vs Bahrain)  Bahrain=%.4f  Monaco=%.4f  %s",
        prob_bahrain, prob_monaco, "PASS ✓" if check4_pass else "FAIL ✗",
    )

    n_pass = sum(v["passed"] for v in results.values())
    logger.info("Sanity checks: %d/4 passed", n_pass)

    return results


# ── Inference ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_rival_policy() -> tuple[_CalibratedPitModel, list[str], pd.DataFrame]:
    """Load model, feature columns, and driver styles (cached)."""
    if not _MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found at {_MODEL_PATH} — run: python -m pitiq.ml.rival_policy --train"
        )
    model, feature_columns = joblib.load(_MODEL_PATH)
    styles = pd.read_parquet(_FEATURES_DIR / "driver_styles.parquet")
    return model, feature_columns, styles


def predict_pit_probability(
    *,
    driver: str,
    circuit: str,
    compound: str,
    tire_age: int,
    laps_remaining: int,
    position: int,
    stint_number: int,
    fuel_estimate: float,
    is_wet: bool,
    track_temp: float,
    year: int = 2025,
) -> float:
    """Return the probability (0-1) that this driver will pit on the next lap.

    Parameters
    ----------
    driver       : Three-letter abbreviation matching driver_styles.parquet index
                   (e.g. "VER", "HAM").  Unknown drivers get NaN style features
                   (XGBoost handles natively).
    circuit      : Full EventName string matching training data
                   (e.g. "Bahrain Grand Prix", "Monaco Grand Prix").
                   Unknown circuits get zeroed one-hot columns.
    compound     : "SOFT", "MEDIUM", "HARD", "INTERMEDIATE", or "WET".
    year         : Informational only (not a model feature at this stage).
    """
    model, feature_columns, styles = _load_rival_policy()

    cliff_lap = float(COMPOUND_CLIFF_LAP.get(compound, 30))
    row: dict = {
        "tire_age":           float(tire_age),
        "laps_past_cliff":    max(0.0, float(tire_age) - cliff_lap),
        "fuel_load_estimate": float(fuel_estimate),
        "laps_remaining":     float(laps_remaining),
        "position":           float(position),
        "stint_number":       float(stint_number),
        "track_temp":         float(track_temp),
        "is_wet":             float(is_wet),
        "EventName":          circuit,
        "Compound":           compound,
    }

    for f in STYLE_FEATURES:
        row[f] = styles.loc[driver, f] if driver in styles.index else np.nan

    df_row = pd.DataFrame([row])
    X = _make_feature_matrix(df_row, feature_columns)

    return float(model.predict_proba(X)[0, 1])


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Train the rival pit-decision classifier (Phase 4.5.1)."
    )
    p.add_argument("--train", action="store_true", help="Train and save the model")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    if not args.train:
        _build_parser().print_help()
        sys.exit(0)

    metrics = train()

    print("\n" + "=" * 60)
    print("RIVAL PIT POLICY — Phase 4.5.1 Results")
    print("=" * 60)
    print(f"  AUC-ROC (test)       : {metrics['auc_roc_test']:.4f}  (target > 0.75)")
    print(f"  Avg Precision (test) : {metrics['avg_precision_test']:.4f}")
    print(
        f"  @ threshold=0.30     : precision={metrics['precision_at_030']:.3f}"
        f"  recall={metrics['recall_at_030']:.3f}"
        f"  f1={metrics['f1_at_030']:.3f}"
    )
    print(f"  scale_pos_weight     : {metrics['scale_pos_weight']:.1f}")
    print(f"  best_iteration       : {metrics['best_iteration']}")
    print(f"  features             : {metrics['n_features']}")
    print()
    print("Sanity checks:")
    for key, res in metrics["sanity_checks"].items():
        status = "PASS ✓" if res["passed"] else "FAIL ✗"
        print(f"  {status}  {res['description']}")
        for k, v in res.items():
            if k.startswith("prob_"):
                print(f"         {k}: {v:.4f}")
    print()
    print(f"  Model  → {_MODEL_PATH}")
    print(f"  Meta   → {_META_PATH}")
    print(f"  Figs   → {_FIGURES_DIR}/rival_pit_*.png")


if __name__ == "__main__":
    main()
