"""Season-level lap + telemetry ingestion pipeline.

CLI usage:
    python -m pitiq.data.ingest --season 2024
    python -m pitiq.data.ingest --season 2024 --max-races 3   # dev/test
"""

import argparse
import logging
import sys
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd

from pitiq.data.client import load_session

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parents[4]
_PROCESSED_DIR = _REPO_ROOT / "data" / "processed"

# Columns extracted directly from the FastF1 laps DataFrame
_LAP_COLS = [
    "Driver",
    "DriverNumber",
    "Team",
    "LapNumber",
    "LapTime",
    "Compound",
    "TyreLife",
    "Stint",
    "IsAccurate",
    "PitInTime",
    "PitOutTime",
    "Sector1Time",
    "Sector2Time",
    "Sector3Time",
    "Position",
    "TrackStatus",
    "FreshTyre",
]


# ---------------------------------------------------------------------------
# Per-lap telemetry summary
# ---------------------------------------------------------------------------

def _telemetry_summary(lap: pd.Series) -> dict:
    """Compute scalar telemetry features for a single lap.

    Returns an empty dict if telemetry is unavailable for this lap —
    the caller logs and moves on rather than crashing.
    """
    try:
        tel = lap.get_telemetry()
        if tel is None or tel.empty:
            return {}

        speed = tel["Speed"].dropna()
        throttle = tel["Throttle"].dropna()
        brake = tel["Brake"].dropna()

        return {
            "tel_speed_avg": float(speed.mean()) if len(speed) else np.nan,
            "tel_speed_max": float(speed.max()) if len(speed) else np.nan,
            "tel_throttle_pct": float((throttle > 0).mean() * 100) if len(throttle) else np.nan,
            "tel_brake_pct": float((brake > 0).mean() * 100) if len(brake) else np.nan,
        }
    except Exception as exc:
        logger.debug("Telemetry unavailable for lap (skipping): %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Single-session extraction
# ---------------------------------------------------------------------------

def _extract_session(
    session: fastf1.core.Session,
    year: int,
    round_number: int,
    event_name: str,
) -> pd.DataFrame:
    """Extract all laps from one session into a flat DataFrame."""
    laps = session.laps

    if laps is None or laps.empty:
        logger.warning("No laps found for %s (round %d)", event_name, round_number)
        return pd.DataFrame()

    # Keep only columns that are present (guards against FastF1 schema changes)
    present_cols = [c for c in _LAP_COLS if c in laps.columns]
    df = laps[present_cols].copy()

    # Add race context columns
    df["Year"] = year
    df["RoundNumber"] = round_number
    df["EventName"] = event_name

    # Convert timedelta columns to float seconds for Parquet compatibility
    for col in ["LapTime", "PitInTime", "PitOutTime", "Sector1Time", "Sector2Time", "Sector3Time"]:
        if col in df.columns:
            df[col] = pd.to_timedelta(df[col]).dt.total_seconds()

    # Attach telemetry summaries row by row
    tel_rows: list[dict] = []
    tel_missing = 0
    for _, lap in laps.iterrows():
        summary = _telemetry_summary(lap)
        if not summary:
            tel_missing += 1
        tel_rows.append(summary)

    tel_df = pd.DataFrame(tel_rows, index=df.index)
    df = pd.concat([df.reset_index(drop=True), tel_df.reset_index(drop=True)], axis=1)

    if tel_missing:
        logger.info(
            "%s round %d: %d/%d laps missing telemetry (skipped, not a crash)",
            event_name, round_number, tel_missing, len(laps),
        )

    return df


# ---------------------------------------------------------------------------
# Season ingestion
# ---------------------------------------------------------------------------

def ingest_season(year: int, max_races: int | None = None) -> pd.DataFrame:
    """Ingest all race sessions for *year*, return combined DataFrame.

    Args:
        year: F1 championship year.
        max_races: If set, stop after this many races (useful for quick tests).

    Returns:
        Combined DataFrame with all laps for the season.
    """
    _PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    schedule = fastf1.get_event_schedule(year, include_testing=False)
    if max_races is not None:
        schedule = schedule.head(max_races)

    all_frames: list[pd.DataFrame] = []
    failed: list[str] = []

    for _, event in schedule.iterrows():
        round_num = int(event["RoundNumber"])
        event_name = str(event["EventName"])

        logger.info("Processing round %d: %s", round_num, event_name)
        try:
            session = load_session(
                year,
                event_name,
                "R",
                load_laps=True,
                load_telemetry=True,
            )
            frame = _extract_session(session, year, round_num, event_name)
            if not frame.empty:
                all_frames.append(frame)
                logger.info("  → %d laps extracted", len(frame))
        except Exception as exc:
            logger.error("Failed to load %s (round %d): %s — skipping", event_name, round_num, exc)
            failed.append(f"{event_name} (round {round_num}): {exc}")

    if not all_frames:
        raise RuntimeError(f"No data extracted for season {year}. Failures: {failed}")

    combined = pd.concat(all_frames, ignore_index=True)

    out_path = _PROCESSED_DIR / f"laps_{year}.parquet"
    combined.to_parquet(out_path, index=False)
    logger.info("Saved %d laps → %s", len(combined), out_path)

    if failed:
        logger.warning("%d sessions failed:\n  %s", len(failed), "\n  ".join(failed))

    return combined


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingest FastF1 lap data for a season.")
    p.add_argument("--season", type=int, required=True, help="Championship year, e.g. 2024")
    p.add_argument(
        "--max-races",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N races (dev/testing shortcut)",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # Silence FastF1's verbose internal loggers unless user asked for DEBUG
    if args.log_level != "DEBUG":
        for noisy in ("fastf1", "urllib3", "requests"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    df = ingest_season(args.season, max_races=args.max_races)

    print(f"\nDone. {len(df):,} laps written to data/processed/laps_{args.season}.parquet")
    print(f"Columns ({len(df.columns)}): {list(df.columns)}")
    print(f"Races: {df['RoundNumber'].nunique()} | Drivers: {df['Driver'].nunique()}")


if __name__ == "__main__":
    main()
