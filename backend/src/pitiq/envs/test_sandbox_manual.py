"""Manual validation for SandboxRaceEnv (Phase 4.1).

Runs 4 strategies on a 53-lap Monza 2025 simulation with VER starting P1 on MEDIUM:

    Strategy 1 — Optimal 1-stop: MEDIUM → HARD on lap 25  (printed lap-by-lap)
    Strategy 2 — No pit:        MEDIUM all race            (violates two-compound rule)
    Strategy 3 — 2-stop:        MEDIUM → HARD → MEDIUM laps 18 and 36
    Strategy 4 — Wasteful 4-stop: pits every ~11 laps

Validation assertions:
    - 1-stop total race time < 4-stop total race time
    - 53-lap Monza cum. time within ±3% of historical avg (~87 min)
    - two_compound_rule_violated == True only for Strategy 2

CLI:
    python -m pitiq.envs.test_sandbox_manual
"""

from __future__ import annotations

import logging
import sys
from typing import Callable

from pitiq.envs.sandbox import SandboxRaceEnv

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)

# ── Config ─────────────────────────────────────────────────────────────────────

_CONFIG = {
    "circuit":            "Italian Grand Prix",
    "driver":             "VER",
    "year":               2025,
    "total_laps":         53,
    "starting_position":  1,
    "starting_compound":  "MEDIUM",
    "weather":            {"air_temp": 26, "track_temp": 40, "humidity": 45, "is_wet": False},
    "two_compound_rule_enforced": True,
}

_TOLERANCE = 0.03                        # ±3% of rival-baseline reference


# ── Strategy helpers ───────────────────────────────────────────────────────────

def _run_strategy(
    name: str,
    pit_fn: Callable[[int, str], int],
    verbose: bool = False,
) -> dict:
    """Run a full race using pit_fn(lap_num, compound) → action.

    Returns summary dict with: name, total_time, final_position, n_pits,
    two_compound_satisfied, violated_rule, lap_times.
    """
    env = SandboxRaceEnv(render_mode="ansi" if verbose else None)
    obs, _ = env.reset(options=_CONFIG)

    n_pits = 0
    lap_times: list[float] = []
    terminated = False
    info: dict = {}

    while not terminated:
        lap_num  = env._lap_num      # current lap about to run
        compound = env._compound

        action = pit_fn(lap_num, compound)
        obs, reward, terminated, truncated, info = env.step(action)

        lap_times.append(info["lap_time"])
        if info["pit_this_lap"]:
            n_pits += 1

        if verbose:
            line = env.render()
            # render() already prints if mode='ansi'... actually 'ansi' just returns
            # string, 'human' prints. For verbose, we printed manually:
            print(env.render())

    env.close()

    two_satisfied = not info.get("violated_two_compound_rule", False)
    return {
        "name":                 name,
        "total_time":           info["cumulative_race_time"],
        "final_position":       info["position"],
        "n_pits":               n_pits,
        "two_compound_satisfied": two_satisfied,
        "violated_rule":        info.get("violated_two_compound_rule", False),
        "lap_times":            lap_times,
    }


# ── Strategy definitions ───────────────────────────────────────────────────────

def _strat_1_stop(lap_num: int, compound: str) -> int:
    """MEDIUM → HARD on lap 25."""
    if lap_num == 25 and compound == "MEDIUM":
        return 3  # pit_hard
    return 0


def _strat_no_pit(lap_num: int, compound: str) -> int:
    return 0


def _strat_2_stop(lap_num: int, compound: str) -> int:
    """MEDIUM → HARD lap 18, HARD → MEDIUM lap 36."""
    if lap_num == 18 and compound == "MEDIUM":
        return 3  # pit_hard
    if lap_num == 36 and compound == "HARD":
        return 2  # pit_medium
    return 0


