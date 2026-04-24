"""Phase 2.1 — Core lap feature engineering.

Reads data/processed/laps_all.parquet, computes per-lap ML features,
joins circuit metadata and per-session weather summaries, writes
data/features/lap_features.parquet.

CLI:
    python -m pitiq.features.build
    python -m pitiq.features.build --no-weather   # skip slow weather loads
"""

import argparse
import logging
import sys
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd

from pitiq.data.client import _CACHE_DIR, _ensure_cache

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parents[4]
_PROCESSED_DIR = _REPO_ROOT / "data" / "processed"
_FEATURES_DIR  = _REPO_ROOT / "data" / "features"

# Fuel constants — same as clean.py so features are consistent
_FUEL_START_KG       = 110.0
_FUEL_BURN_KG_PER_LAP = 1.8


# ---------------------------------------------------------------------------
# Circuit metadata lookup
# ---------------------------------------------------------------------------
# Keys match EventName strings in laps_all.parquet.
# circuit_type: "street" | "permanent"
# pit_loss_s: typical time lost per pit stop (pit-lane delta vs. staying out)

_CIRCUIT_META: dict[str, dict] = {
    "Bahrain Grand Prix":           {"length_km": 5.412, "type": "permanent", "pit_loss_s": 22.0},
    "Saudi Arabian Grand Prix":     {"length_km": 6.174, "type": "street",    "pit_loss_s": 24.0},
    "Australian Grand Prix":        {"length_km": 5.278, "type": "permanent", "pit_loss_s": 24.0},
    "Japanese Grand Prix":          {"length_km": 5.807, "type": "permanent", "pit_loss_s": 22.0},
    "Chinese Grand Prix":           {"length_km": 5.451, "type": "permanent", "pit_loss_s": 22.0},
    "Miami Grand Prix":             {"length_km": 5.412, "type": "street",    "pit_loss_s": 24.0},
    "Emilia Romagna Grand Prix":    {"length_km": 4.909, "type": "permanent", "pit_loss_s": 22.0},
    "Monaco Grand Prix":            {"length_km": 3.337, "type": "street",    "pit_loss_s": 28.0},
    "Canadian Grand Prix":          {"length_km": 4.361, "type": "street",    "pit_loss_s": 24.0},
    "Spanish Grand Prix":           {"length_km": 4.675, "type": "permanent", "pit_loss_s": 21.0},
    "Austrian Grand Prix":          {"length_km": 4.318, "type": "permanent", "pit_loss_s": 20.0},
    "Styrian Grand Prix":           {"length_km": 4.318, "type": "permanent", "pit_loss_s": 20.0},
    "British Grand Prix":           {"length_km": 5.891, "type": "permanent", "pit_loss_s": 21.0},
    "Hungarian Grand Prix":         {"length_km": 4.381, "type": "permanent", "pit_loss_s": 22.0},
    "Belgian Grand Prix":           {"length_km": 7.004, "type": "permanent", "pit_loss_s": 21.0},
    "Dutch Grand Prix":             {"length_km": 4.259, "type": "permanent", "pit_loss_s": 20.0},
    "Italian Grand Prix":           {"length_km": 5.793, "type": "permanent", "pit_loss_s": 23.0},
    "Azerbaijan Grand Prix":        {"length_km": 6.003, "type": "street",    "pit_loss_s": 25.0},
    "Singapore Grand Prix":         {"length_km": 4.940, "type": "street",    "pit_loss_s": 28.0},
    "United States Grand Prix":     {"length_km": 5.513, "type": "permanent", "pit_loss_s": 22.0},
    "Mexico City Grand Prix":       {"length_km": 4.304, "type": "permanent", "pit_loss_s": 22.0},
    "São Paulo Grand Prix":         {"length_km": 4.309, "type": "permanent", "pit_loss_s": 22.0},
    "Las Vegas Grand Prix":         {"length_km": 6.201, "type": "street",    "pit_loss_s": 26.0},
    "Qatar Grand Prix":             {"length_km": 5.380, "type": "permanent", "pit_loss_s": 22.0},
    "Abu Dhabi Grand Prix":         {"length_km": 5.281, "type": "permanent", "pit_loss_s": 22.0},
    "Portuguese Grand Prix":        {"length_km": 4.684, "type": "permanent", "pit_loss_s": 21.0},
    "French Grand Prix":            {"length_km": 5.842, "type": "permanent", "pit_loss_s": 21.0},
    "Turkish Grand Prix":           {"length_km": 5.338, "type": "permanent", "pit_loss_s": 22.0},
    "Russian Grand Prix":           {"length_km": 5.848, "type": "street",    "pit_loss_s": 24.0},
}


def _join_circuit_meta(df: pd.DataFrame) -> pd.DataFrame:
    meta_df = pd.DataFrame.from_dict(_CIRCUIT_META, orient="index").rename_axis("EventName").reset_index()
    meta_df = meta_df.rename(columns={"type": "circuit_type"})

    before = len(df)
    df = df.merge(meta_df, on="EventName", how="left")

    unknown = df["circuit_type"].isna().sum()
    if unknown:
        missing = df.loc[df["circuit_type"].isna(), "EventName"].unique()
        logger.warning(
            "%d laps have no circuit metadata — unknown events: %s",
            unknown, list(missing),
        )
    logger.info("Circuit metadata joined: %d → %d rows", before, len(df))
    return df


