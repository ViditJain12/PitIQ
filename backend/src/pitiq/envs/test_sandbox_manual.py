"""Manual validation for SandboxRaceEnv (Phase 4.1).

Part 1 — Monza 4-strategy test (VER, P1 pole, MEDIUM start):
    Strategy 1 — Optimal 1-stop: MEDIUM → HARD on lap 32  (printed lap-by-lap)
    Strategy 2 — No pit:        MEDIUM all race            (violates two-compound rule)
    Strategy 3 — 2-stop:        MEDIUM → HARD → MEDIUM laps 18 and 40
    Strategy 4 — Wasteful 4-stop: pits every ~11 laps

    Assertions: 1-stop < 4-stop race time, rule-violation flag correct.

Part 2 — 5-circuit polesitter test (2024 season, 1-stop each, pitting at rival median lap):
    Italian GP (Monza, low deg)   — PIA, 53 laps
    Bahrain GP (high deg)          — VER, 57 laps
    Singapore GP (street)          — NOR, 62 laps
    Belgian GP (long lap, high deg)— PER, 44 laps  [2023 used; 2024 in test set]
    Australian GP (mixed)          — SAI, 57 laps

    Assertions per circuit:
    - Race time within ±5% of rival reference time
    - Polesitter on 1-stop finishes P1–P10

CLI:
    python -m pitiq.envs.test_sandbox_manual
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Callable

from pitiq.envs.sandbox import SandboxRaceEnv, load_circuit_rival_profile, rival_reference_time

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)

_TOLERANCE_MONZA   = 0.03   # ±3% for Monza single-circuit checks
_TOLERANCE_MULTI   = 0.05   # ±5% for 5-circuit checks


# ── Strategy runner ────────────────────────────────────────────────────────────

def _run_strategy(
    name: str,
    config: dict,
    pit_fn: Callable[[int, str], int],
    verbose: bool = False,
) -> dict:
    env = SandboxRaceEnv()
    obs, _ = env.reset(options=config)
    n_pits, terminated = 0, False
    last_info: dict = {}
    while not terminated:
        action = pit_fn(env._lap_num, env._compound)
        obs, _, terminated, _, last_info = env.step(action)
        if last_info["pit_this_lap"]:
            n_pits += 1
        if verbose:
            print(env.render())
    env.close()
    return {
        "name":                   name,
        "total_time":             last_info["cumulative_race_time"],
        "final_position":         last_info["position"],
        "n_pits":                 n_pits,
        "two_compound_satisfied": not last_info["violated_two_compound_rule"],
        "violated_rule":          last_info["violated_two_compound_rule"],
    }


def _check(desc: str, passed: bool, detail: str) -> bool:
    status = "PASS ✓" if passed else "FAIL ✗"
    print(f"  [{status}] {desc}")
    print(f"          {detail}")
    return passed


# ── Part 1: Monza 4-strategy test ─────────────────────────────────────────────

_MONZA_CONFIG = {
    "circuit":            "Italian Grand Prix",
    "driver":             "VER",
    "year":               2025,
    "total_laps":         53,
    "starting_position":  1,
    "starting_compound":  "MEDIUM",
    "weather":            {"air_temp": 26, "track_temp": 40, "humidity": 45, "is_wet": False},
    "two_compound_rule_enforced": True,
}


def _monza_part1() -> bool:
    print("=" * 70)
    print("  PART 1 — Monza 4-Strategy Test  (VER, P1, MEDIUM start, 2025)")
    print("=" * 70)

    # Strategy 1: full lap-by-lap log
    print("\n>>> Strategy 1: Optimal 1-stop (MEDIUM → HARD lap 32) — full lap log\n")
    env = SandboxRaceEnv()
    obs, _ = env.reset(options=_MONZA_CONFIG)
    n_pits, terminated, last_info = 0, False, {}
    while not terminated:
        lap, cpd = env._lap_num, env._compound
        action = 3 if (lap == 32 and cpd == "MEDIUM") else 0
        obs, _, terminated, _, last_info = env.step(action)
        if last_info["pit_this_lap"]: n_pits += 1
        print(env.render())
    env.close()
    s1_time = last_info["cumulative_race_time"]
    s1_pos  = last_info["position"]
    s1_rule = not last_info["violated_two_compound_rule"]
    m, s = divmod(s1_time, 60)
    print(f"\n  Total: {int(m)}m {s:.3f}s  | P{s1_pos} | {n_pits} stop(s) | Two-compound: {'OK ✓' if s1_rule else 'VIOL ✗'}")

    strategies = [
        ("Strategy 2: No pit (violates rule)", lambda l, c: 0),
        ("Strategy 3: 2-stop (M→H→M laps 18, 40)",
         lambda l, c: (3 if l == 18 and c == "MEDIUM" else (2 if l == 40 and c == "HARD" else 0))),
        ("Strategy 4: Wasteful 4-stop (laps 10,22,35,46)",
         lambda l, c: {(10,"MEDIUM"):3,(22,"HARD"):2,(35,"MEDIUM"):3,(46,"HARD"):2}.get((l,c),0)),
    ]
    results = [{
        "name": "Strategy 1: 1-stop (M→H lap 32)",
        "total_time": s1_time, "final_position": s1_pos,
        "n_pits": n_pits, "two_compound_satisfied": s1_rule, "violated_rule": not s1_rule,
    }]
    for label, fn in strategies:
        print(f"\n>>> {label}")
        r = _run_strategy(label, _MONZA_CONFIG, fn)
        results.append(r)
        m2, s2 = divmod(r["total_time"], 60)
        print(f"  Total: {int(m2)}m {s2:.3f}s  | P{r['final_position']} | {r['n_pits']} stop(s) | "
              f"Two-compound: {'OK ✓' if r['two_compound_satisfied'] else 'VIOL ✗'}")

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  {'Strategy':<45} {'Time':>12}  {'Pos':>4}  {'Pits':>5}  {'Rule':>8}")
    print("  " + "-" * 68)
    for r in results:
        m2, s2 = divmod(r["total_time"], 60)
        rule_str = "OK ✓" if r["two_compound_satisfied"] else "VIOL ✗"
        print(f"  {r['name']:<45} {int(m2)}m{s2:06.3f}s  P{r['final_position']:<3}  {r['n_pits']:>4}  {rule_str:>8}")

    # Reference from rival profile
    pace_s1, pace_s2, rival_pit = load_circuit_rival_profile(
        _MONZA_CONFIG["circuit"], _MONZA_CONFIG["year"]
    )
    ref = rival_reference_time(_MONZA_CONFIG["circuit"], _MONZA_CONFIG["year"], _MONZA_CONFIG["total_laps"])

    print("\n" + "=" * 70)
    print("  SANITY CHECKS — PART 1")
    print("=" * 70)
    s4_time = results[3]["total_time"]
    checks_passed = True
    checks_passed &= _check(
        "1-stop < 4-stop (pit overhead dominates)",
        s1_time < s4_time,
        f"1-stop {s1_time:.1f}s vs 4-stop {s4_time:.1f}s",
    )
    checks_passed &= _check(
        "No-pit violates two-compound rule",
        results[1]["violated_rule"],
        f"violated={results[1]['violated_rule']}",
    )
    checks_passed &= _check(
        "1-stop satisfies two-compound rule",
        s1_rule,
        f"satisfied={s1_rule}",
    )
    checks_passed &= _check(
        f"1-stop within ±{_TOLERANCE_MONZA*100:.0f}% of rival-baseline reference ({ref:.0f}s)",
        abs(s1_time - ref) / ref <= _TOLERANCE_MONZA,
        f"sim={s1_time:.1f}s  ref={ref:.1f}s  Δ={abs(s1_time-ref)/ref*100:.1f}%",
    )
    checks_passed &= _check(
        "Polesitter (VER) on 1-stop finishes P1–P10",
        s1_pos <= 10,
        f"final_position=P{s1_pos}",
    )
    return checks_passed


# ── Part 2: 5-circuit polesitter test ─────────────────────────────────────────

@dataclass
class CircuitCase:
    circuit: str
    driver:  str
    year:    int
    total_laps: int
    starting_compound: str
    note: str


_CIRCUIT_CASES = [
    CircuitCase("Italian Grand Prix",   "PIA", 2024, 53, "MEDIUM", "Monza — low deg"),
    CircuitCase("Bahrain Grand Prix",   "VER", 2024, 57, "SOFT",   "Bahrain — high deg"),
    CircuitCase("Singapore Grand Prix", "NOR", 2024, 62, "MEDIUM", "Singapore — street"),
    CircuitCase("Belgian Grand Prix",   "PER", 2023, 44, "SOFT",   "Belgian — long lap  [2023; 2024 in test set]"),
    CircuitCase("Australian Grand Prix","SAI", 2024, 57, "MEDIUM", "Australian — mixed"),
]


def _multi_circuit_part2() -> bool:
    print("\n" + "=" * 70)
    print("  PART 2 — 5-Circuit Polesitter Test  (1-stop at rival median pit lap)")
    print("=" * 70)

    all_passed = True
    for case in _CIRCUIT_CASES:
        _, _, median_pit = load_circuit_rival_profile(case.circuit, case.year)
        ref = rival_reference_time(case.circuit, case.year, case.total_laps)

        config = {
            "circuit":           case.circuit,
            "driver":            case.driver,
            "year":              case.year,
            "total_laps":        case.total_laps,
            "starting_position": 1,
            "starting_compound": case.starting_compound,
            "weather":           {},
            "two_compound_rule_enforced": True,
        }

        # Determine pit target compound (opposite of starting)
        pit_action = 2 if case.starting_compound == "SOFT" else 3   # SOFT → MEDIUM, else → HARD

        def make_pit_fn(pit_lap: int, start_cpd: str, action: int) -> Callable[[int, str], int]:
            def fn(lap: int, cpd: str) -> int:
                return action if (lap == pit_lap and cpd == start_cpd) else 0
            return fn

        # Apply a 40% floor so VSC/SC-biased median pit laps don't create unrealistic
        # 40+ lap second stints in validation. The env itself still stores the historical
        # median; this is a test-strategy choice only.
        ego_pit = max(median_pit, int(case.total_laps * 0.40))
        pit_fn = make_pit_fn(ego_pit, case.starting_compound, pit_action)
        r = _run_strategy(f"{case.circuit} {case.year}", config, pit_fn)

        m, s = divmod(r["total_time"], 60)
        delta_pct = abs(r["total_time"] - ref) / ref * 100

        print(f"\n  {case.note}")
        print(f"    Driver: {case.driver}  |  Median pit: {median_pit} → test pit: {ego_pit}  |  Start: {case.starting_compound}")
        print(f"    Rival ref: {ref:.0f}s  |  Sim: {r['total_time']:.1f}s ({int(m)}m{s:06.3f}s)  |  Δ{delta_pct:.1f}%")
        print(f"    Final position: P{r['final_position']}  |  Stops: {r['n_pits']}")

        ok_time = abs(r["total_time"] - ref) / ref <= _TOLERANCE_MULTI
        ok_pos  = r["final_position"] <= 10

        if not ok_time:
            print(f"    [FAIL ✗] Race time outside ±{_TOLERANCE_MULTI*100:.0f}% of reference")
            all_passed = False
        if not ok_pos:
            print(f"    [FAIL ✗] Finished P{r['final_position']} — outside top 10")
            all_passed = False
        if ok_time and ok_pos:
            print(f"    [PASS ✓] Within ±{_TOLERANCE_MULTI*100:.0f}% of reference  |  P{r['final_position']} (top-10)")

    return all_passed


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    part1_ok = _monza_part1()
    part2_ok = _multi_circuit_part2()

    print("\n" + "=" * 70)
    if part1_ok and part2_ok:
        print("  ALL CHECKS PASSED ✓")
    else:
        print("  SOME CHECKS FAILED ✗ — review output above")
        sys.exit(1)


if __name__ == "__main__":
    main()
