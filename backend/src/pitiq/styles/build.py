"""Driver style fingerprinting — per-driver style vectors across 5 seasons.

Features per driver (one row per driver in driver_styles.parquet):
  pace_trend_{soft,medium,hard}    — OLS slope (s/lap of tire age), stint-1 green-flag laps,
                                     tire_age >= 5 to skip warm-up.
                                     NOTE: measures NET pace change = tire degradation MINUS
                                     track evolution (rubber build-up). In stint 1 the track
                                     is still coming in, so track evolution often outweighs
                                     tire wear, producing negative slopes. This is expected
                                     and physically correct. The relative ordering between
                                     drivers remains a valid style signal (a driver with a
                                     less-negative slope manages tires better OR races on
                                     circuits with weaker track evolution).
  cornering_aggression             — avg tel_brake_pct across all accurate laps
  throttle_smoothness              — 1 / std(tel_throttle_pct); higher = smoother
  wet_skill_delta                  — driver median on INT/WET vs grid-wide median (negative =
                                     faster); NaN if driver has < MIN_WET_LAPS wet-compound laps
  tire_saving_coef                 — median(early-stint avg / late-stint avg) per stint;
                                     > 1.0 means driver paces slower early = tire saving
  sector_profile_s1/s2/s3         — avg lap rank (1=best, 20=worst) per sector, green-flag laps

CLI:
    python -m pitiq.styles.build
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

logger = logging.getLogger(__name__)

_REPO_ROOT    = Path(__file__).parents[4]
_FEATURES_DIR = _REPO_ROOT / "data" / "features"

MIN_DRIVER_LAPS  = 500
MIN_DEG_LAPS     = 20   # min laps per (driver, compound) for pace_trend regression
MIN_WET_LAPS     = 20   # min wet-compound laps for wet_skill_delta; below = NaN
DEG_MIN_TIRE_AGE = 5    # skip warm-up laps in pace_trend regression
DRY_COMPOUNDS    = ["SOFT", "MEDIUM", "HARD"]
WET_COMPOUNDS    = ["INTERMEDIATE", "WET"]
GREEN_STATUS     = "1"  # FastF1 TrackStatus for green flag


def _load_features() -> pd.DataFrame:
    path = _FEATURES_DIR / "lap_features.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run build pipeline first")
    df = pd.read_parquet(path)
    df = df[~df["Compound"].isin(["None", "nan"])].copy()
    logger.info("Loaded %d rows", len(df))
    return df


def _qualified_drivers(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    counts = df["Driver"].value_counts()
    qualified = counts[counts >= MIN_DRIVER_LAPS].index.tolist()
    excluded  = counts[counts <  MIN_DRIVER_LAPS].index.tolist()
    logger.info(
        "%d drivers qualify (>=%d laps); excluded: %s",
        len(qualified), MIN_DRIVER_LAPS, excluded or "none",
    )
    return qualified, excluded


def _pace_trends(df: pd.DataFrame, drivers: list[str]) -> pd.DataFrame:
    """OLS slope of LapTimeCorrected vs tire_age per driver per compound.

    Columns: pace_trend_{soft,medium,hard}

    The slope measures net pace change per lap of tire age in a controlled window
    (stint 1, green flag, tire_age >= DEG_MIN_TIRE_AGE). Negative values are common
    because track evolution (rubber build-up) often outpaces tire degradation in
    early stints. Driver-to-driver differences in slope remain meaningful as a
    style signal even when absolute signs are negative.
    """
    sub = df[
        (df["Stint"] == 1) &
        (df["TrackStatus"] == GREEN_STATUS) &
        (df["tire_age"] >= DEG_MIN_TIRE_AGE) &
        df["LapTimeCorrected"].notna() &
        df["tire_age"].notna()
    ]

    records = []
    for driver in drivers:
        row: dict = {"Driver": driver}
        d = sub[sub["Driver"] == driver]
        for compound in DRY_COMPOUNDS:
            col = f"pace_trend_{compound.lower()}"
            c = d[d["Compound"] == compound]
            if len(c) < MIN_DEG_LAPS:
                row[col] = np.nan
                continue
            x = c["tire_age"].values.reshape(-1, 1)
            y = c["LapTimeCorrected"].values
            row[col] = float(LinearRegression().fit(x, y).coef_[0])
        records.append(row)

    return pd.DataFrame(records).set_index("Driver")


def _telemetry_features(df: pd.DataFrame, drivers: list[str]) -> pd.DataFrame:
    """cornering_aggression and throttle_smoothness from telemetry summary columns."""
    sub = df[df["tel_throttle_pct"].notna() & df["tel_brake_pct"].notna()]
    records = []
    for driver in drivers:
        d = sub[sub["Driver"] == driver]
        aggression = float(d["tel_brake_pct"].mean())
        std_t = d["tel_throttle_pct"].std()
        smoothness = float(1.0 / std_t) if std_t > 0 else np.nan
        records.append({
            "Driver": driver,
            "cornering_aggression": aggression,
            "throttle_smoothness":  smoothness,
        })
    return pd.DataFrame(records).set_index("Driver")


def _wet_skill_delta(
    df: pd.DataFrame,
    drivers: list[str],
) -> tuple[pd.DataFrame, list[str]]:
    """Race-normalised wet skill: median of per-lap deviations from same-race/same-compound median.

    Using a global grid median as the baseline conflates circuit speed with driver skill —
    São Paulo INT laps (~83s) vs Belgian INT laps (~120s) differ by 37s, so a driver whose
    wet laps happen to be concentrated at fast circuits will look artificially skilled.
    Race-normalisation removes that circuit-mix confound entirely: each lap is compared
    only to other drivers on the same compound at the same race.

    Negative = driver is faster than race peers in wet conditions.
    Drivers with fewer than MIN_WET_LAPS wet-compound laps receive NaN.
    Returns (DataFrame, list_of_nulled_drivers_with_reasons).
    """
    wet = df[df["Compound"].isin(WET_COMPOUNDS) & df["LapTimeCorrected"].notna()].copy()

    # Per-lap deviation from same-race, same-compound median
    wet["_race_median"] = wet.groupby(["Year", "RoundNumber", "Compound"])[
        "LapTimeCorrected"
    ].transform("median")
    wet["_lap_delta"] = wet["LapTimeCorrected"] - wet["_race_median"]

    records = []
    nulled: list[str] = []
    for driver in drivers:
        d_wet = wet[wet["Driver"] == driver]
        n = len(d_wet)
        if n < MIN_WET_LAPS:
            records.append({"Driver": driver, "wet_skill_delta": np.nan})
            nulled.append(
                f"{driver}: {n} wet lap{'s' if n != 1 else ''} (< {MIN_WET_LAPS} minimum) → NaN"
            )
        else:
            delta = float(d_wet["_lap_delta"].median())
            records.append({"Driver": driver, "wet_skill_delta": delta})

    return pd.DataFrame(records).set_index("Driver"), nulled


def _tire_saving_coef(df: pd.DataFrame, drivers: list[str]) -> pd.DataFrame:
    """Median of (early-stint avg / late-stint avg) per driver across all stints.

    Early = tire_age 3–6 (post warm-up), late = 3 highest tire_age laps in that stint.
    > 1.0 means driver paced slower early relative to late → tire saving behaviour.
    Low cross-driver variance is expected; Phase 3 feature importance will confirm utility.
    """
    sub = df[
        (df["TrackStatus"] == GREEN_STATUS) &
        df["LapTimeCorrected"].notna() &
        df["tire_age"].notna() &
        df["Stint"].notna()
    ].copy()

    stint_cols = ["Driver", "Year", "RoundNumber", "Stint"]

    sub["_early"] = sub["tire_age"].between(3, 6)
    sub["_age_rank_desc"] = sub.groupby(stint_cols)["tire_age"].rank(
        method="min", ascending=False
    )
    sub["_late"] = sub["_age_rank_desc"] <= 3

    early_avg = (sub[sub["_early"]]
                   .groupby(stint_cols)["LapTimeCorrected"]
                   .mean()
                   .rename("early_avg"))
    late_avg  = (sub[sub["_late"]]
                   .groupby(stint_cols)["LapTimeCorrected"]
                   .mean()
                   .rename("late_avg"))

    stints = early_avg.to_frame().join(late_avg, how="inner")
    stints["ratio"] = stints["early_avg"] / stints["late_avg"]

    coefs = stints["ratio"].groupby(level="Driver").median()
    return pd.DataFrame(
        {"tire_saving_coef": coefs.reindex(drivers)},
        index=pd.Index(drivers, name="Driver"),
    )


def _sector_profile(df: pd.DataFrame, drivers: list[str]) -> pd.DataFrame:
    """Avg rank (1=best, N=worst) per sector, computed per (Year, RoundNumber, LapNumber)."""
    green = df[df["TrackStatus"] == GREEN_STATUS].copy()

    for s in [1, 2, 3]:
        green[f"_s{s}_rank"] = (
            green.groupby(["Year", "RoundNumber", "LapNumber"])[f"Sector{s}Time"]
                 .rank(method="min")
        )

    avg_ranks = (
        green.groupby("Driver")[["_s1_rank", "_s2_rank", "_s3_rank"]]
             .mean()
             .rename(columns={
                 "_s1_rank": "sector_profile_s1",
                 "_s2_rank": "sector_profile_s2",
                 "_s3_rank": "sector_profile_s3",
             })
    )
    return avg_ranks.reindex(drivers)


def build_driver_styles() -> tuple[pd.DataFrame, list[str], list[str]]:
    """Load features, compute all style vectors.

    Returns (styles_df, excluded_drivers, wet_nulled_messages).
    """
    df = _load_features()
    drivers, excluded = _qualified_drivers(df)

    logger.info("Computing pace trends...")
    trends = _pace_trends(df, drivers)

    logger.info("Computing telemetry features...")
    tel = _telemetry_features(df, drivers)

    logger.info("Computing wet skill deltas...")
    wet, wet_nulled = _wet_skill_delta(df, drivers)

    logger.info("Computing tire saving coefficients...")
    tsc = _tire_saving_coef(df, drivers)

    logger.info("Computing sector profiles...")
    sec = _sector_profile(df, drivers)

    styles = trends.join(tel).join(wet).join(tsc).join(sec)
    styles.index.name = "Driver"
    logger.info(
        "Style vectors assembled: %d drivers × %d features", len(styles), len(styles.columns)
    )
    return styles, excluded, wet_nulled


def save_driver_styles(styles: pd.DataFrame) -> None:
    _FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    out = _FEATURES_DIR / "driver_styles.parquet"
    styles.to_parquet(out)
    logger.info("Saved %d driver style vectors → %s", len(styles), out)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compute per-driver style feature vectors.")
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

    styles, excluded, wet_nulled = build_driver_styles()
    save_driver_styles(styles)

    print(f"\nDriver style vectors computed: {len(styles)} drivers")
    if excluded:
        print(f"Excluded (< {MIN_DRIVER_LAPS} laps): {', '.join(excluded)}")

    if wet_nulled:
        print(f"\nwet_skill_delta nulled (< {MIN_WET_LAPS} wet laps):")
        for msg in wet_nulled:
            print(f"  {msg}")

    nan_counts = styles.isna().sum()
    nan_counts = nan_counts[nan_counts > 0]
    print("\nFeature NaN counts:")
    if nan_counts.empty:
        print("  None — all features fully populated ✓")
    else:
        for col, n in nan_counts.items():
            pct = n / len(styles) * 100
            print(f"  {col:<30}  {n:>3} / {len(styles)}  ({pct:.0f}%)")

    print("\nStyle vector sample (5 drivers):")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 140)
    pd.set_option("display.float_format", "{:.4f}".format)
    print(styles.head())


if __name__ == "__main__":
    main()
