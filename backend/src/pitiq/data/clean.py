"""Lap data cleaning pipeline.

Reads per-season Parquet files produced by ingest.py, applies cleaning
steps, and writes a combined laps_all.parquet ready for feature engineering.

Cleaning steps (in order):
  1. Drop inaccurate laps  (IsAccurate == False)
  2. Drop in-laps          (PitInTime is not NaN  — lap ends in the pit box)
  3. Drop out-laps         (PitOutTime is not NaN — lap starts from pit box)
  4. Fuel-correct LapTime  (remove the ~0.03 s/kg benefit of burning fuel)

CLI usage:
    python -m pitiq.data.clean
    python -m pitiq.data.clean --seasons 2023 2024   # subset
    python -m pitiq.data.clean --no-fuel-correction
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parents[4]
_PROCESSED_DIR = _REPO_ROOT / "data" / "processed"

# Standard F1 fuel constants
# ~110 kg start load, ~1.8 kg/lap burn rate, 0.03 s/kg lap-time effect
_FUEL_START_KG: float = 110.0
_FUEL_BURN_KG_PER_LAP: float = 1.8
_FUEL_EFFECT_S_PER_KG: float = 0.03

DEFAULT_SEASONS = [2021, 2022, 2023, 2024, 2025]


# ---------------------------------------------------------------------------
# Individual cleaning steps
# ---------------------------------------------------------------------------

def drop_inaccurate(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df[df["IsAccurate"].astype(bool)].copy()
    logger.info("drop_inaccurate: %d → %d rows (-%d)", before, len(df), before - len(df))
    return df


def drop_in_out_laps(df: pd.DataFrame) -> pd.DataFrame:
    """Remove laps where the car pitted in or out — these are not race-pace laps."""
    before = len(df)
    in_lap = df["PitInTime"].notna()
    out_lap = df["PitOutTime"].notna()
    df = df[~(in_lap | out_lap)].copy()
    logger.info("drop_in_out_laps: %d → %d rows (-%d)", before, len(df), before - len(df))
    return df


def fuel_correct(df: pd.DataFrame) -> pd.DataFrame:
    """Subtract the lap-time benefit of carrying fuel.

    Formula per lap:
        fuel_load  = max(0, FUEL_START_KG - (LapNumber - 1) * FUEL_BURN_KG_PER_LAP)
        correction = fuel_load * FUEL_EFFECT_S_PER_KG
        LapTimeCorrected = LapTime - correction

    This shifts all laps toward their equivalent empty-tank pace, making
    laps from lap 1 and lap 50 directly comparable for the ML model.
    """
    fuel_load = (_FUEL_START_KG - (df["LapNumber"] - 1) * _FUEL_BURN_KG_PER_LAP).clip(lower=0.0)
    correction = fuel_load * _FUEL_EFFECT_S_PER_KG
    df = df.copy()
    df["LapTimeCorrected"] = df["LapTime"] - correction
    df["FuelCorrectionS"] = correction  # keep for inspection / debugging
    logger.info(
        "fuel_correct: median correction = %.3f s, max = %.3f s",
        correction.median(),
        correction.max(),
    )
    return df


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def clean_season(year: int, *, apply_fuel_correction: bool = True) -> pd.DataFrame | None:
    """Load and clean one season's Parquet file. Returns None if file missing."""
    path = _PROCESSED_DIR / f"laps_{year}.parquet"
    if not path.exists():
        logger.warning("laps_%d.parquet not found — skipping (run ingest first)", year)
        return None

    df = pd.read_parquet(path)
    logger.info("Loaded %d laps for %d from %s", len(df), year, path)

    df = drop_inaccurate(df)
    df = drop_in_out_laps(df)
    if apply_fuel_correction:
        df = fuel_correct(df)

    logger.info("Season %d cleaned: %d laps remaining", year, len(df))
    return df


def build_combined(
    seasons: list[int] = DEFAULT_SEASONS,
    *,
    apply_fuel_correction: bool = True,
) -> pd.DataFrame:
    """Clean each season and concatenate into laps_all.parquet.

    Only seasons whose per-season Parquet already exists are included;
    missing seasons are logged and skipped so partial backfills work.
    """
    frames: list[pd.DataFrame] = []
    for year in seasons:
        df = clean_season(year, apply_fuel_correction=apply_fuel_correction)
        if df is not None and not df.empty:
            frames.append(df)

    if not frames:
        raise RuntimeError(
            f"No cleaned data for seasons {seasons}. "
            "Run `python -m pitiq.data.ingest --season <year>` first."
        )

    combined = pd.concat(frames, ignore_index=True)

    out_path = _PROCESSED_DIR / "laps_all.parquet"
    combined.to_parquet(out_path, index=False)
    logger.info(
        "Saved laps_all.parquet: %d laps, %d seasons, %d drivers",
        len(combined),
        combined["Year"].nunique(),
        combined["Driver"].nunique(),
    )
    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Clean and combine per-season lap Parquet files.")
    p.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=DEFAULT_SEASONS,
        metavar="YEAR",
        help=f"Seasons to include (default: {DEFAULT_SEASONS})",
    )
    p.add_argument(
        "--no-fuel-correction",
        action="store_true",
        help="Skip fuel-load lap-time correction (useful for debugging)",
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

    df = build_combined(
        seasons=args.seasons,
        apply_fuel_correction=not args.no_fuel_correction,
    )

    print(f"\nDone.")
    print(f"  Laps:    {len(df):,}")
    print(f"  Seasons: {sorted(df['Year'].unique())}")
    print(f"  Drivers: {df['Driver'].nunique()}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Output:  data/processed/laps_all.parquet")


if __name__ == "__main__":
    main()