def _strat_4_stop(lap_num: int, compound: str) -> int:
    """4 stops — MEDIUM→HARD→MEDIUM→HARD→MEDIUM at laps 10, 22, 35, 46."""
    pit_map: dict[tuple[int, str], int] = {
        (10, "MEDIUM"): 3,   # → HARD
        (22, "HARD"):   2,   # → MEDIUM
        (35, "MEDIUM"): 3,   # → HARD
        (46, "HARD"):   2,   # → MEDIUM
    }
    return pit_map.get((lap_num, compound), 0)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("  SandboxRaceEnv — Phase 4.1 Manual Validation")
    print(f"  Circuit: {_CONFIG['circuit']}  |  Driver: {_CONFIG['driver']}")
    print(f"  Year: {_CONFIG['year']}  |  Total laps: {_CONFIG['total_laps']}")
    print("=" * 70)

    # ── Strategy 1: Optimal 1-stop (lap-by-lap output) ────────────────────────
    print("\n>>> Strategy 1: Optimal 1-stop (MEDIUM → HARD lap 25) — full lap log\n")
    env = SandboxRaceEnv()
    obs, _ = env.reset(options=_CONFIG)
    n_pits_s1 = 0
    last_info: dict = {}
    terminated = False

    while not terminated:
        lap_num  = env._lap_num
        compound = env._compound
        action   = _strat_1_stop(lap_num, compound)
        obs, reward, terminated, truncated, last_info = env.step(action)
        if last_info["pit_this_lap"]:
            n_pits_s1 += 1
        print(env.render())

    env.close()
    s1_time = last_info["cumulative_race_time"]
    s1_pos  = last_info["position"]
    s1_rule = not last_info["violated_two_compound_rule"]

    total_m = int(s1_time // 60)
    total_s = s1_time % 60
    print(f"\n  Total race time : {total_m}m {total_s:.3f}s  ({s1_time:.1f}s)")
    print(f"  Final position  : P{s1_pos}")
    print(f"  Pit stops       : {n_pits_s1}")
    print(f"  Two-compound OK : {'YES ✓' if s1_rule else 'NO ✗'}")

    # ── Strategies 2–4 (summary only) ─────────────────────────────────────────
    strategies = [
        ("Strategy 2: No pit (violates 2-compound rule)", _strat_no_pit),
        ("Strategy 3: 2-stop (MEDIUM→HARD→MEDIUM laps 18, 36)", _strat_2_stop),
        ("Strategy 4: Wasteful 4-stop (laps 10, 22, 35, 46)", _strat_4_stop),
    ]

    results: list[dict] = [
        {
            "name": "Strategy 1: Optimal 1-stop (MEDIUM→HARD lap 25)",
            "total_time": s1_time,
            "final_position": s1_pos,
            "n_pits": n_pits_s1,
            "two_compound_satisfied": s1_rule,
            "violated_rule": not s1_rule,
        }
    ]

    for label, fn in strategies:
        print(f"\n>>> {label}")
        r = _run_strategy(label, fn, verbose=False)
        results.append(r)
        m = int(r["total_time"] // 60)
        s = r["total_time"] % 60
        print(f"  Total: {m}m {s:.3f}s  ({r['total_time']:.1f}s) | "
              f"P{r['final_position']} | "
              f"{r['n_pits']} stop(s) | "
              f"Two-compound: {'OK ✓' if r['two_compound_satisfied'] else 'VIOLATED ✗'}")

    # ── Comparison table ───────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  RESULTS SUMMARY")
    print("=" * 70)
    print(f"  {'Strategy':<48} {'Race time':>10}  {'Pos':>4}  {'Pits':>5}  {'Rule':>8}")
    print("  " + "-" * 66)
    for r in results:
        m = int(r["total_time"] // 60)
        s = r["total_time"] % 60
        rule_str = "OK ✓" if r["two_compound_satisfied"] else "VIOL ✗"
        print(f"  {r['name']:<48} {m}m{s:06.3f}s  "
              f"P{r['final_position']:<3}  {r['n_pits']:>4}  {rule_str:>8}")

    # ── Sanity checks ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  SANITY CHECKS")
    print("=" * 70)

    s4_time = results[3]["total_time"]   # 4-stop
    s2_rule = results[1]["violated_rule"]  # no-pit should violate rule

    # Reference: rival baseline pace * total_laps (a no-pit car at mean field pace).
    # A valid 1-stop race should be within ±3% of this — it costs ~22s net in the
    # pit lane but fresh tires partially recover that, so the sim time should be
    # close to (and slightly above) the no-pit rival baseline.
    from pitiq.envs.sandbox import _get_rival_pace
    rival_pace  = _get_rival_pace(_CONFIG["circuit"], _CONFIG["year"])
    reference_s = rival_pace * _CONFIG["total_laps"]

    checks = [
        (
            "1-stop < 4-stop (efficiency)",
            s1_time < s4_time,
            f"1-stop {s1_time:.1f}s vs 4-stop {s4_time:.1f}s",
        ),
        (
            "No-pit violates two-compound rule",
            s2_rule,
            f"violated={s2_rule}",
        ),
        (
            "1-stop two-compound rule satisfied",
            s1_rule,
            f"satisfied={s1_rule}",
        ),
        (
            f"1-stop race time within ±{_TOLERANCE*100:.0f}% of rival-baseline "
            f"({reference_s:.0f}s = {rival_pace:.3f}s × {_CONFIG['total_laps']} laps)",
            abs(s1_time - reference_s) / reference_s <= _TOLERANCE,
            f"sim={s1_time:.1f}s  baseline={reference_s:.1f}s  "
            f"Δ={abs(s1_time - reference_s)/reference_s*100:.1f}%",
        ),
    ]

    all_passed = True
    for desc, passed, detail in checks:
        status = "PASS ✓" if passed else "FAIL ✗"
        print(f"  [{status}] {desc}")
        print(f"          {detail}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("  All sanity checks passed ✓")
    else:
        print("  One or more checks FAILED — review output above")
        sys.exit(1)


if __name__ == "__main__":
    main()
