"""Inference wrapper around the styled XGBoost model (Phase 3.3).

Exposes three public functions:

    predict_lap_time(driver, circuit, compound, tire_age, ...)  → float
    predict_degradation_curve(driver, circuit, compound, ...)   → list[float]
    degradation_curve_to_json(curve, metadata)                  → dict

The module is designed for zero-overhead repeated calls: model, feature list,
driver styles, and circuit defaults are loaded once and cached.

CLI (validation)
----------------
    python -m pitiq.ml.predict
"""

from __future__ import annotations

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

try:
    import joblib
except ImportError:
    import pickle as joblib  # type: ignore[no-redef]

import xgboost as xgb

logger = logging.getLogger(__name__)

_REPO_ROOT    = Path(__file__).parents[4]
_MODELS_DIR   = _REPO_ROOT / "models"
_FEATURES_DIR = _REPO_ROOT / "data" / "features"
_FIGURES_DIR  = _MODELS_DIR / "figures"

_DEFAULT_MODEL_PATH = str(_MODELS_DIR / "xgb_styled.pkl")

VALID_COMPOUNDS = {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"}

# Fuel model constants — match Phase 1.3 / DECISIONS.md
_FUEL_START_KG       = 110.0
_FUEL_BURN_KG_PER_LAP = 1.8


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fuel_load(race_lap: int) -> float:
    return max(0.0, _FUEL_START_KG - (race_lap - 1) * _FUEL_BURN_KG_PER_LAP)


def _build_circuit_defaults(features_path: Path) -> dict[str, dict]:
    """Compute per-circuit inference defaults from the features parquet.

    Returns a dict keyed by EventName with sub-keys:
        length_km, circuit_type, pit_loss_s, is_street_circuit,
        air_temp, track_temp, humidity, typical_round
    """
    df = pd.read_parquet(features_path)
    static = df.groupby("EventName")[
        ["length_km", "circuit_type", "pit_loss_s", "is_street_circuit"]
    ].first()
    weather = df.groupby("EventName")[["air_temp", "track_temp", "humidity"]].mean()
    # typical_round: prefer most recent year's round number
    latest_year_per_circuit = df.groupby("EventName")["Year"].max()
    rounds: dict[str, int] = {}
    for circuit, yr in latest_year_per_circuit.items():
        sub = df[(df["EventName"] == circuit) & (df["Year"] == yr)]
        rounds[circuit] = int(sub["RoundNumber"].mode().iloc[0])

    out: dict[str, dict] = {}
    for circuit in static.index:
        out[circuit] = {
            "length_km":        float(static.loc[circuit, "length_km"]),
            "circuit_type":     str(static.loc[circuit, "circuit_type"]),
            "pit_loss_s":       float(static.loc[circuit, "pit_loss_s"]),
            "is_street_circuit": bool(static.loc[circuit, "is_street_circuit"]),
            "air_temp":         float(weather.loc[circuit, "air_temp"]),
            "track_temp":       float(weather.loc[circuit, "track_temp"]),
            "humidity":         float(weather.loc[circuit, "humidity"]),
            "typical_round":    int(rounds[circuit]),
        }
    return out


# ── Model loading (cached) ────────────────────────────────────────────────────

@lru_cache(maxsize=4)
def load_model(
    model_path: str = _DEFAULT_MODEL_PATH,
) -> tuple[xgb.XGBRegressor, list[str], pd.DataFrame, dict[str, dict]]:
    """Load model, feature list, driver styles, and circuit defaults.

    Results are cached by model_path — repeated calls are free.
    Returns (model, feature_cols, styles_df, circuit_defaults).
    """
    model_p = Path(model_path)
    meta_p  = model_p.with_suffix("").parent / (model_p.stem + "_meta.json")

    if not model_p.exists():
        raise FileNotFoundError(f"Model not found: {model_p}")
    if not meta_p.exists():
        raise FileNotFoundError(f"Metadata not found: {meta_p}")

    model        = joblib.load(model_p)
    feature_cols = json.loads(meta_p.read_text())["features"]
    styles_df    = pd.read_parquet(_FEATURES_DIR / "driver_styles.parquet")

    features_path = _FEATURES_DIR / "lap_features.parquet"
    if not features_path.exists():
        raise FileNotFoundError(f"lap_features.parquet not found — needed for circuit defaults")
    circuit_defaults = _build_circuit_defaults(features_path)

    logger.info(
        "Loaded model %s — %d features, %d drivers, %d circuits",
        model_p.name, len(feature_cols), len(styles_df), len(circuit_defaults),
    )
    return model, feature_cols, styles_df, circuit_defaults


# ── Single-lap inference ──────────────────────────────────────────────────────

def predict_lap_time(
    driver: str,
    circuit: str,
    compound: str,
    tire_age: int | float,
    stint_number: int = 1,
    fuel_load: float | None = None,
    position: float = 10.0,
    laps_remaining: float = 30.0,
    air_temp: float | None = None,
    track_temp: float | None = None,
    humidity: float | None = None,
    is_wet: bool = False,
    year: int = 2025,
    round_number: int | None = None,
    model_path: str = _DEFAULT_MODEL_PATH,
) -> float:
    """Predict a single lap time in seconds.

    Unknown drivers (not in driver_styles.parquet) receive NaN style features;
    XGBoost routes these via its native missing-value branch.

    Args:
        driver:         3-letter driver code, e.g. 'VER'
        circuit:        EventName as it appears in training data, e.g. 'Italian Grand Prix'
        compound:       One of SOFT / MEDIUM / HARD / INTERMEDIATE / WET (case-insensitive)
        tire_age:       Laps on current set (1 = fresh)
        stint_number:   Stint index within the race (1-indexed)
        fuel_load:      Fuel mass in kg; if None, derived from race_lap = stint_start_lap + tire_age - 1
                        via the standard 110kg / 1.8kg-per-lap model
        position:       Current race position (1=leader)
        laps_remaining: Laps left in race at this point
        air_temp:       Air temperature °C; defaults to circuit training mean
        track_temp:     Track temperature °C; defaults to circuit training mean
        humidity:       Relative humidity %; defaults to circuit training mean
        is_wet:         Whether race conditions are wet
        year:           Season year (used by model for car-generation calibration)
        round_number:   Race round number; defaults to most recent round for this circuit
    """
    # Always call positionally so lru_cache uses a consistent key
    model, feature_cols, styles_df, circuit_defaults = load_model(model_path)

    compound = compound.upper()
    if compound not in VALID_COMPOUNDS:
        raise ValueError(f"compound must be one of {VALID_COMPOUNDS}, got {compound!r}")

    if circuit not in circuit_defaults:
        known = sorted(circuit_defaults.keys())
        raise ValueError(
            f"Unknown circuit {circuit!r}. Known circuits:\n  " + "\n  ".join(known)
        )

    meta = circuit_defaults[circuit]

    # Weather defaults
    _air_temp    = air_temp    if air_temp    is not None else meta["air_temp"]
    _track_temp  = track_temp  if track_temp  is not None else meta["track_temp"]
    _humidity    = humidity    if humidity    is not None else meta["humidity"]
    _round       = round_number if round_number is not None else meta["typical_round"]

    # Fuel: caller can override; otherwise we require an explicit fuel_load
    # (predict_degradation_curve always passes it)
    if fuel_load is None:
        fuel_load = _fuel_load(int(tire_age))

    # Style features — NaN for unknown drivers
    style_vals: dict[str, float] = {}
    if driver in styles_df.index:
        style_vals = styles_df.loc[driver].to_dict()
    else:
        logger.debug("Driver %s not in driver_styles — using NaN style features", driver)
        from pitiq.ml.train_xgboost import STYLE_FEATURES
        style_vals = {f: float("nan") for f in STYLE_FEATURES}

    from pitiq.ml.train_xgboost import STYLE_FEATURES, NUMERIC_FEATURES, CATEGORICAL_FEATURES, BOOLEAN_FEATURES

    row: dict[str, object] = {
        # Numeric
        "tire_age":           float(tire_age),
        "stint_number":       float(stint_number),
        "fuel_load_estimate": float(fuel_load),
        "laps_remaining":     float(laps_remaining),
        "position":           float(position),
        "length_km":          meta["length_km"],
        "pit_loss_s":         meta["pit_loss_s"],
        "air_temp":           float(_air_temp),
        "track_temp":         float(_track_temp),
        "humidity":           float(_humidity),
        "Year":               float(year),
        "RoundNumber":        float(_round),
        # Categorical (will be one-hot encoded)
        "Compound":           compound,
        "circuit_type":       meta["circuit_type"],
        "EventName":          circuit,
        # Boolean (int cast happens inside _build_feature_matrix)
        "is_street_circuit":  meta["is_street_circuit"],
        "is_wet":             is_wet,
    }
    # Add style features
    for feat in STYLE_FEATURES:
        row[feat] = style_vals.get(feat, float("nan"))

    df = pd.DataFrame([row])

    from pitiq.ml.train_xgboost import _build_feature_matrix
    X = _build_feature_matrix(df, expected_cols=feature_cols, include_style=True)

    return float(model.predict(X)[0])


# ── Degradation curve ─────────────────────────────────────────────────────────

def predict_degradation_curve(
    driver: str,
    circuit: str,
    compound: str,
    stint_start_lap: int,
    stint_length: int,
    total_race_laps: int,
    stint_number: int = 1,
    position: float = 10.0,
    apply_compound_dynamics: bool = False,
    **kwargs,
) -> list[float]:
    """Predict lap times for an entire stint.

    tire_age iterates 1..stint_length. Fuel load and laps_remaining are
    computed from the race lap number (stint_start_lap + tire_age - 1).

    Args:
        driver:                  Driver code
        circuit:                 EventName
        compound:                Tyre compound
        stint_start_lap:         Race lap on which this stint begins (1-indexed)
        stint_length:            Number of laps in the stint
        total_race_laps:         Total laps in the race (for laps_remaining)
        stint_number:            Stint index (1-indexed)
        position:                Assumed race position throughout stint
        apply_compound_dynamics: If True, apply fresh-tyre offset and post-cliff
                                 penalty from compound_constants on top of the
                                 XGBoost prediction. Default False so the raw
                                 model output is preserved for Phase 4 to layer
                                 compound dynamics explicitly in the RaceEnv.
        **kwargs:                Forwarded to predict_lap_time (air_temp,
                                 track_temp, humidity, is_wet, year, round_number)
    """
    from pitiq.ml.compound_constants import (
        COMPOUND_CLIFF_LAP,
        COMPOUND_CLIFF_PENALTY_S,
        COMPOUND_FRESH_TIRE_OFFSET_S,
    )
    compound_upper = compound.upper()

    curve: list[float] = []
    for tire_age in range(1, stint_length + 1):
        race_lap = stint_start_lap + tire_age - 1
        lap_time = predict_lap_time(
            driver=driver,
            circuit=circuit,
            compound=compound,
            tire_age=tire_age,
            stint_number=stint_number,
            fuel_load=_fuel_load(race_lap),
            position=position,
            laps_remaining=float(total_race_laps - race_lap),
            **kwargs,
        )
        if apply_compound_dynamics:
            # Fresh-tyre offset (constant across the stint)
            lap_time += COMPOUND_FRESH_TIRE_OFFSET_S.get(compound_upper, 0.0)
            # Post-cliff penalty (zero until cliff, then grows linearly)
            laps_past_cliff = max(0, tire_age - COMPOUND_CLIFF_LAP.get(compound_upper, 999))
            lap_time += laps_past_cliff * COMPOUND_CLIFF_PENALTY_S.get(compound_upper, 0.0)
        curve.append(lap_time)
    return curve


# ── JSON serialisation ────────────────────────────────────────────────────────

def degradation_curve_to_json(
    curve: list[float],
    metadata: dict,
) -> dict:
    """Convert a degradation curve to API-friendly JSON.

    Args:
        curve:    List of lap times from predict_degradation_curve
        metadata: Dict with at minimum: driver, circuit, compound

    Returns dict with keys:
        driver, circuit, compound, stint_length, lap_times,
        cumulative_time, mean_lap_time, degradation_per_lap
    """
    if not curve:
        raise ValueError("curve must be non-empty")

    cumulative = list(np.cumsum(curve))
    # Linear regression slope (degradation per lap, positive = getting slower)
    x = np.arange(len(curve), dtype=float)
    slope = float(np.polyfit(x, curve, 1)[0])

    return {
        "driver":             metadata.get("driver", ""),
        "circuit":            metadata.get("circuit", ""),
        "compound":           metadata.get("compound", ""),
        "stint_length":       len(curve),
        "lap_times":          [round(t, 4) for t in curve],
        "cumulative_time":    [round(t, 4) for t in cumulative],
        "mean_lap_time":      round(float(np.mean(curve)), 4),
        "degradation_per_lap": round(slope, 6),
    }


# ── Validation / CLI ──────────────────────────────────────────────────────────

def _run_validation() -> None:
    circuit      = "Italian Grand Prix"
    total_laps   = 53
    stint_start  = 2
    stint_length = 30
    compounds    = ["SOFT", "MEDIUM", "HARD"]
    colors       = {"SOFT": "#E8002D", "MEDIUM": "#FFF500", "HARD": "#CCCCCC"}

    print(f"\n{'═'*60}")
    print(f"  Validation: VER @ {circuit}  (stint start L{stint_start}, {stint_length} laps)")
    print(f"{'═'*60}")

    # ── Pure model curves (apply_compound_dynamics=False) ─────────────────────
    print("\n  [Pure XGBoost — no compound dynamics]")
    pure_curves: dict[str, list[float]] = {}
    for compound in compounds:
        curve = predict_degradation_curve(
            driver="VER", circuit=circuit, compound=compound,
            stint_start_lap=stint_start, stint_length=stint_length,
            total_race_laps=total_laps,
        )
        j = degradation_curve_to_json(curve, {"driver": "VER", "circuit": circuit, "compound": compound})
        pure_curves[compound] = curve
        print(f"\n  {compound}")
        print(f"    First 5 lap times : {[round(t, 3) for t in curve[:5]]}")
        print(f"    Last 5 lap times  : {[round(t, 3) for t in curve[-5:]]}")
        print(f"    Mean lap time     : {j['mean_lap_time']:.3f}s")
        print(f"    Degradation/lap   : {j['degradation_per_lap']:+.4f}s  "
              f"({'increasing ✓' if j['degradation_per_lap'] > 0 else 'decreasing — low-deg circuit'})")

    # ── With compound dynamics ─────────────────────────────────────────────────
    print(f"\n  [With compound dynamics — cliff + fresh-tyre offset]")
    dyn_curves: dict[str, list[float]] = {}
    for compound in compounds:
        curve = predict_degradation_curve(
            driver="VER", circuit=circuit, compound=compound,
            stint_start_lap=stint_start, stint_length=stint_length,
            total_race_laps=total_laps,
            apply_compound_dynamics=True,
        )
        j = degradation_curve_to_json(curve, {"driver": "VER", "circuit": circuit, "compound": compound})
        dyn_curves[compound] = curve
        print(f"\n  {compound}")
        print(f"    First 5 lap times : {[round(t, 3) for t in curve[:5]]}")
        print(f"    Last 5 lap times  : {[round(t, 3) for t in curve[-5:]]}")
        print(f"    Mean lap time     : {j['mean_lap_time']:.3f}s")
        print(f"    Degradation/lap   : {j['degradation_per_lap']:+.4f}s")

    # Soft cliff check: at tire_age=18 soft should begin rising above medium
    soft_at_cliff  = dyn_curves["SOFT"][17]   # tire_age=18 (index 17)
    med_at_cliff   = dyn_curves["MEDIUM"][17]
    soft_at_cliff5 = dyn_curves["SOFT"][min(22, stint_length-1)]   # 5 laps past cliff
    med_at_cliff5  = dyn_curves["MEDIUM"][min(22, stint_length-1)]
    print(f"\n  Soft cliff check:")
    print(f"    SOFT at tire_age=18   : {soft_at_cliff:.3f}s  MEDIUM: {med_at_cliff:.3f}s  "
          f"({'SOFT > MEDIUM ✓' if soft_at_cliff > med_at_cliff else 'SOFT <= MEDIUM'})")
    print(f"    SOFT at tire_age=23   : {soft_at_cliff5:.3f}s  MEDIUM: {med_at_cliff5:.3f}s")
    med_hard_diff = dyn_curves["MEDIUM"][0] - dyn_curves["HARD"][0]
    print(f"  MEDIUM vs HARD at lap 1: Δ={med_hard_diff:+.3f}s  "
          f"({'differentiated ✓' if abs(med_hard_diff) > 0.05 else 'still identical'})")

    # VER vs HAM on Medium — cumulative stint time diff
    print(f"\n{'─'*60}")
    print(f"  VER vs HAM — MEDIUM  @ {circuit}")
    ver_med = predict_degradation_curve(
        "VER", circuit, "MEDIUM", stint_start, stint_length, total_laps,
    )
    ham_med = predict_degradation_curve(
        "HAM", circuit, "MEDIUM", stint_start, stint_length, total_laps,
    )
    ver_cum = sum(ver_med)
    ham_cum = sum(ham_med)
    print(f"    VER cumulative stint time : {ver_cum:.3f}s")
    print(f"    HAM cumulative stint time : {ham_cum:.3f}s")
    print(f"    Δ (HAM − VER)             : {ham_cum - ver_cum:+.3f}s  "
          f"({'HAM slower ✓' if ham_cum > ver_cum else 'HAM faster'})")
    _, _, styles, _ = load_model(_DEFAULT_MODEL_PATH)
    print(f"    overall_pace_rank — VER: {styles.loc['VER','overall_pace_rank']:.2f}  "
          f"HAM: {styles.loc['HAM','overall_pace_rank']:.2f}")

    # ── Plots ──────────────────────────────────────────────────────────────────
    _FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    x = list(range(1, stint_length + 1))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(f"VER @ {circuit} — L{stint_start}, {stint_length}-lap stint", fontsize=12)

    for ax, curve_dict, title in [
        (axes[0], pure_curves,  "Pure XGBoost (no compound dynamics)"),
        (axes[1], dyn_curves,   "With compound dynamics (cliff + offset)"),
    ]:
        for compound in compounds:
            ax.plot(x, curve_dict[compound], label=compound,
                    color=colors[compound], linewidth=2, marker="o", markersize=2)
        ax.set_xlabel("Tire age (laps)")
        ax.set_ylabel("Predicted lap time (s)")
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = _FIGURES_DIR / "degradation_curves_validation.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"\n  Plot saved → {out}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    _run_validation()
