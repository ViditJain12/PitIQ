"""Tests for pitiq.features.build — runs against existing lap_features.parquet."""

import pandas as pd
import pytest

from pitiq.features.build import _FEATURES_DIR, _compute_lap_features, _join_circuit_meta


@pytest.fixture(scope="module")
def features_df() -> pd.DataFrame:
    path = _FEATURES_DIR / "lap_features.parquet"
    if not path.exists():
        pytest.skip("lap_features.parquet not found — run build pipeline first")
    return pd.read_parquet(path)


# --- Schema ---

def test_row_count(features_df: pd.DataFrame):
    assert len(features_df) > 100_000


def test_required_columns_present(features_df: pd.DataFrame):
    required = {
        "tire_age", "stint_number", "fuel_load_estimate", "laps_remaining", "position",
        "length_km", "circuit_type", "pit_loss_s", "is_street_circuit",
        "air_temp", "track_temp", "humidity", "is_wet",
    }
    missing = required - set(features_df.columns)
    assert not missing, f"Missing columns: {missing}"


# --- Per-lap feature ranges ---

def test_fuel_load_estimate_bounds(features_df: pd.DataFrame):
    assert features_df["fuel_load_estimate"].between(0, 110).all()


def test_laps_remaining_non_negative(features_df: pd.DataFrame):
    assert (features_df["laps_remaining"] >= 0).all()


def test_position_range(features_df: pd.DataFrame):
    valid = features_df["position"].dropna()
    assert valid.between(1, 20).all()


def test_tire_age_positive(features_df: pd.DataFrame):
    valid = features_df["tire_age"].dropna()
    assert (valid >= 1).all()


# --- Circuit metadata ---

def test_no_unknown_circuits(features_df: pd.DataFrame):
    assert features_df["circuit_type"].notna().all(), "Some rows have no circuit metadata"


def test_circuit_type_values(features_df: pd.DataFrame):
    assert set(features_df["circuit_type"].unique()) <= {"permanent", "street"}


def test_street_circuit_flag_consistent(features_df: pd.DataFrame):
    street_rows = features_df["circuit_type"] == "street"
    assert (features_df.loc[street_rows, "is_street_circuit"]).all()
    assert (~features_df.loc[~street_rows, "is_street_circuit"]).all()


def test_pit_loss_range(features_df: pd.DataFrame):
    assert features_df["pit_loss_s"].between(15, 35).all()


# --- Weather ---

def test_weather_no_nulls(features_df: pd.DataFrame):
    for col in ["air_temp", "track_temp", "humidity"]:
        assert features_df[col].notna().all(), f"{col} has nulls"


def test_known_wet_races_flagged(features_df: pd.DataFrame):
    # Spa 2021 was red-flagged due to rain — should be wet
    spa = features_df[(features_df["Year"] == 2021) & (features_df["EventName"] == "Belgian Grand Prix")]
    if not spa.empty:
        assert spa["is_wet"].all()


def test_known_dry_race_not_wet(features_df: pd.DataFrame):
    # Abu Dhabi is always dry
    abu = features_df[features_df["EventName"] == "Abu Dhabi Grand Prix"]
    if not abu.empty:
        assert not abu["is_wet"].any()


# --- Unit tests for compute functions (no file I/O) ---

def test_fuel_load_formula():
    import pandas as pd
    df = pd.DataFrame({"LapNumber": [1, 10, 50], "TyreLife": [1, 5, 3],
                       "Stint": [1, 1, 2], "Position": [1, 2, 3],
                       "Year": [2024, 2024, 2024], "RoundNumber": [1, 1, 1]})
    out = _compute_lap_features(df)
    assert out.loc[0, "fuel_load_estimate"] == pytest.approx(110.0)
    assert out.loc[1, "fuel_load_estimate"] == pytest.approx(110.0 - 9 * 1.8)
    assert out.loc[2, "fuel_load_estimate"] == pytest.approx(110.0 - 49 * 1.8)
