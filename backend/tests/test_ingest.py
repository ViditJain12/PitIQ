"""Tests for pitiq.data.ingest — uses real FastF1 cache (1 race)."""

import pandas as pd
import pytest

from pitiq.data.ingest import _PROCESSED_DIR, ingest_season


EXPECTED_LAP_COLS = {
    "Driver", "LapNumber", "LapTime", "Compound", "TyreLife",
    "Stint", "IsAccurate", "Year", "RoundNumber", "EventName",
    "Sector1Time", "Sector2Time", "Sector3Time",
    "tel_speed_avg", "tel_speed_max", "tel_throttle_pct", "tel_brake_pct",
}


@pytest.fixture(scope="module")
def single_race_df() -> pd.DataFrame:
    """Ingest just round 1 (Bahrain 2024) — already cached, should be fast."""
    return ingest_season(2024, max_races=1)


def test_returns_dataframe(single_race_df: pd.DataFrame):
    assert isinstance(single_race_df, pd.DataFrame)


def test_expected_columns_present(single_race_df: pd.DataFrame):
    missing = EXPECTED_LAP_COLS - set(single_race_df.columns)
    assert not missing, f"Missing columns: {missing}"


def test_row_count_reasonable(single_race_df: pd.DataFrame):
    # A 57-lap race with 20 drivers = ~1140 laps; allow some margin
    assert len(single_race_df) > 500


def test_lap_time_is_float_seconds(single_race_df: pd.DataFrame):
    valid = single_race_df["LapTime"].dropna()
    assert valid.between(50, 200).all(), "LapTime values look wrong (expected 50–200s)"


def test_telemetry_cols_numeric(single_race_df: pd.DataFrame):
    for col in ["tel_speed_avg", "tel_speed_max", "tel_throttle_pct", "tel_brake_pct"]:
        assert pd.api.types.is_float_dtype(single_race_df[col]), f"{col} is not float"


def test_parquet_written(single_race_df: pd.DataFrame):
    path = _PROCESSED_DIR / "laps_2024.parquet"
    assert path.exists(), f"Parquet not found at {path}"


def test_parquet_readable():
    path = _PROCESSED_DIR / "laps_2024.parquet"
    df = pd.read_parquet(path)
    assert len(df) > 0
