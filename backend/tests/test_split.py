"""Tests for pitiq.features.split."""

import pandas as pd
import pytest

from pitiq.features.split import _FEATURES_DIR, split_features


# Load and return the train/val/test splits once for the entire test module.
@pytest.fixture(scope="module")
def splits() -> dict[str, pd.DataFrame]:
    path = _FEATURES_DIR / "lap_features.parquet"
    if not path.exists():
        pytest.skip("lap_features.parquet not found")
    return split_features()


# Verify that split_features returns exactly three keys: train, val, and test.
def test_three_splits_returned(splits):
    assert set(splits.keys()) == {"train", "val", "test"}


# Verify that the sum of rows across all splits equals the total in lap_features.parquet.
def test_row_counts_sum_to_total(splits):
    path = _FEATURES_DIR / "lap_features.parquet"
    total = len(pd.read_parquet(path))
    assert sum(len(v) for v in splits.values()) == total


# Verify that the training split contains exactly the years 2021–2024.
def test_train_years(splits):
    assert set(splits["train"]["Year"].unique()) == {2021, 2022, 2023, 2024}


# Verify that the validation split is 2025 rounds 1–12.
def test_val_years_and_rounds(splits):
    assert splits["val"]["Year"].unique().tolist() == [2025]
    assert splits["val"]["RoundNumber"].max() <= 12


# Verify that the test split is 2025 rounds 13 and above.
def test_test_years_and_rounds(splits):
    assert splits["test"]["Year"].unique().tolist() == [2025]
    assert splits["test"]["RoundNumber"].min() >= 13


# Verify that no (year, round) pair appears in more than one split.
def test_no_race_overlap(splits):
    # Return the set of (Year, RoundNumber) tuples present in a split DataFrame.
    def race_keys(df):
        return set(zip(df["Year"], df["RoundNumber"]))

    assert not race_keys(splits["train"]) & race_keys(splits["val"])
    assert not race_keys(splits["train"]) & race_keys(splits["test"])
    assert not race_keys(splits["val"])   & race_keys(splits["test"])


# Verify that the training split is the largest of the three splits.
def test_train_is_largest(splits):
    assert len(splits["train"]) > len(splits["val"])
    assert len(splits["train"]) > len(splits["test"])


# Verify that split_features writes train.parquet, val.parquet, and test.parquet to disk.
def test_parquet_files_written(splits):
    for name in ["train", "val", "test"]:
        assert (_FEATURES_DIR / f"{name}.parquet").exists()
