"""XGBoost lap time prediction — baseline and driver-style-aware models.

Baseline (--baseline)
    No driver style features. Establishes the MAE reference so Phase 3.2
    can quantify the marginal improvement from style features.

Styled  (--styled)
    Joins 11 driver style features (Phase 2.5) by Driver before training.
    Identical splits, hyperparameters, and seed as baseline — the only
    difference is the addition of style features.
    Loads baseline metrics from xgb_baseline_meta.json and prints a
    side-by-side comparison table.

Features (baseline)
--------
Numeric  : tire_age, stint_number, fuel_load_estimate, laps_remaining,
           position, length_km, pit_loss_s, air_temp, track_temp, humidity,
           Year, RoundNumber
Categorical (one-hot): Compound, circuit_type, EventName
Boolean  : is_street_circuit, is_wet
Target   : LapTimeCorrected

Style features added in --styled (numeric, NaN handled natively by XGBoost)
    pace_trend_{soft,medium,hard}, cornering_aggression, throttle_smoothness,
    wet_skill_delta, tire_saving_coef, overall_pace_rank,
    sector_relative_{s1,s2,s3}

CLI
---
    python -m pitiq.ml.train_xgboost --baseline
    python -m pitiq.ml.train_xgboost --styled
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
except ImportError:
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
    # Year captures inter-season car development; RoundNumber captures within-season
    # development. Both always known at inference time — not leakage.
    "Year",
    "RoundNumber",
]
# EventName one-hot: physical proxies (length_km, pit_loss_s) don't uniquely
# identify circuits. 29-circuit set is fixed; sanity check guards unseen circuits.
CATEGORICAL_FEATURES = ["Compound", "circuit_type", "EventName"]
BOOLEAN_FEATURES     = ["is_street_circuit", "is_wet"]
TARGET               = "LapTimeCorrected"

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

# ── XGBoost hyperparameters ────────────────────────────────────────────────────
XGB_PARAMS = {
    "n_estimators":          500,
    "max_depth":             6,
    "learning_rate":         0.05,
    "subsample":             0.8,
    "colsample_bytree":      0.8,
    "objective":             "reg:squarederror",
    "random_state":          42,
    "n_jobs":                -1,
    "early_stopping_rounds": 20,
}

# Stable circuit threshold — circuits with < MIN_TRAIN_YEARS are labelled sparse
MIN_TRAIN_YEARS = 3


# ── Data helpers ───────────────────────────────────────────────────────────────

def _load_split(name: str) -> pd.DataFrame:
    path = _FEATURES_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run build pipeline first")
    df = pd.read_parquet(path)
    df = df[~df["Compound"].isin(["None", "nan"])].copy()
    df = df[df[TARGET].notna() & df["tire_age"].notna()].copy()
    logger.info("Loaded %s: %d rows", name, len(df))
    return df


def _load_styles() -> pd.DataFrame:
    path = _FEATURES_DIR / "driver_styles.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run pitiq.styles.build first")
    styles = pd.read_parquet(path)[STYLE_FEATURES]
    logger.info("Loaded driver styles: %d drivers × %d features", len(styles), len(styles.columns))
    return styles


def _join_styles(df: pd.DataFrame, styles: pd.DataFrame) -> pd.DataFrame:
    """Left-join style features onto lap dataframe by Driver index.

    Drivers not in driver_styles.parquet (e.g. reserve drivers) get NaN for
    all style columns. XGBoost handles NaN natively via its default missing-
    value branch — no imputation needed.
    """
    return df.join(styles, on="Driver", how="left")


def _build_feature_matrix(
    df: pd.DataFrame,
    expected_cols: list[str] | None = None,
    include_style: bool = False,
) -> pd.DataFrame:
    """Select, encode, and return the feature matrix.

    include_style=True appends STYLE_FEATURES columns (already numeric; NaN
    preserved for XGBoost's native missing-value handling).
    expected_cols reindexes to the training column set for val/test consistency.
    """
    extra = STYLE_FEATURES if include_style else []
    raw = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES + extra].copy()
    for col in BOOLEAN_FEATURES:
        raw[col] = raw[col].astype(int)

    encoded = pd.get_dummies(raw, columns=CATEGORICAL_FEATURES, drop_first=False)

    if expected_cols is not None:
        encoded = encoded.reindex(columns=expected_cols, fill_value=0)

    return encoded


def _circuit_train_years(train_df: pd.DataFrame) -> dict[str, int]:
    return train_df.groupby("EventName")["Year"].nunique().to_dict()


# ── Circuit coverage sanity check ─────────────────────────────────────────────

def _check_circuit_coverage(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
) -> None:
    train_circuits = set(train_df["EventName"].unique())
    for name, df in [("val", val_df), ("test", test_df)]:
        unseen = set(df["EventName"].unique()) - train_circuits
        if unseen:
            raise ValueError(
                f"Circuits in {name} not seen in train — EventName one-hot will "
                f"produce silent zero-fill for: {sorted(unseen)}."
            )
    logger.info("Circuit coverage check passed.")


# ── Training ───────────────────────────────────────────────────────────────────

def _train(include_style: bool) -> tuple[xgb.XGBRegressor, list[str], dict]:
    """Core training routine shared by baseline and styled runs."""
    train_df = _load_split("train")
    val_df   = _load_split("val")
    test_df  = _load_split("test")

    _check_circuit_coverage(train_df, val_df, test_df)

    if include_style:
        styles   = _load_styles()
        train_df = _join_styles(train_df, styles)
        val_df   = _join_styles(val_df,   styles)
        test_df  = _join_styles(test_df,  styles)
        n_style_nan = train_df[STYLE_FEATURES].isna().any(axis=1).sum()
        logger.info(
            "Style join complete — %d / %d train rows have ≥1 NaN style feature "
            "(XGBoost will route these via its missing-value branch)",
            n_style_nan, len(train_df),
        )

    X_train = _build_feature_matrix(train_df, include_style=include_style)
    feature_cols = X_train.columns.tolist()

    X_val  = _build_feature_matrix(val_df,  expected_cols=feature_cols, include_style=include_style)
    X_test = _build_feature_matrix(test_df, expected_cols=feature_cols, include_style=include_style)

    y_train = train_df[TARGET].values
    y_val   = val_df[TARGET].values
    y_test  = test_df[TARGET].values

    logger.info(
        "Feature matrix: train=%s, val=%s, test=%s, features=%d",
        X_train.shape, X_val.shape, X_test.shape, len(feature_cols),
    )

    params = {k: v for k, v in XGB_PARAMS.items() if k != "early_stopping_rounds"}
    model  = xgb.XGBRegressor(
        **params,
        early_stopping_rounds=XGB_PARAMS["early_stopping_rounds"],
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=50)
    logger.info("Best iteration: %d", model.best_iteration)

    train_years = _circuit_train_years(train_df)
    metrics = _evaluate(model, X_test, y_test, test_df, feature_cols, train_years)
    return model, feature_cols, metrics


def train_baseline() -> tuple[xgb.XGBRegressor, list[str], dict]:
    return _train(include_style=False)


def train_styled() -> tuple[xgb.XGBRegressor, list[str], dict]:
    return _train(include_style=True)


# ── Evaluation ────────────────────────────────────────────────────────────────

def _evaluate(
    model: xgb.XGBRegressor,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    test_df: pd.DataFrame,
    feature_cols: list[str],
    train_years: dict[str, int],
) -> dict:
    preds  = model.predict(X_test)
    errors = np.abs(preds - y_test)

    mae  = float(mean_absolute_error(y_test, preds))
    rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
    logger.info("Test MAE: %.4f s   RMSE: %.4f s", mae, rmse)

    test_df = test_df.copy()
    test_df["_pred"]  = preds
    test_df["_error"] = errors

    # Per-compound MAE
    compound_mae: dict[str, float] = {}
    for compound in ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]:
        mask = test_df["Compound"] == compound
        if mask.sum() == 0:
            continue
        compound_mae[compound] = float(mean_absolute_error(
            y_test[mask.values], preds[mask.values]
        ))

    # Per-circuit MAE
    circuit_mae = test_df.groupby("EventName")["_error"].mean().sort_values()

    # Stable / sparse subset MAE
    stable_circuits = [c for c in circuit_mae.index if train_years.get(c, 0) >= MIN_TRAIN_YEARS]
    sparse_circuits = [c for c in circuit_mae.index if train_years.get(c, 0) <  MIN_TRAIN_YEARS]

    stable_mask = test_df["EventName"].isin(stable_circuits)
    sparse_mask = test_df["EventName"].isin(sparse_circuits)

    stable_mae = float(test_df.loc[stable_mask, "_error"].mean()) if stable_mask.any() else float("nan")
    sparse_mae = float(test_df.loc[sparse_mask, "_error"].mean()) if sparse_mask.any() else float("nan")

    # Per-driver MAE
    driver_mae = (
        test_df.groupby("Driver")["_error"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "mae", "count": "n"})
        .sort_values("mae")
    )

    metrics = {
        "mae":             mae,
        "rmse":            rmse,
        "stable_mae":      stable_mae,
        "sparse_mae":      sparse_mae,
        "stable_circuits": stable_circuits,
        "sparse_circuits": sparse_circuits,
        "compound_mae":    compound_mae,
        "circuit_mae":     circuit_mae.to_dict(),
        "driver_mae":      driver_mae["mae"].to_dict(),
        "driver_n":        driver_mae["n"].to_dict(),
        "n_test":          int(len(y_test)),
        "best_iteration":  int(model.best_iteration),
    }
    return metrics


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_metrics(metrics: dict, label: str = "") -> None:
    tag = f" ({label})" if label else ""
    print(f"\n{'─'*52}")
    print(f"  Model{tag}")
    print(f"  Test MAE        : {metrics['mae']:.4f} s")
    print(f"  Test RMSE       : {metrics['rmse']:.4f} s")
    print(f"  Stable MAE      : {metrics['stable_mae']:.4f} s  ({', '.join(metrics['stable_circuits'][:2])}...)")
    print(f"  Sparse MAE      : {metrics['sparse_mae']:.4f} s  ({', '.join(metrics['sparse_circuits'])})")
    print(f"  n_test          : {metrics['n_test']:,}")
    print(f"  Best iteration  : {metrics['best_iteration']}")

    print("\nPer-compound MAE:")
    for compound, mae in metrics["compound_mae"].items():
        print(f"  {compound:<14} {mae:.4f} s")

    print("\nPer-circuit MAE:")
    for circuit, mae in sorted(metrics["circuit_mae"].items(), key=lambda x: x[1]):
        print(f"  {circuit:<35} {mae:.4f} s")
    print(f"{'─'*52}")


def print_comparison(baseline: dict, styled: dict) -> None:
    """Print side-by-side baseline vs styled comparison table."""

    def delta(b: float, s: float) -> str:
        d = s - b
        sign = "+" if d >= 0 else "−"
        return f"{sign}{abs(d):.4f}"

    def row(label: str, b: float, s: float) -> None:
        print(f"  {label:<34}  {b:>8.4f}s  {s:>8.4f}s  {delta(b, s):>8}")

    print(f"\n{'═'*62}")
    print(f"  {'Metric':<34}  {'Baseline':>9}  {'Styled':>8}  {'Δ':>8}")
    print(f"  {'─'*34}  {'─'*9}  {'─'*8}  {'─'*8}")

    row("Overall MAE",           baseline["mae"],        styled["mae"])
    row(f"Stable MAE ({len(styled['stable_circuits'])} circuits)",
                                  baseline["stable_mae"], styled["stable_mae"])
    row(f"Sparse MAE ({len(styled['sparse_circuits'])} circuit)",
                                  baseline["sparse_mae"], styled["sparse_mae"])

    print(f"  {'─'*34}  {'─'*9}  {'─'*8}  {'─'*8}")

    all_compounds = sorted(set(baseline["compound_mae"]) | set(styled["compound_mae"]))
    for compound in all_compounds:
        b_c = baseline["compound_mae"].get(compound, float("nan"))
        s_c = styled["compound_mae"].get(compound, float("nan"))
        if not (np.isnan(b_c) or np.isnan(s_c)):
            row(f"  {compound}", b_c, s_c)

    print(f"{'═'*62}")


def print_driver_breakdown(metrics: dict, n: int = 5) -> None:
    driver_mae = sorted(metrics["driver_mae"].items(), key=lambda x: x[1])
    driver_n   = metrics["driver_n"]

    print(f"\nTop {n} best-predicted drivers:")
    for driver, mae in driver_mae[:n]:
        print(f"  {driver:<5}  MAE={mae:.4f}s  (n={driver_n[driver]:.0f} laps)")

    print(f"\nTop {n} worst-predicted drivers:")
    for driver, mae in driver_mae[-n:][::-1]:
        print(f"  {driver:<5}  MAE={mae:.4f}s  (n={driver_n[driver]:.0f} laps)")


def save_feature_importance_plot(
    model: xgb.XGBRegressor,
    feature_cols: list[str],
    title: str,
    filename: str,
    n_top: int = 15,
    style_features: list[str] | None = None,
) -> None:
    _FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    importances = model.feature_importances_
    idx        = np.argsort(importances)[-n_top:][::-1]
    top_names  = [feature_cols[i] for i in idx]
    top_values = importances[idx]

    # Colour style features distinctly
    style_set = set(style_features or [])
    colors = ["#00D2BE" if n in style_set else "#E8002D" for n in top_names]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(range(n_top), top_values[::-1], color=colors[::-1])
    ax.set_yticks(range(n_top))
    ax.set_yticklabels(top_names[::-1], fontsize=9)
    ax.set_xlabel("Gain (importance)")
    ax.set_title(title)
    ax.invert_yaxis()
    if style_features:
        from matplotlib.patches import Patch
        ax.legend(handles=[
            Patch(color="#E8002D", label="Lap/circuit features"),
            Patch(color="#00D2BE", label="Driver style features"),
        ], loc="lower right")
    plt.tight_layout()

    out = _FIGURES_DIR / filename
    fig.savefig(out, dpi=150)
    plt.close(fig)
    logger.info("Feature importance plot saved → %s", out)

    print(f"\nTop {n_top} features by gain:")
    style_in_top = [n for n in top_names if n in style_set]
    for name, val in zip(top_names, top_values):
        tag = " ◀ style" if name in style_set else ""
        print(f"  {name:<40} {val:.6f}{tag}")

    if style_features is not None:
        if style_in_top:
            print(f"\nStyle features in top {n_top}: {style_in_top}")
        else:
            print(f"\nNo style features in top {n_top}.")


# ── Persistence ───────────────────────────────────────────────────────────────

def save_artifacts(
    model: xgb.XGBRegressor,
    feature_cols: list[str],
    metrics: dict,
    model_name: str,
) -> None:
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = _MODELS_DIR / f"{model_name}.pkl"
    joblib.dump(model, model_path)
    logger.info("Model saved → %s", model_path)

    # metrics contains non-serialisable types (numpy ints/floats) — normalise
    def _to_python(obj):
        if isinstance(obj, (np.integer,)):   return int(obj)
        if isinstance(obj, (np.floating,)):  return float(obj)
        if isinstance(obj, dict):            return {k: _to_python(v) for k, v in obj.items()}
        if isinstance(obj, list):            return [_to_python(v) for v in obj]
        return obj

    meta = _to_python({
        "model":           model_name,
        "features":        feature_cols,
        "hyperparameters": {k: v for k, v in XGB_PARAMS.items()},
        "metrics":         {k: v for k, v in metrics.items()
                            if k not in ("driver_mae", "driver_n")},
    })
    meta_path = _MODELS_DIR / f"{model_name}_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    logger.info("Metadata saved → %s", meta_path)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train XGBoost lap time models.")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--baseline", action="store_true",
                       help="Train baseline model (no style features)")
    group.add_argument("--styled",   action="store_true",
                       help="Train driver-style-aware model; prints comparison vs baseline")
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

    if args.baseline:
        logger.info("Training XGBoost baseline model...")
        model, feature_cols, metrics = train_baseline()
        print_metrics(metrics, label="baseline")
        save_feature_importance_plot(
            model, feature_cols,
            title="XGBoost Baseline — Top 15 Feature Importances",
            filename="baseline_feature_importance.png",
            n_top=15,
        )
        save_artifacts(model, feature_cols, metrics, model_name="xgb_baseline")
        print(f"\nArtifacts saved to {_MODELS_DIR}/")

    else:  # --styled
        logger.info("Training XGBoost styled model...")
        model, feature_cols, metrics = train_styled()
        print_metrics(metrics, label="styled")
        save_feature_importance_plot(
            model, feature_cols,
            title="XGBoost Styled — Top 15 Feature Importances",
            filename="styled_feature_importance.png",
            n_top=15,
            style_features=STYLE_FEATURES,
        )
        save_artifacts(model, feature_cols, metrics, model_name="xgb_styled")
        print(f"\nArtifacts saved to {_MODELS_DIR}/")

        # Load baseline metrics for comparison
        baseline_meta_path = _MODELS_DIR / "xgb_baseline_meta.json"
        if baseline_meta_path.exists():
            baseline_metrics = json.loads(baseline_meta_path.read_text())["metrics"]
            print_comparison(baseline_metrics, metrics)
        else:
            print("\n⚠ xgb_baseline_meta.json not found — run --baseline first for comparison.")

        print_driver_breakdown(metrics, n=5)


if __name__ == "__main__":
    main()
