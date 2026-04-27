"""Race-based train/val/test split for lap_features.parquet.

Split policy (explicit stratified race selection):
  test  — 6 races spanning 2024–2025 with mixed training history:
            2024 R14  Belgian GP          (stable: 3 train years)
            2024 R19  United States GP    (stable: 4 train years)
            2024 R23  Qatar GP            (stable: 3 train years)
            2025 R7   Emilia Romagna GP   (stable: 3 train years)
            2025 R15  Dutch GP            (stable: 4 train years)
            2025 R22  Las Vegas GP        (sparse: 2 train years)
  val   — 4 races for early stopping signal diversity:
            2024 R20  Mexico City GP
            2024 R24  Abu Dhabi GP
            2025 R12  British GP
            2025 R18  Singapore GP
  train — all remaining races (~98,000 laps)

Using explicit (Year, RoundNumber) sets avoids accidental boundary-creep
and makes the intended holdouts completely transparent. The test set mixes
5 high-data circuits (≥3 train years) with 1 sparse circuit (Las Vegas,
F1 calendar since 2023) for an honest stable-vs-sparse MAE comparison.

Note on round numbers: the 2024 and 2025 F1 calendars share circuit names
but use different round numbers (e.g. British GP = 2024 R12, 2025 R12;
Belgian GP = 2024 R14, 2025 R13). All round numbers here were verified
against the ingested data.

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

# Explicit (Year, RoundNumber) sets — verified against ingested calendar
TEST_RACES: frozenset[tuple[int, int]] = frozenset({
    (2024, 14),   # Belgian GP
    (2024, 19),   # United States GP
    (2024, 23),   # Qatar GP
    (2025,  7),   # Emilia Romagna GP
    (2025, 15),   # Dutch GP
    (2025, 22),   # Las Vegas GP
})
VAL_RACES: frozenset[tuple[int, int]] = frozenset({
    (2024, 20),   # Mexico City GP
    (2024, 24),   # Abu Dhabi GP
    (2025, 12),   # British GP
    (2025, 18),   # Singapore GP
})


def split_features(src: Path | None = None) -> dict[str, pd.DataFrame]:
    """Load lap_features.parquet and return train/val/test DataFrames."""
    path = src or (_FEATURES_DIR / "lap_features.parquet")
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run build pipeline first")

    df = pd.read_parquet(path)
    logger.info("Loaded %d rows from %s", len(df), path)

    race_key = list(zip(df["Year"], df["RoundNumber"]))
    test_mask  = pd.Series([k in TEST_RACES  for k in race_key], index=df.index)
    val_mask   = pd.Series([k in VAL_RACES   for k in race_key], index=df.index)
    train_mask = ~test_mask & ~val_mask

    train = df[train_mask].copy()
    val   = df[val_mask].copy()
    test  = df[test_mask].copy()

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
