"""Tests for pitiq.features.split."""

import pandas as pd
import pytest

from pitiq.features.split import _FEATURES_DIR, split_features


@pytest.fixture(scope="module")
def splits() -> dict[str, pd.DataFrame]:
    path = _FEATURES_DIR / "lap_features.parquet"
    if not path.exists():
        pytest.skip("lap_features.parquet not found")
    return split_features()


def test_three_splits_returned(splits):
    assert set(splits.keys()) == {"train", "val", "test"}


def test_row_counts_sum_to_total(splits):
    path = _FEATURES_DIR / "lap_features.parquet"
    total = len(pd.read_parquet(path))
    assert sum(len(v) for v in splits.values()) == total


def test_train_years(splits):
    assert set(splits["train"]["Year"].unique()) == {2021, 2022, 2023, 2024}


def test_val_years_and_rounds(splits):
    assert splits["val"]["Year"].unique().tolist() == [2025]
    assert splits["val"]["RoundNumber"].max() <= 12


def test_test_years_and_rounds(splits):
    assert splits["test"]["Year"].unique().tolist() == [2025]
    assert splits["test"]["RoundNumber"].min() >= 13


def test_no_race_overlap(splits):
    def race_keys(df):
        return set(zip(df["Year"], df["RoundNumber"]))

    assert not race_keys(splits["train"]) & race_keys(splits["val"])
    assert not race_keys(splits["train"]) & race_keys(splits["test"])
    assert not race_keys(splits["val"])   & race_keys(splits["test"])


def test_train_is_largest(splits):
    assert len(splits["train"]) > len(splits["val"])
    assert len(splits["train"]) > len(splits["test"])


def test_parquet_files_written(splits):
    for name in ["train", "val", "test"]:
        assert (_FEATURES_DIR / f"{name}.parquet").exists()
