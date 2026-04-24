"""Race-based train/val/test split for lap_features.parquet.

Split policy (no data leakage):
  train  — 2021–2024 full seasons
  val    — 2025 rounds 1–12  (first half)
  test   — 2025 rounds 13–24 (second half)

Splitting by race ensures all laps from a given race weekend stay together.
Random row-level splits would leak track conditions, weather, and rival
behaviour across splits, inflating val/test metrics.

CLI:
    python -m pitiq.features.split
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_REPO_ROOT    = Path(__file__).parents[4]
_FEATURES_DIR = _REPO_ROOT / "data" / "features"

VAL_MAX_ROUND  = 12   # 2025 rounds 1-12  → val
TEST_MIN_ROUND = 13   # 2025 rounds 13-24 → test


def split_features(src: Path | None = None) -> dict[str, pd.DataFrame]:
    """Load lap_features.parquet and return train/val/test DataFrames."""
    path = src or (_FEATURES_DIR / "lap_features.parquet")
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run build pipeline first")

    df = pd.read_parquet(path)
    logger.info("Loaded %d rows from %s", len(df), path)

    train = df[df["Year"] <= 2024].copy()
    val   = df[(df["Year"] == 2025) & (df["RoundNumber"] <= VAL_MAX_ROUND)].copy()
    test  = df[(df["Year"] == 2025) & (df["RoundNumber"] >= TEST_MIN_ROUND)].copy()

    _verify_no_overlap(train, val, test)

    return {"train": train, "val": val, "test": test}


def _verify_no_overlap(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
) -> None:
    """Assert no (Year, RoundNumber) race key appears in more than one split."""
    def race_keys(df: pd.DataFrame) -> set:
        return set(zip(df["Year"], df["RoundNumber"]))

    tv = race_keys(train) & race_keys(val)
    tt = race_keys(train) & race_keys(test)
    vt = race_keys(val)   & race_keys(test)

    assert not tv, f"Train/val overlap on races: {tv}"
    assert not tt, f"Train/test overlap on races: {tt}"
    assert not vt, f"Val/test overlap on races: {vt}"
    logger.info("Overlap check passed — no race appears in more than one split")


def save_splits(splits: dict[str, pd.DataFrame]) -> None:
    _FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in splits.items():
        out = _FEATURES_DIR / f"{name}.parquet"
        df.to_parquet(out, index=False)
        logger.info("Saved %s: %d rows → %s", name, len(df), out)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Race-based train/val/test split.")
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

    splits = split_features()
    save_splits(splits)

    total = sum(len(v) for v in splits.values())
    print("\nSplit summary:")
    print(f"  {'split':<8}  {'rows':>8}  {'races':>6}  {'years'}")
    for name, df in splits.items():
        years = sorted(df["Year"].unique())
        year_str = f"{years[0]}–{years[-1]}" if len(years) > 1 else str(years[0])
        print(f"  {name:<8}  {len(df):>8,}  {df.groupby(['Year','RoundNumber']).ngroups:>6}  {year_str}")
    print(f"  {'total':<8}  {total:>8,}")
    print(f"\n  ✓ No race appears in more than one split")


if __name__ == "__main__":
    main()
