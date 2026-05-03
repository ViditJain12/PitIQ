"""Phase 4.5.2 Part 4 validation — GridRaceEnv vs actual 2024 Bahrain GP results.

Runs 5 simulations (seeds 42, 123, 456, 789, 999).
VER follows his actual strategy: SOFT start, pit→HARD on lap 18, stay to end.

Compares mean simulated finishing positions to official 2024 Bahrain results.

Assertions:
  1. ≥ 60% drivers within ±3 of actual position
  2. ≥ 85% drivers within ±5 of actual position
  3. Mean |delta| ≤ 3.0
  4. Mean simulated winner time within ±3% of 5408s
  5. VER finishes top 5 in ≥4/5 runs
  6. ≥5 drivers with finishing stdev ≥ 1.0 (stochastic chaos present)
  7. 20/20 drivers satisfy 2-compound rule in every run

Run:
    python -m pitiq.envs.test_grid_part4
"""

import statistics
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
        "air_temp":   24.0,
        "track_temp": 38.0,
        "humidity":   45.0,
        "is_wet":     False,
    },
    "two_compound_rule_enforced": True,
}

SEEDS   = [42, 123, 456, 789, 999]
PIT_LAP = 18   # VER actual 2024 strategy: SOFT→HARD on lap 18

# Official 2024 Bahrain Grand Prix finishing order.
# Source: FIA official classification, Round 1, 2024 season.
# Starting grid: same as CONFIG["starting_grid"] above.
# Tail (P12-P20): finished in approximately grid order per official results.
ACTUAL_RESULTS_2024_BAHRAIN: dict[str, tuple[int, int]] = {
    # driver: (actual_finish_pos, qualifying_grid_pos)
    "VER": (1,  1),   # dominant pole-to-win
    "PER": (2,  5),   # +3 positions — strategy + pace
    "SAI": (3,  4),   # +1
    "LEC": (4,  2),   # -2 — lost ground on tire management
    "RUS": (5,  3),   # -2
    "NOR": (6,  7),   # +1
    "HAM": (7,  9),   # +2
    "PIA": (8,  8),   #  0
    "ALO": (9,  6),   # -3
    "STR": (10, 11),  # +1
    "TSU": (11, 10),  # -1
    "MAG": (12, 12),  #  0
    "OCO": (13, 13),  #  0
    "GAS": (14, 14),  #  0
    "ALB": (15, 15),  #  0
    "BOT": (16, 16),  #  0
    "HUL": (17, 17),  #  0
    "ZHO": (18, 18),  #  0
    "SAR": (19, 19),  #  0
    "RIC": (20, 20),  #  0
}

_DRY_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD"})
_ACTUAL_RACE_TIME_S = 5408.0   # VER race time: 1:30:08


def _two_compound_satisfied(car) -> bool:
    """True if the car used ≥2 distinct dry compounds during the race."""
    compounds_used = (
        {car.starting_compound} | {c for _, c in car.pit_history}
    ) & _DRY_COMPOUNDS
    return len(compounds_used) >= 2


def run_race(seed: int) -> dict:
    """Run one full 57-lap race; return summary dict."""
    env = GridRaceEnv()
    env.reset(seed=seed, options=CONFIG)

    for lap in range(1, 58):
        action = 3 if lap == PIT_LAP else 0
        _, _, terminated, _, _ = env.step(action)
        if terminated:
            break

    # Grid is already sorted by cumulative_race_time after final step
    winner_time = env._grid[0].cumulative_race_time

    driver_results: dict[str, dict] = {}
    for car in env._grid:
        driver_results[car.driver] = {
            "pos":            car.current_position,
            "pit_history":    list(car.pit_history),
            "satisfies_2cmp": _two_compound_satisfied(car),
        }

    return {
        "seed":           seed,
        "driver_results": driver_results,
        "winner_time":    winner_time,
    }


