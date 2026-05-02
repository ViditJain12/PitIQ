"""Phase 4.5.2 Part 1 validation — GridRaceEnv skeleton + reset().

Checks:
  - 20-car grid rendered in starting order, all SOFT, all tire_age=1
  - All 20 cars have a style_vector with exactly 11 keys
  - VER overall_pace_rank is consistent with top-driver (lower = faster)
  - ZHO overall_pace_rank is consistent with mid-grid driver
  - All starting_positions are 1-20 with no duplicates
  - All cumulative_race_time == 0 after reset
  - ego car is VER at P1
  - step() raises NotImplementedError

Run:
    python -m pitiq.envs.test_grid_part1
"""

import sys
from pitiq.envs.grid import GridRaceEnv

DRIVERS = [
    "VER", "LEC", "RUS", "SAI", "PER",
    "ALO", "NOR", "PIA", "HAM", "TSU",
    "STR", "MAG", "OCO", "GAS", "ALB",
    "BOT", "HUL", "ZHO", "SAR", "RIC",
]

CONFIG = {
    "circuit":               "Bahrain Grand Prix",
    "year":                  2024,
    "total_laps":            57,
    "ego_driver":            "VER",
    "ego_starting_position": 1,
    "starting_grid":         DRIVERS,
    "starting_compounds":    {d: "SOFT" for d in DRIVERS},
    "weather": {
        "air_temp":  24.0,
        "track_temp": 38.0,
        "humidity":  45.0,
        "is_wet":    False,
    },
    "two_compound_rule_enforced": True,
}


def main() -> None:
    env = GridRaceEnv()
    obs, info = env.reset(options=CONFIG)

    print()
    env.render()
    print()

    failures: list[str] = []

    # ── Check 1: All 20 cars initialised ────────────────────────────────────
    if len(env._grid) != 20:
        failures.append(f"Expected 20 cars, got {len(env._grid)}")

    # ── Check 2: style_vector has exactly 11 keys ───────────────────────────
    for car in env._grid:
        if len(car.style_vector) != 11:
            failures.append(
                f"{car.driver}: style_vector has {len(car.style_vector)} keys, expected 11"
            )

    # ── Check 3: VER overall_pace_rank is low (top driver) ──────────────────
    ver_car = next(c for c in env._grid if c.driver == "VER")
    ver_rank = ver_car.style_vector["overall_pace_rank"]
    zho_car  = next(c for c in env._grid if c.driver == "ZHO")
    zho_rank = zho_car.style_vector["overall_pace_rank"]

    print("── Style vector sanity ─────────────────────────────────────────────")
    print(f"  VER overall_pace_rank : {ver_rank:.3f}  (top driver → lower rank ≈ faster)")
    print(f"  ZHO overall_pace_rank : {zho_rank:.3f}  (mid-grid → higher rank than VER)")

    if ver_rank >= zho_rank:
        failures.append(
            f"VER overall_pace_rank ({ver_rank:.3f}) should be < ZHO ({zho_rank:.3f})"
        )
    print()

    # ── Check 4: starting_position uniqueness ───────────────────────────────
    positions = [c.starting_position for c in env._grid]
    if sorted(positions) != list(range(1, 21)):
        failures.append(f"starting_positions not 1-20 unique: {sorted(positions)}")

    # ── Check 5: all cumulative_race_time == 0 ───────────────────────────────
    non_zero = [c.driver for c in env._grid if c.cumulative_race_time != 0.0]
    if non_zero:
        failures.append(f"Non-zero cumulative_race_time after reset: {non_zero}")

    # ── Check 6: ego reference ───────────────────────────────────────────────
    if env._ego is None or env._ego.driver != "VER":
        failures.append(f"ego not VER: {env._ego}")
    if env._ego and env._ego.current_position != 1:
        failures.append(f"VER ego current_position={env._ego.current_position}, expected 1")

    # ── Check 7: all cars on SOFT tire_age=1 ────────────────────────────────
    wrong_compound = [c.driver for c in env._grid if c.compound != "SOFT"]
    wrong_age      = [c.driver for c in env._grid if c.tire_age != 1]
    if wrong_compound:
        failures.append(f"Cars not on SOFT: {wrong_compound}")
    if wrong_age:
        failures.append(f"Cars with tire_age != 1: {wrong_age}")

    # ── Check 8: step() raises NotImplementedError ──────────────────────────
    try:
        env.step(0)
        failures.append("step() did not raise NotImplementedError")
    except NotImplementedError as e:
        print(f"step() correctly raises NotImplementedError: {e}")
    print()

    # ── Check table ──────────────────────────────────────────────────────────
    print("── Check table ─────────────────────────────────────────────────────")
    print(f"  {'Driver':<6}  {'Pos':>3}  {'Compound':<10}  {'TireAge':>7}  "
          f"{'CumTime':>8}  {'StyleKeys':>9}  {'pace_rank':>9}")
    for car in env._grid:
        print(
            f"  {car.driver:<6}  {car.current_position:>3}  {car.compound:<10}  "
            f"{car.tire_age:>7}  {car.cumulative_race_time:>8.1f}  "
            f"{len(car.style_vector):>9}  {car.style_vector['overall_pace_rank']:>9.3f}"
        )
    print()

    # ── Result ───────────────────────────────────────────────────────────────
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print("All checks passed ✓")


if __name__ == "__main__":
    main()