# ---------------------------------------------------------------------------
# Weather loading (per-session aggregate)
# ---------------------------------------------------------------------------

def _load_weather_for_sessions(
    sessions: list[tuple[int, str]],
) -> pd.DataFrame:
    """Load and aggregate weather for each (year, event_name) pair.

    Returns a DataFrame with one row per session and columns:
        Year, EventName, air_temp, track_temp, humidity, is_wet
    """
    _ensure_cache()
    rows: list[dict] = []
    total = len(sessions)

    for i, (year, event_name) in enumerate(sessions, 1):
        logger.info("Weather [%d/%d]: %d %s", i, total, year, event_name)
        try:
            session = fastf1.get_session(year, event_name, "R")
            session.load(laps=False, telemetry=False, weather=True, messages=False)
            w = session.weather_data

            if w is None or w.empty:
                raise ValueError("empty weather data")

            rows.append({
                "Year":       year,
                "EventName":  event_name,
                "air_temp":   float(w["AirTemp"].mean()),
                "track_temp": float(w["TrackTemp"].mean()),
                "humidity":   float(w["Humidity"].mean()),
                "is_wet":     bool(w["Rainfall"].any()),
            })
        except Exception as exc:
            logger.warning("Weather unavailable for %d %s (%s) — filling NaN", year, event_name, exc)
            rows.append({
                "Year": year, "EventName": event_name,
                "air_temp": np.nan, "track_temp": np.nan,
                "humidity": np.nan, "is_wet": False,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Core feature computation
# ---------------------------------------------------------------------------

def _compute_lap_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # --- tire_age: TyreLife is already per-lap tyre age from FastF1 ---
    df["tire_age"] = df["TyreLife"]

    # --- stint_number: Stint is already present ---
    df["stint_number"] = df["Stint"]

    # --- fuel_load_estimate: kg of fuel remaining at start of this lap ---
    df["fuel_load_estimate"] = (
        _FUEL_START_KG - (df["LapNumber"] - 1) * _FUEL_BURN_KG_PER_LAP
    ).clip(lower=0.0)

    # --- laps_remaining: total race laps minus current lap ---
    total_laps = (
        df.groupby(["Year", "RoundNumber"])["LapNumber"]
        .transform("max")
    )
    df["laps_remaining"] = (total_laps - df["LapNumber"]).clip(lower=0)

    # --- position: already present as Position ---
    df["position"] = df["Position"]

    return df


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def build_features(*, include_weather: bool = True) -> pd.DataFrame:
    _FEATURES_DIR.mkdir(parents=True, exist_ok=True)

    laps_path = _PROCESSED_DIR / "laps_all.parquet"
    if not laps_path.exists():
        raise FileNotFoundError(f"{laps_path} not found — run clean pipeline first")

    df = pd.read_parquet(laps_path)
    logger.info("Loaded %d laps from laps_all.parquet", len(df))

    # Derived per-lap features
    df = _compute_lap_features(df)
    logger.info("Per-lap features computed")

    # Circuit metadata
    df = _join_circuit_meta(df)

    # Weather
    if include_weather:
        sessions = (
            df[["Year", "EventName"]]
            .drop_duplicates()
            .sort_values(["Year", "EventName"])
            .itertuples(index=False)
        )
        session_list = [(r.Year, r.EventName) for r in sessions]
        weather_df = _load_weather_for_sessions(session_list)
        df = df.merge(weather_df, on=["Year", "EventName"], how="left")
        logger.info("Weather features joined")
    else:
        for col in ["air_temp", "track_temp", "humidity", "is_wet"]:
            df[col] = np.nan
        logger.info("Weather skipped — columns filled with NaN")

    # Encode circuit_type as boolean for ML convenience
    df["is_street_circuit"] = (df["circuit_type"] == "street").astype(bool)

    out_path = _FEATURES_DIR / "lap_features.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Saved %d rows → %s", len(df), out_path)
    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build lap feature dataset.")
    p.add_argument(
        "--no-weather",
        action="store_true",
        help="Skip weather loading (faster, leaves weather cols as NaN)",
    )
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
    if args.log_level != "DEBUG":
        for noisy in ("fastf1", "urllib3", "requests"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    df = build_features(include_weather=not args.no_weather)

    new_cols = [
        "tire_age", "stint_number", "fuel_load_estimate",
        "laps_remaining", "position",
        "length_km", "circuit_type", "pit_loss_s", "is_street_circuit",
        "air_temp", "track_temp", "humidity", "is_wet",
    ]
    print(f"\nDone. {len(df):,} rows → data/features/lap_features.parquet")
    print(f"New feature columns: {new_cols}")
    print(f"\nNull counts on new features:")
    print(df[new_cols].isnull().sum().to_string())


if __name__ == "__main__":
    main()