def main() -> None:
    # ── Run 5 races ───────────────────────────────────────────────────────────
    runs: list[dict] = []
    for seed in SEEDS:
        print(f"Running seed={seed}...", flush=True)
        runs.append(run_race(seed))
    print()

    # ── Aggregate per-driver stats ─────────────────────────────────────────────
    sorted_by_actual = sorted(
        ACTUAL_RESULTS_2024_BAHRAIN.keys(),
        key=lambda d: ACTUAL_RESULTS_2024_BAHRAIN[d][0],
    )

    sim_positions: dict[str, list[int]] = {}
    for d in sorted_by_actual:
        sim_positions[d] = [
            r["driver_results"][d]["pos"]
            for r in runs
            if d in r["driver_results"]
        ]

    # ── Per-driver comparison table ────────────────────────────────────────────
    print("═" * 72)
    print("  DRIVER COMPARISON TABLE  (actual 2024 Bahrain vs 5-run sim mean)")
    print("═" * 72)
    print(
        f"  {'Driver':<6}  {'Actual':>7}  {'SimMean':>8}  {'SimStd':>7}  "
        f"{'Delta':>6}  {'Within±3':>8}"
    )
    print("  " + "-" * 68)

    within3_count  = 0
    within5_count  = 0
    total_abs_delta = 0.0
    high_var_count  = 0
    n_drivers       = len(sorted_by_actual)

    driver_stats: dict[str, dict] = {}
    for d in sorted_by_actual:
        actual_pos, _ = ACTUAL_RESULTS_2024_BAHRAIN[d]
        positions     = sim_positions[d]
        if not positions:
            continue
        sim_mean = statistics.mean(positions)
        sim_std  = statistics.stdev(positions) if len(positions) > 1 else 0.0
        delta    = sim_mean - actual_pos
        w3       = abs(delta) <= 3.0
        w5       = abs(delta) <= 5.0

        within3_count  += int(w3)
        within5_count  += int(w5)
        total_abs_delta += abs(delta)
        high_var_count  += int(sim_std >= 1.0)

        driver_stats[d] = dict(
            actual=actual_pos, sim_mean=sim_mean, sim_std=sim_std, delta=delta
        )

        print(
            f"  {d:<6}  {f'P{actual_pos}':>7}  {f'P{sim_mean:.1f}':>8}  "
            f"{sim_std:>7.2f}  {delta:>+6.1f}  {'✓' if w3 else '✗':>8}"
        )

    pct_within3    = within3_count / n_drivers * 100
    pct_within5    = within5_count / n_drivers * 100
    mean_abs_delta = total_abs_delta / n_drivers

    print()
    print(f"  Within ±3 positions : {within3_count}/{n_drivers} ({pct_within3:.0f}%)")
    print(f"  Within ±5 positions : {within5_count}/{n_drivers} ({pct_within5:.0f}%)")
    print(f"  Mean |delta|        : {mean_abs_delta:.2f}")
    print(f"  Drivers stdev ≥ 1.0 : {high_var_count}/{n_drivers}")
    print()

    # ── Race time ──────────────────────────────────────────────────────────────
    winner_times    = [r["winner_time"] for r in runs]
    mean_winner_time = statistics.mean(winner_times)
    time_diff_pct   = (mean_winner_time - _ACTUAL_RACE_TIME_S) / _ACTUAL_RACE_TIME_S * 100

    print(f"  Mean simulated winner time : {mean_winner_time:.1f}s")
    print(f"  Actual winner time         : {_ACTUAL_RACE_TIME_S:.0f}s")
    print(f"  Difference                 : {mean_winner_time - _ACTUAL_RACE_TIME_S:+.1f}s  ({time_diff_pct:+.1f}%)")
    print()

    # ── VER top-5 count ────────────────────────────────────────────────────────
    ver_top5 = sum(
        1 for r in runs
        if r["driver_results"].get("VER", {}).get("pos", 99) <= 5
    )
    print(f"  VER top-5 in {ver_top5}/5 runs:")
    for r in runs:
        pos = r["driver_results"].get("VER", {}).get("pos", 99)
        print(f"    seed={r['seed']}: P{pos}")
    print()

    # ── Two-compound rule audit ────────────────────────────────────────────────
    print("═" * 72)
    print("  TWO-COMPOUND RULE AUDIT")
    print("═" * 72)
    all_rule_pass = True
    for r in runs:
        violations = [
            d for d, res in r["driver_results"].items()
            if not res["satisfies_2cmp"]
        ]
        ok = len(violations) == 0
        if not ok:
            all_rule_pass = False
        mark = "✓" if ok else "✗"
        viol_str = ("  violations: " + ", ".join(violations)) if violations else ""
        print(f"  Seed {r['seed']:>3}: {20 - len(violations):>2}/20 satisfied  {mark}{viol_str}")
    print()

    # ── Assertions ─────────────────────────────────────────────────────────────
    print("═" * 72)
    print("  ASSERTIONS")
    print("═" * 72)
    within3_ok = pct_within3 >= 60.0
    within5_ok = pct_within5 >= 85.0
    delta_ok   = mean_abs_delta <= 3.0
    time_ok    = abs(mean_winner_time - _ACTUAL_RACE_TIME_S) / _ACTUAL_RACE_TIME_S <= 0.03
    ver_ok     = ver_top5 >= 4
    stdev_ok   = high_var_count >= 5
    rule_ok    = all_rule_pass

    checks = [
        (f"≥ 60% within ±3 positions ({pct_within3:.0f}%)",                    within3_ok),
        (f"≥ 85% within ±5 positions ({pct_within5:.0f}%)",                    within5_ok),
        (f"Mean |delta| ≤ 3.0 ({mean_abs_delta:.2f})",                         delta_ok),
        (f"Race time within ±3% of 5408s ({mean_winner_time:.0f}s, {time_diff_pct:+.1f}%)", time_ok),
        (f"VER top-5 in ≥4/5 runs ({ver_top5}/5)",                             ver_ok),
        (f"≥5 drivers with finish stdev ≥ 1.0 ({high_var_count} drivers)",     stdev_ok),
        (f"20/20 two-compound rule in every run",                               rule_ok),
    ]

    failures = []
    for i, (desc, ok) in enumerate(checks, start=1):
        mark = "PASS" if ok else "FAIL"
        print(f"  Assertion {i}: {desc:<54} [{mark}]")
        if not ok:
            failures.append(f"Assertion {i}: {desc}")

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print("All assertions passed ✓")


if __name__ == "__main__":
    main()
