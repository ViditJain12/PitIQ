"""Tests for pitiq.data.clean.

Uses the 2-race laps_2024.parquet produced during Phase 1.2 smoke test.
Full multi-season tests run after the Phase 1.3 backfill completes.
"""

import numpy as np
import pandas as pd
import pytest

from pitiq.data.clean import (
    _PROCESSED_DIR,
    drop_in_out_laps,
    drop_inaccurate,
    fuel_correct,
    clean_season,
)


@pytest.fixture(scope="module")
def raw_2024() -> pd.DataFrame:
    path = _PROCESSED_DIR / "laps_2024.parquet"
    if not path.exists():
        pytest.skip("laps_2024.parquet not found — run ingest first")
    return pd.read_parquet(path)


def test_drop_inaccurate_removes_flagged_laps(raw_2024: pd.DataFrame):
    n_inaccurate = (~raw_2024["IsAccurate"].astype(bool)).sum()
    cleaned = drop_inaccurate(raw_2024)
    assert cleaned["IsAccurate"].all()
    assert len(cleaned) == len(raw_2024) - n_inaccurate


def test_drop_in_out_laps_removes_pit_laps(raw_2024: pd.DataFrame):
    n_pit = (raw_2024["PitInTime"].notna() | raw_2024["PitOutTime"].notna()).sum()
    cleaned = drop_in_out_laps(raw_2024)
    assert cleaned["PitInTime"].isna().all()
    assert cleaned["PitOutTime"].isna().all()
    assert len(cleaned) == len(raw_2024) - n_pit


def test_fuel_correct_adds_columns(raw_2024: pd.DataFrame):
    df = fuel_correct(raw_2024)
    assert "LapTimeCorrected" in df.columns
    assert "FuelCorrectionS" in df.columns


def test_fuel_correction_lap1_larger_than_last(raw_2024: pd.DataFrame):
    df = fuel_correct(raw_2024)
    lap1_correction = df.loc[df["LapNumber"] == 1, "FuelCorrectionS"]
    last_lap = df["LapNumber"].max()
    last_correction = df.loc[df["LapNumber"] == last_lap, "FuelCorrectionS"]
    assert lap1_correction.mean() > last_correction.mean()


def test_fuel_corrected_lap_time_less_than_raw(raw_2024: pd.DataFrame):
    df = fuel_correct(raw_2024)
    valid = df["LapTime"].notna() & df["LapTimeCorrected"].notna()
    assert (df.loc[valid, "LapTimeCorrected"] <= df.loc[valid, "LapTime"]).all()


def test_clean_season_returns_dataframe():
    df = clean_season(2024)
    if df is None:
        pytest.skip("laps_2024.parquet not found")
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0


def test_clean_season_no_inaccurate_laps():
    df = clean_season(2024)
    if df is None:
        pytest.skip("laps_2024.parquet not found")
    assert df["IsAccurate"].all()


def test_clean_season_no_pit_laps():
    df = clean_season(2024)
    if df is None:
        pytest.skip("laps_2024.parquet not found")
    assert df["PitInTime"].isna().all()
    assert df["PitOutTime"].isna().all()


def test_clean_season_missing_returns_none():
    result = clean_season(1900)  # year that will never exist
    assert result is None
