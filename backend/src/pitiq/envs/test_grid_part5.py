"""Phase 4.5.3 validation — rival-aware 25-dim observation space.

Race 1: VER ego at P1, 2024 Bahrain, seed=42.
  VER follows actual strategy: SOFT start, pit→HARD lap 18.
  Prints labeled 25-dim obs at laps 1, 10, 17, 19, 30, 56.

Race 2: PER ego at P5, same config, seed=42.
  At lap 5 — verifies rival lookup works for non-P1 starting positions.

Run:
    python -m pitiq.envs.test_grid_part5
"""

import sys
import numpy as np
from pitiq.envs.grid import GridRaceEnv, _COMPOUNDS_ORDER, _COMPOUND_IDX

DRIVERS = [
    "VER", "LEC", "RUS", "SAI", "PER",
    "ALO", "NOR", "PIA", "HAM", "TSU",
    "STR", "MAG", "OCO", "GAS", "ALB",
    "BOT", "HUL", "ZHO", "SAR", "RIC",
]

CONFIG_VER = {
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

CONFIG_PER = {**CONFIG_VER, "ego_driver": "PER", "ego_starting_position": 5}

PIT_LAP = 18   # VER hardcoded: SOFT→HARD on lap 18

# Obs field labels (25 dims)
OBS_LABELS = [
    "lap_fraction",                  # [0]
    "cmp_SOFT",                      # [1]
    "cmp_MEDIUM",                    # [2]
    "cmp_HARD",                      # [3]
    "cmp_INT",                       # [4]
    "cmp_WET",                       # [5]
    "tire_age",                      # [6]
    "stint_number",                  # [7]
    "fuel_estimate_kg",              # [8]
    "position",                      # [9]
    "laps_remaining",                # [10]
    "laps_past_cliff",               # [11]
    "has_2nd_compound",              # [12]
    "gap_to_rival_ahead_s",          # [13]
    "rival_ahead_cmp_idx",           # [14]
    "rival_ahead_tire_age",          # [15]
    "rival_ahead_pace_rank",         # [16]
    "rival_ahead_tire_save",         # [17]
    "gap_to_rival_behind_s",         # [18]
    "rival_behind_cmp_idx",          # [19]
    "rival_behind_tire_age",         # [20]
    "rival_behind_pace_rank",        # [21]
    "rival_behind_tire_save",        # [22]
    "undercut_window_open",          # [23]
    "defending_against_undercut",    # [24]
]

_IDX_TO_COMPOUND = {v: k for k, v in _COMPOUND_IDX.items()}


def _rival_car(env: GridRaceEnv, pos: int):
    pos_map = {car.current_position: car for car in env._grid}
    return pos_map.get(pos)


def print_obs(env: GridRaceEnv, obs: np.ndarray, lap: int, ego_driver: str) -> None:
    """Print a labeled 25-dim observation with rival context narrative."""
    ego = next(c for c in env._grid if c.driver == ego_driver)
    rival_ahead  = _rival_car(env, ego.current_position - 1)
    rival_behind = _rival_car(env, ego.current_position + 1)

    # Decode compound from one-hot
    cmp_oh  = obs[1:6]
    cmp_idx = int(np.argmax(cmp_oh))
    ego_cmp = _IDX_TO_COMPOUND.get(cmp_idx, "?")

    print(f"{'═'*62}")
    print(f"  LAP {lap} — obs after completing lap {lap}  (entering lap {lap+1})")
    print(f"{'═'*62}")
    print(
        f"  Ego: {ego.driver}  P{ego.current_position}  "
        f"{ego_cmp}  age {ego.tire_age}  "
        f"fuel {ego.fuel_estimate_kg:.1f}kg  "
        f"laps_remaining {int(obs[10])}"
    )
    print()

    # Dims 0-12: ego state
    print("  ── dims [0-12] ego state ───────────────────────────���──────")
    for i in range(13):
        print(f"   [{i:2d}] {OBS_LABELS[i]:<28} = {obs[i]:.4f}")
    print()

    # Dims 13-17: rival ahead
    if rival_ahead is not None:
        ra_cmp = _IDX_TO_COMPOUND.get(int(obs[14]), "?")
        print(
            f"  ── dims [13-17] rival ahead: {rival_ahead.driver}  "
            f"P{rival_ahead.current_position}  "
            f"{rival_ahead.compound}  age {rival_ahead.tire_age} ──"
        )
    else:
        print("  ── dims [13-17] rival ahead: NONE (ego P1) — sentinels active ──")
    for i in range(13, 18):
        sentinel_tag = "  (sentinel)" if rival_ahead is None else ""
        print(f"   [{i:2d}] {OBS_LABELS[i]:<28} = {obs[i]:.4f}{sentinel_tag}")
    print()

    # Dims 18-22: rival behind
    if rival_behind is not None:
        print(
            f"  ── dims [18-22] rival behind: {rival_behind.driver}  "
            f"P{rival_behind.current_position}  "
            f"{rival_behind.compound}  age {rival_behind.tire_age} ──"
        )
    else:
        print("  ── dims [18-22] rival behind: NONE (ego P20) — sentinels active ──")
    for i in range(18, 23):
        sentinel_tag = "  (sentinel)" if rival_behind is None else ""
        print(f"   [{i:2d}] {OBS_LABELS[i]:<28} = {obs[i]:.4f}{sentinel_tag}")
    print()

    # Dims 23-24: strategy flags
    print("  ── dims [23-24] strategy flags ────────────────────────────")
    undercut_reason = (
        "ego P1, no rival ahead" if rival_ahead is None
        else f"gap={obs[13]:.2f}s, rival_age={rival_ahead.tire_age} vs ego_age={ego.tire_age}"
    )
    defend_reason = (
        "ego P20, no rival behind" if rival_behind is None
        else f"gap={obs[18]:.2f}s, rival_age={rival_behind.tire_age} vs ego_age={ego.tire_age}"
    )
    print(f"   [23] undercut_window_open       = {obs[23]:.1f}  ({undercut_reason})")
    print(f"   [24] defending_against_undercut = {obs[24]:.1f}  ({defend_reason})")
    print()


def run_race_ver(seed: int = 42) -> tuple[dict[int, np.ndarray], GridRaceEnv]:
    """Run VER race; capture obs at specific laps."""
    env = GridRaceEnv()
    env.reset(seed=seed, options=CONFIG_VER)
    captured: dict[int, np.ndarray] = {}
    capture_at = {1, 10, 17, 19, 30, 56}

    for lap in range(1, 58):
        action = 3 if lap == PIT_LAP else 0
        obs, _, terminated, _, _ = env.step(action)
        if lap in capture_at:
            captured[lap] = obs.copy()
        if terminated:
            break

    return captured, env


def run_race_per(seed: int = 42) -> tuple[np.ndarray, GridRaceEnv]:
    """Run PER race at P5; capture obs at lap 5."""
    env = GridRaceEnv()
    env.reset(seed=seed, options=CONFIG_PER)
    obs_lap5 = None

    for lap in range(1, 58):
        action = 0  # PER stays (no specific strategy for validation)
        obs, _, terminated, _, _ = env.step(action)
        if lap == 5:
            obs_lap5 = obs.copy()
            break  # only need lap 5

    return obs_lap5, env


def main() -> None:
    # ── Race 1: VER at P1 ────────────────────────────────���────────────────────
    print()
    print("╔═════════════════════��════════════════════════════════════════╗")
    print("║  RACE 1 — VER ego at P1, 2024 Bahrain, seed=42              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    captured_ver, env_ver = run_race_ver(seed=42)

    PRINT_LAPS_VER = [1, 10, 17, 19, 30, 56]
    for lap in PRINT_LAPS_VER:
        if lap in captured_ver:
            print_obs(env_ver, captured_ver[lap], lap, "VER")

    # ── Race 2: PER at P5 ─────────────────────────────────────────────────────
    print()
    print("╔════════════════════════════════════════════════���═════════════╗")
    print("║  RACE 2 — PER ego at P5, 2024 Bahrain, seed=42, lap 5       ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    obs_per5, env_per = run_race_per(seed=42)
    print_obs(env_per, obs_per5, 5, "PER")

    # ── Sanity assertions ─────────────────────────────────────────────────────
    print("╔═════════════════════════════════════════════════��════════════╗")
    print("║  SANITY ASSERTIONS                                           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    failures: list[str] = []

    def check(desc: str, ok: bool, note: str = "") -> None:
        mark = "PASS" if ok else "FAIL"
        suffix = f"  ({note})" if note else ""
        print(f"  [{mark}]  {desc}{suffix}")
        if not ok:
            failures.append(desc)

    # A1: Lap 1 — ego P1: gap_to_ahead = 30.0 (sentinel), gap_to_behind > 0
    obs1 = captured_ver[1]
    check(
        "Lap 1: gap_to_rival_ahead_s = 30.0 (P1 sentinel)",
        obs1[13] == 30.0,
        f"got {obs1[13]:.3f}",
    )
    check(
        "Lap 1: gap_to_rival_behind_s > 0 (cars behind exist)",
        obs1[18] > 0.0,
        f"got {obs1[18]:.3f}",
    )
    check(
        "Lap 1: obs has 25 dims",
        len(obs1) == 25,
        f"len={len(obs1)}",
    )

    # A2: Lap 10 — ego likely still P1; gap_behind should be small (tight racing)
    obs10 = captured_ver[10]
    ego10_pos = int(obs10[9])
    if ego10_pos == 1:
        check(
            "Lap 10: gap_to_rival_behind_s in (0, 10] (still tight racing)",
            0.0 < obs10[18] <= 10.0,
            f"got {obs10[18]:.3f}  (ego P{ego10_pos})",
        )
    else:
        check(
            "Lap 10: gap_to_rival_ahead_s in (0, 10] (tight racing)",
            0.0 < obs10[13] <= 10.0,
            f"got {obs10[13]:.3f}  (ego P{ego10_pos})",
        )

    # A3: Lap 17 — ego P1, no rival ahead → undercut_window_open = 0
    obs17 = captured_ver[17]
    check(
        "Lap 17: undercut_window_open = 0.0 (ego P1, no rival ahead)",
        obs17[23] == 0.0,
        f"got {obs17[23]:.1f}",
    )
    check(
        "Lap 17: gap_to_rival_ahead_s = 30.0 (P1 sentinel)",
        obs17[13] == 30.0,
        f"got {obs17[13]:.3f}",
    )

    # A4: Lap 19 — ego just pitted to fresh HARD; defending = 0 since ego has fresher tires
    obs19 = captured_ver[19]
    ego19_tire_age = int(obs19[6])
    rival_behind_age19 = int(obs19[20])
    check(
        "Lap 19: ego on fresh HARD (tire_age ≤ 3 post-pit)",
        ego19_tire_age <= 3,
        f"ego tire_age={ego19_tire_age}",
    )
    check(
        "Lap 19: defending_against_undercut = 0 (ego freshest, rivals older)",
        obs19[24] == 0.0,
        f"got {obs19[24]:.1f}  (rival_behind_age={rival_behind_age19}, ego_age={ego19_tire_age})",
    )

    # A5: Lap 30 — rival tire ages should be realistic when rivals exist
    obs30 = captured_ver[30]
    ra_age30 = int(obs30[15])
    rb_age30 = int(obs30[20])
    # rival_ahead sentinel active when ego is P1 (gap == 30.0) — skip age check
    if obs30[13] < 30.0:
        check(
            "Lap 30: rival_ahead_tire_age in [1, 49] (not sentinel/maxed)",
            1 <= ra_age30 <= 49,
            f"got rival_ahead_age={ra_age30}",
        )
    else:
        check(
            "Lap 30: rival_ahead sentinel active (ego P1) — age=0 is correct",
            ra_age30 == 0,
            f"got rival_ahead_age={ra_age30}",
        )
    check(
        "Lap 30: rival_behind_tire_age in [1, 49]",
        1 <= rb_age30 <= 49,
        f"got rival_behind_age={rb_age30}",
    )

    # A6: Lap 56 — ego likely still leading; gap_behind > 5s (race spread out)
    obs56 = captured_ver[56]
    check(
        "Lap 56: gap_to_rival_behind_s > 5.0 (race has spread out)",
        obs56[18] > 5.0,
        f"got {obs56[18]:.2f}s",
    )

    # A7: Race 2 (PER at P5, lap 5) — both gaps nonzero and rivals identified
    check(
        "Race 2 Lap 5: gap_to_rival_ahead_s > 0 (PER not P1)",
        obs_per5[13] > 0.0,
        f"got {obs_per5[13]:.3f}",
    )
    check(
        "Race 2 Lap 5: gap_to_rival_behind_s > 0 (PER not P20)",
        obs_per5[18] > 0.0,
        f"got {obs_per5[18]:.3f}",
    )
    per_pos = int(obs_per5[9])
    check(
        "Race 2 Lap 5: rival_ahead sentinel NOT active (gap < 30.0)",
        obs_per5[13] < 30.0,
        f"gap_ahead={obs_per5[13]:.3f}  ego_pos=P{per_pos}",
    )
    check(
        "Race 2 Lap 5: rival_behind sentinel NOT active (gap < 30.0)",
        obs_per5[18] < 30.0,
        f"gap_behind={obs_per5[18]:.3f}  ego_pos=P{per_pos}",
    )

    # A8: obs_space shape matches returned obs shape
    check(
        "Observation space shape = (25,)",
        GridRaceEnv().observation_space.shape == (25,),
        f"got {GridRaceEnv().observation_space.shape}",
    )

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
