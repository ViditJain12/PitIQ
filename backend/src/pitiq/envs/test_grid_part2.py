"""Phase 4.5.2 Part 2 validation — GridRaceEnv full step() implementation.

Runs VER's actual 2024 Bahrain strategy:
  Lap 1-17  : stay on SOFT (action=0)
  Lap 18    : pit → HARD  (action=3)
  Lap 19-57 : stay on HARD (action=0)

Checks:
  - Winner's total race time within ±5% of 5,400s (~90 min)
  - VER finishes in top 10
  - At least 18 of 19 rivals pit at least once
  - Max position changes per driver ≤ 19 (no wrap-around)
  - Race runs all 57 laps without error
  - VER pit history records lap 18 → HARD

Run:
    python -m pitiq.envs.test_grid_part2
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
        "air_temp":   24.0,
        "track_temp": 38.0,
        "humidity":   45.0,
        "is_wet":     False,
    },
    "two_compound_rule_enforced": True,
}

# VER's actual 2024 Bahrain strategy: SOFT stint 1 (laps 1-17), pit lap 18 → HARD
PIT_LAP = 18   # lap number on which VER pits (completed_lap == 18 inside step())


def main() -> None:
    env = GridRaceEnv()
    obs, info = env.reset(options=CONFIG)

    print()
    print("═" * 60)
    print("  GridRaceEnv Part 2 — Full 57-lap Bahrain 2024 validation")
    print("═" * 60)
    print()

    total_reward  = 0.0
    lap_infos: list[dict] = []

    for lap in range(1, 58):
        action = 3 if lap == PIT_LAP else 0  # pit_hard on lap 18, stay otherwise
        obs, reward, terminated, truncated, step_info = env.step(action)
        total_reward += reward
        lap_infos.append({"lap": lap, "reward": reward, **step_info})

        # Print key laps
        if lap in {1, PIT_LAP, PIT_LAP + 1, 30, 50, 57}:
            print(f"--- Lap {lap} (action={'pit_hard' if lap == PIT_LAP else 'stay'}) ---")
            env.render()
            print(f"  reward={reward:+.3f}  cum_reward={total_reward:+.3f}")
            print()

        if terminated:
            break

    # ── Final standings ───────────────────────────────────────────────────────
    print("═" * 60)
    print("  FINAL STANDINGS")
    print("═" * 60)
    final_grid = sorted(env._grid, key=lambda c: c.cumulative_race_time)
    leader_time = final_grid[0].cumulative_race_time

    print(f"  {'Pos':<4} {'Driver':<6} {'Compound':<10} {'TireAge':>7} "
          f"{'RaceTime':>10} {'Gap':>8}  Pit history")
    for rank, car in enumerate(final_grid, start=1):
        gap = car.cumulative_race_time - leader_time
        gap_str = "LEAD" if gap == 0.0 else f"+{gap:.1f}s"
        ego_tag = " ← EGO" if car.driver == "VER" else ""
        pit_str = ", ".join(f"L{ln}→{cmp[0]}" for ln, cmp in car.pit_history) or "no stops"
        print(
            f"  P{rank:<3} {car.driver:<6} {car.compound:<10} {car.tire_age:>7}  "
            f"{car.cumulative_race_time:>10.1f}  {gap_str:>8}  {pit_str}{ego_tag}"
        )

    print()
    print(f"  Total reward accumulated by VER ego: {total_reward:+.2f}")
    print()

    # ── Assertions ────────────────────────────────────────────────────────────
    failures: list[str] = []

    # Check 1: winner race time within ±5% of 5,400s
    TARGET_S   = 5_400.0
    TOLERANCE  = 0.05
    winner_time = leader_time
    if not (TARGET_S * (1 - TOLERANCE) <= winner_time <= TARGET_S * (1 + TOLERANCE)):
        failures.append(
            f"Winner time {winner_time:.1f}s outside ±5% band "
            f"[{TARGET_S*(1-TOLERANCE):.0f}, {TARGET_S*(1+TOLERANCE):.0f}]"
        )

    # Check 2: VER finishes top 10
    ver_car  = next(c for c in env._grid if c.driver == "VER")
    ver_pos  = ver_car.current_position
    if ver_pos > 10:
        failures.append(f"VER finished P{ver_pos} (expected top 10)")

    # Check 3: ≥18 rivals pitted at least once
    rivals_pitted = sum(
        1 for c in env._grid
        if c.driver != "VER" and len(c.pit_history) >= 1
    )
    if rivals_pitted < 18:
        failures.append(
            f"Only {rivals_pitted}/19 rivals pitted at least once (expected ≥18)"
        )

    # Check 4: max position swing ≤ 19 (sanity: no wrap-around)
    for car in env._grid:
        swing = abs(car.current_position - car.starting_position)
        if swing > 19:
            failures.append(
                f"{car.driver} position swing={swing} > 19 (P{car.starting_position}→P{car.current_position})"
            )

    # Check 5: VER pit history records lap 18 → HARD
    expected_pit = [(PIT_LAP, "HARD")]
    if ver_car.pit_history != expected_pit:
        failures.append(
            f"VER pit_history={ver_car.pit_history}, expected {expected_pit}"
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    print("═" * 60)
    print("  CHECK TABLE")
    print("═" * 60)
    checks = [
        (f"Winner time {winner_time:.1f}s within ±5% of 5400s",
         TARGET_S * (1 - TOLERANCE) <= winner_time <= TARGET_S * (1 + TOLERANCE)),
        (f"VER finishes top 10 (P{ver_pos})",              ver_pos <= 10),
        (f"Rivals pitted ≥18 ({rivals_pitted}/19)",         rivals_pitted >= 18),
        ("All position swings ≤ 19",
         not any(abs(c.current_position - c.starting_position) > 19 for c in env._grid)),
        (f"VER pit history = lap 18→HARD",                 ver_car.pit_history == expected_pit),
    ]
    for desc, ok in checks:
        mark = "✓" if ok else "✗"
        print(f"  {mark}  {desc}")

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print("All checks passed ✓")


if __name__ == "__main__":
    main()
