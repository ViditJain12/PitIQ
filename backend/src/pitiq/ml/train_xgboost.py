"""XGBoost lap time prediction — baseline model (no driver style features).

Baseline establishes MAE/RMSE reference so Phase 3.2 can quantify the
improvement from adding driver style vectors.

Features
--------
Numeric  : tire_age, stint_number, fuel_load_estimate, laps_remaining,
           position, length_km, pit_loss_s, air_temp, track_temp, humidity
Categorical (one-hot): Compound, circuit_type
Boolean  : is_street_circuit, is_wet
Target   : LapTimeCorrected

CLI
---
    python -m pitiq.ml.train_xgboost --baseline
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
import xgboost as xgb

try:
    import joblib
except ImportError:  # joblib ships with sklearn; guard anyway
    import pickle as joblib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

_REPO_ROOT    = Path(__file__).parents[4]
_FEATURES_DIR = _REPO_ROOT / "data" / "features"
_MODELS_DIR   = _REPO_ROOT / "models"
_FIGURES_DIR  = _MODELS_DIR / "figures"

# ── Feature lists ──────────────────────────────────────────────────────────────
NUMERIC_FEATURES = [
    "tire_age",
    "stint_number",
    "fuel_load_estimate",
    "laps_remaining",
    "position",
    "length_km",
    "pit_loss_s",
    "air_temp",
    "track_temp",
    "humidity",
    # Year captures inter-season car development (F1 cars improve ~2-4s/yr at some
    # circuits). RoundNumber captures within-season development and surface evolution.
    # Both are always known at inference time — not leakage.
    "Year",
    "RoundNumber",
]
# EventName is included as a categorical identifier — physical proxies (length_km,
# pit_loss_s, circuit_type) do not uniquely distinguish circuits (e.g. Hungary,
# Mexico, São Paulo all share ~4.3km / 22s but span a 7s lap-time range).
# Trade-off: physical features would generalise to unseen circuits; EventName
# one-hot fails silently for new venues. For MVP our 29-circuit set is fixed and
# fully covered in train, so EventName one-hot is safe.
CATEGORICAL_FEATURES = ["Compound", "circuit_type", "EventName"]
BOOLEAN_FEATURES     = ["is_street_circuit", "is_wet"]
TARGET               = "LapTimeCorrected"

# ── XGBoost hyperparameters ────────────────────────────────────────────────────
XGB_PARAMS = {
    "n_estimators":         500,
    "max_depth":            6,
    "learning_rate":        0.05,
    "subsample":            0.8,
    "colsample_bytree":     0.8,
    "objective":            "reg:squarederror",
    "random_state":         42,
    "n_jobs":               -1,
    "early_stopping_rounds": 20,
}


# ── Data helpers ───────────────────────────────────────────────────────────────

def _load_split(name: str) -> pd.DataFrame:
    path = _FEATURES_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run build pipeline first")
    df = pd.read_parquet(path)
    # Drop rows with invalid Compound or missing target / tire_age
    df = df[~df["Compound"].isin(["None", "nan"])].copy()
    df = df[df[TARGET].notna() & df["tire_age"].notna()].copy()
    logger.info("Loaded %s: %d rows", name, len(df))
    return df


def _build_feature_matrix(df: pd.DataFrame, expected_cols: list[str] | None = None) -> pd.DataFrame:
    """Select features and one-hot encode categoricals.

    If expected_cols is provided (inference / val / test), reindex to match
    training columns so missing dummies are zero-filled.
    """
    raw = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES].copy()
    # Cast booleans to int so XGBoost sees 0/1
    for col in BOOLEAN_FEATURES:
        raw[col] = raw[col].astype(int)

    encoded = pd.get_dummies(raw, columns=CATEGORICAL_FEATURES, drop_first=False)

    if expected_cols is not None:
        encoded = encoded.reindex(columns=expected_cols, fill_value=0)

    return encoded


# ── Training ───────────────────────────────────────────────────────────────────

def _check_circuit_coverage(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame) -> None:
    """Assert every circuit in val/test was seen in train.

    EventName one-hot dummies for unseen circuits are zero-filled (via
    reindex), causing silent garbage predictions. Fail fast instead.
    """
    train_circuits = set(train_df["EventName"].unique())
    for name, df in [("val", val_df), ("test", test_df)]:
        unseen = set(df["EventName"].unique()) - train_circuits
        if unseen:
            raise ValueError(
                f"Circuits in {name} not seen in train — EventName one-hot will "
                f"produce silent zero-fill for: {sorted(unseen)}. "
                "Either add these races to training data or switch to physical features."
            )
    logger.info("Circuit coverage check passed — all val/test circuits present in train.")


def train_baseline() -> tuple[xgb.XGBRegressor, list[str], dict]:
    """Train XGBoost baseline model.

    Returns (model, feature_columns, metrics_dict).
    """
    train_df = _load_split("train")
    val_df   = _load_split("val")
    test_df  = _load_split("test")

    _check_circuit_coverage(train_df, val_df, test_df)

    X_train = _build_feature_matrix(train_df)
    feature_cols = X_train.columns.tolist()

    X_val  = _build_feature_matrix(val_df,  expected_cols=feature_cols)
    X_test = _build_feature_matrix(test_df, expected_cols=feature_cols)

    y_train = train_df[TARGET].values
    y_val   = val_df[TARGET].values
    y_test  = test_df[TARGET].values

    logger.info(
        "Feature matrix: train=%s, val=%s, test=%s, features=%d",
        X_train.shape, X_val.shape, X_test.shape, len(feature_cols),
    )

    params = {k: v for k, v in XGB_PARAMS.items() if k != "early_stopping_rounds"}
    model = xgb.XGBRegressor(
        **params,
        early_stopping_rounds=XGB_PARAMS["early_stopping_rounds"],
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=50,
    )
    logger.info("Best iteration: %d", model.best_iteration)

    metrics = _evaluate(model, X_test, y_test, test_df, feature_cols)
    return model, feature_cols, metrics


# ── Evaluation ────────────────────────────────────────────────────────────────

def _evaluate(
    model: xgb.XGBRegressor,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    test_df: pd.DataFrame,
    feature_cols: list[str],
) -> dict:
    preds = model.predict(X_test)
    errors = np.abs(preds - y_test)

    mae  = float(mean_absolute_error(y_test, preds))
    rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
    logger.info("Test MAE: %.4f s   RMSE: %.4f s", mae, rmse)

    # Per-compound MAE
    compound_mae: dict[str, float] = {}
    for compound in ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]:
        mask = test_df["Compound"] == compound
        if mask.sum() == 0:
            continue
        compound_mae[compound] = float(mean_absolute_error(y_test[mask], preds[mask]))

    # Per-circuit MAE (top 5 best / worst)
    test_df = test_df.copy()
    test_df["_error"] = errors
    circuit_mae = (
        test_df.groupby("EventName")["_error"]
        .mean()
        .sort_values()
    )
    best5  = circuit_mae.head(5).to_dict()
    worst5 = circuit_mae.tail(5).to_dict()

    metrics = {
        "mae":          mae,
        "rmse":         rmse,
        "compound_mae": compound_mae,
        "circuit_mae_best5":  best5,
        "circuit_mae_worst5": worst5,
        "n_test":       int(len(y_test)),
        "best_iteration": int(model.best_iteration),
    }
    return metrics


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_metrics(metrics: dict) -> None:
    print(f"\n{'─'*50}")
    print(f"  Test MAE  : {metrics['mae']:.4f} s")
    print(f"  Test RMSE : {metrics['rmse']:.4f} s")
    print(f"  n_test    : {metrics['n_test']:,}")
    print(f"  Best iter : {metrics['best_iteration']}")

    print("\nPer-compound MAE:")
    for compound, mae in metrics["compound_mae"].items():
        print(f"  {compound:<14} {mae:.4f} s")

    print("\nTop 5 best circuits (lowest MAE):")
    for circuit, mae in metrics["circuit_mae_best5"].items():
        print(f"  {circuit:<35} {mae:.4f} s")

    print("\nTop 5 worst circuits (highest MAE):")
    for circuit, mae in metrics["circuit_mae_worst5"].items():
        print(f"  {circuit:<35} {mae:.4f} s")
    print(f"{'─'*50}")


def save_feature_importance_plot(model: xgb.XGBRegressor, feature_cols: list[str]) -> None:
    _FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    importances = model.feature_importances_
    idx = np.argsort(importances)[-10:][::-1]
    top_names   = [feature_cols[i] for i in idx]
    top_values  = importances[idx]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(range(10), top_values[::-1], color="#E8002D")
    ax.set_yticks(range(10))
    ax.set_yticklabels(top_names[::-1], fontsize=10)
    ax.set_xlabel("Gain (importance)")
    ax.set_title("XGBoost Baseline — Top 10 Feature Importances")
    ax.invert_yaxis()
    plt.tight_layout()

    out = _FIGURES_DIR / "baseline_feature_importance.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    logger.info("Feature importance plot saved → %s", out)

    print("\nTop 10 features by gain:")
    for name, val in zip(top_names, top_values):
        print(f"  {name:<35} {val:.6f}")


# ── Persistence ───────────────────────────────────────────────────────────────

def save_artifacts(
    model: xgb.XGBRegressor,
    feature_cols: list[str],
    metrics: dict,
) -> None:
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = _MODELS_DIR / "xgb_baseline.pkl"
    joblib.dump(model, model_path)
    logger.info("Model saved → %s", model_path)

    meta = {
        "model":          "xgb_baseline",
        "features":       feature_cols,
        "hyperparameters": {k: v for k, v in XGB_PARAMS.items()},
        "metrics":        metrics,
    }
    meta_path = _MODELS_DIR / "xgb_baseline_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    logger.info("Metadata saved → %s", meta_path)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train XGBoost baseline lap time model.")
    p.add_argument("--baseline", action="store_true", required=True,
                   help="Train the baseline model (no style features)")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    logger.info("Training XGBoost baseline model...")
    model, feature_cols, metrics = train_baseline()

    print_metrics(metrics)
    save_feature_importance_plot(model, feature_cols)
    save_artifacts(model, feature_cols, metrics)

    print(f"\nArtifacts saved to {_MODELS_DIR}/")

    target = 0.8
    if metrics["mae"] < target:
        print(f"\n✓ MAE {metrics['mae']:.4f}s < {target}s target — baseline looks good.")
    else:
        print(f"\n⚠ MAE {metrics['mae']:.4f}s >= {target}s target — investigate before Phase 3.2.")


if __name__ == "__main__":
    main()
