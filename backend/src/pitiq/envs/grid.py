"""GridRaceEnv — multi-agent F1 race simulation (Phase 4.5.2).

Full 20-car grid where:
  - The ego agent controls its own pit strategy via step(action).
  - Rivals sample pit decisions from the Phase 4.5.1 rival_pit_policy (Part 3).
    Part 2 uses a TEMPORARY cliff-threshold placeholder instead.
  - Lap times predicted per car via the styled XGBoost model (Phase 3.2).
  - Position updated from cumulative race time (+ overtaking friction in Part 3).

Observation space (13 dims, float32) — same layout as SandboxRaceEnv.
Will expand to ~20 dims in Phase 4.5.3 once rival-gap context is added.

Action space (Discrete 4):
    0 = stay   1 = pit_soft   2 = pit_medium   3 = pit_hard

CLI validation:
    python -m pitiq.envs.test_grid_part1   (skeleton)
    python -m pitiq.envs.test_grid_part2   (full race)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from pitiq.ml.compound_constants import (
    COMPOUND_CLIFF_LAP,
    COMPOUND_CLIFF_PENALTY_S,
    COMPOUND_FRESH_TIRE_OFFSET_S,
)
from pitiq.ml.predict import predict_lap_time
from pitiq.ml.rival_policy import predict_pit_probability  # noqa: F401 — used in Part 3

logger = logging.getLogger(__name__)

_REPO_ROOT    = Path(__file__).parents[4]
_FEATURES_DIR = _REPO_ROOT / "data" / "features"

_ACTION_COMPOUND: dict[int, str] = {1: "SOFT", 2: "MEDIUM", 3: "HARD"}
_COMPOUNDS_ORDER = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]
_COMPOUND_IDX: dict[str, int] = {c: i for i, c in enumerate(_COMPOUNDS_ORDER)}
_DRY_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD"})

_PIT_LOSS_S           = 22.0
_FUEL_BURN_KG_PER_LAP = 1.8
_INITIAL_FUEL_KG      = 110.0
_GRID_SIZE            = 20

# Per-circuit overtaking difficulty factor: 0 = procession, 1 = DRS highway.
# Sourced from historical overtaking statistics + F1 analyst consensus.
# Used in Part 3 step() to scale the overtaking probability model so
# position changes at Monaco are appropriately rare vs Bahrain.
CIRCUIT_OVERTAKING_FACTOR: dict[str, float] = {
    "Bahrain Grand Prix":         0.80,
    "Saudi Arabian Grand Prix":   0.70,
    "Australian Grand Prix":      0.50,
    "Japanese Grand Prix":        0.45,
    "Chinese Grand Prix":         0.65,
    "Miami Grand Prix":           0.55,
    "Emilia Romagna Grand Prix":  0.40,
    "Monaco Grand Prix":          0.05,
    "Canadian Grand Prix":        0.60,
    "Spanish Grand Prix":         0.50,
    "Austrian Grand Prix":        0.70,
    "British Grand Prix":         0.65,
    "Hungarian Grand Prix":       0.20,
    "Belgian Grand Prix":         0.80,
    "Dutch Grand Prix":           0.35,
    "Italian Grand Prix":         0.90,
    "Azerbaijan Grand Prix":      0.70,
    "Singapore Grand Prix":       0.10,
    "United States Grand Prix":   0.65,
    "Mexico City Grand Prix":     0.55,
    "São Paulo Grand Prix":       0.60,
    "Las Vegas Grand Prix":       0.75,
    "Qatar Grand Prix":           0.50,
    "Abu Dhabi Grand Prix":       0.45,
    # 2021-only / defunct circuits (kept for training-data coverage)
    "Styrian Grand Prix":         0.60,
    "Turkish Grand Prix":         0.55,
    "Portuguese Grand Prix":      0.65,
    "Russian Grand Prix":         0.55,
}
_DEFAULT_OVERTAKING_FACTOR = 0.50   # fallback for unknown circuits


# ── Car dataclass ─────────────────────────────────────────────────────────────

@dataclass
class Car:
    """Mutable per-car state in GridRaceEnv.

    Initialised by GridRaceEnv.reset(); mutated by step() each lap.
    Fields without defaults must precede fields with defaults.
    """
    driver:                str
    style_vector:          dict   # 11-key dict from driver_styles.parquet
    starting_position:     int    # immutable grid slot (1-20)
    current_position:      int    # live race position, updated each lap
    cumulative_race_time:  float  # seconds elapsed including pit losses
    compound:              str
    tire_age:              int    # laps on current set (1 = brand new)
    stint_number:          int    # 1-indexed
    fuel_estimate_kg:      float
    has_used_2nd_compound: bool
    pit_history:           list   = field(default_factory=list)  # [(lap_num, compound)]
    starting_compound:     str    = ""   # set by reset(); used to detect 2nd compound


# ── Module-level cached data loads ────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_driver_styles() -> pd.DataFrame:
    """Load driver_styles.parquet once; index = Driver abbreviation."""
    return pd.read_parquet(_FEATURES_DIR / "driver_styles.parquet")


@lru_cache(maxsize=1)
def _load_training_laps() -> pd.DataFrame:
    """Training-split lap features (test/val races excluded to prevent leakage)."""
    from pitiq.features.split import TEST_RACES, VAL_RACES
    df = pd.read_parquet(_FEATURES_DIR / "lap_features.parquet")
    held_out = TEST_RACES | VAL_RACES
    df["_key"] = list(zip(df["Year"].astype(int), df["RoundNumber"].astype(int)))
    return df[~df["_key"].isin(held_out)].drop(columns=["_key"])


# ── Rival profile helper (mirrors sandbox.py to avoid cross-import) ───────────

@lru_cache(maxsize=64)
def _circuit_rival_baseline(circuit: str, year: int) -> tuple[float, float, int]:
    """Return (pace_s1, pace_s2, median_pit_lap) from top-10 training data.

    Provides the reference lap time used in the pace_reward component.
    Fallback chain: exact (circuit, year) → closest year → grand mean.
    """
    train = _load_training_laps()

    def _profile(sub: pd.DataFrame) -> tuple[float, float, int] | None:
        top10 = sub[sub["position"] <= 10]
        if len(top10) < 10:
            return None
        pace_s1 = float(top10[top10["stint_number"] == 1]["LapTimeCorrected"].mean())
        s2 = top10[top10["stint_number"] == 2]["LapTimeCorrected"]
        pace_s2 = float(s2.mean()) if len(s2) > 0 else pace_s1
        pit_laps = []
        for _, grp in top10.groupby("Driver"):
            if grp["stint_number"].max() >= 2:
                last_s1 = grp[grp["stint_number"] == 1]["LapNumber"].max()
                if not pd.isna(last_s1):
                    pit_laps.append(int(last_s1))
        if not pit_laps:
            total = int(sub["LapNumber"].max())
            return pace_s1, pace_s1, int(total * 0.55)
        return pace_s1, pace_s2, int(np.median(pit_laps))

    sub = train[(train["EventName"] == circuit) & (train["Year"] == year)]
    if len(sub) > 0:
        result = _profile(sub)
        if result is not None:
            return result

    available = sorted(train[train["EventName"] == circuit]["Year"].unique())
    if available:
        closest = int(min(available, key=lambda y: abs(y - year)))
        sub = train[(train["EventName"] == circuit) & (train["Year"] == closest)]
        result = _profile(sub)
        if result is not None:
            return result

    top10 = train[train["position"] <= 10]
    return (
        float(top10[top10["stint_number"] == 1]["LapTimeCorrected"].mean()),
        float(top10[top10["stint_number"] == 2]["LapTimeCorrected"].mean()),
        25,
    )


# ── Rival pit decision helpers (TEMPORARY — replaced by rival_pit_policy in Part 3) ──

def _placeholder_rival_pit_decision(rival: Car, laps_remaining: int) -> bool:
    """Deterministic cliff-threshold pit rule.

    TEMPORARY PLACEHOLDER — Part 3 replaces this with predict_pit_probability()
    from the Phase 4.5.1 XGBClassifier for stochastic, style-aware decisions.

    Rules (in order):
      1. Pit ~3 laps before the compound cliff if race isn't nearly over.
      2. Force pit if 2-compound rule not satisfied and race is ending.
    """
    cliff_lap = COMPOUND_CLIFF_LAP.get(rival.compound, 999)
    if rival.tire_age >= cliff_lap - 3 and laps_remaining > 5:
        return True
    if not rival.has_used_2nd_compound and laps_remaining < 8:
        return True
    return False


def _rival_pit_compound_choice(rival: Car, laps_remaining: int) -> str:
    """Choose the compound for a rival's pit stop.

    Prefers the hardest durable compound when stints are long, softest when
    short.  Guarantees the chosen compound differs from the current compound.
    """
    if not rival.has_used_2nd_compound:
        # Must switch to satisfy the two-compound rule
        if laps_remaining > 25:
            chosen = "HARD"
        elif laps_remaining > 12:
            chosen = "MEDIUM"
        else:
            chosen = "SOFT"
    else:
        # Free choice based on remaining race distance
        if laps_remaining > 30:
            chosen = "HARD"
        elif laps_remaining > 15:
            chosen = "MEDIUM"
        else:
            chosen = "SOFT"

    # If the chosen compound matches the current one, cycle through alternatives
    if chosen == rival.compound:
        for alt in ["MEDIUM", "HARD", "SOFT"]:
            if alt != rival.compound:
                chosen = alt
                break

    return chosen


# ── Environment ────────────────────────────────────────────────────────────────

class GridRaceEnv(gym.Env):
    """Multi-agent Gymnasium F1 race environment for Optimizer Mode.

    20 cars. Ego agent controls pit strategy; 19 rivals make pit decisions
    via the Phase 4.5.1 rival_pit_policy (Part 3) or the cliff-threshold
    placeholder (Part 2).

    Part 2: step() with lap times, cumulative time, naive position sort.
    Part 3: rival_pit_policy integration + overtaking friction.
    Phase 4.5.3: obs space expanded with rival-gap context.
    """

    metadata = {"render_modes": ["human", "ansi"]}

    def __init__(self, render_mode: str | None = None) -> None:
        super().__init__()
        if render_mode is not None and render_mode not in self.metadata["render_modes"]:
            raise ValueError(f"Unsupported render_mode {render_mode!r}")
        self.render_mode = render_mode

        # Observation space: 13 dims (same layout as SandboxRaceEnv).
        # Phase 4.5.3 will extend with rival-gap features.
        low = np.array([
            0.0,                          # [0]  lap_fraction
            0.0, 0.0, 0.0, 0.0, 0.0,     # [1-5] compound one-hot (S/M/H/I/W)
            1.0,                          # [6]  tire_age
            1.0,                          # [7]  stint_number
            0.0,                          # [8]  fuel_estimate_kg
            1.0,                          # [9]  position
            0.0,                          # [10] laps_remaining
            0.0,                          # [11] laps_past_cliff
            0.0,                          # [12] has_used_2nd_compound
        ], dtype=np.float32)

        high = np.array([
            1.0,
            1.0, 1.0, 1.0, 1.0, 1.0,
            50.0,
            8.0,
            110.0,
            20.0,
            100.0,
            50.0,
            1.0,
        ], dtype=np.float32)

        self.observation_space = spaces.Box(low=low, high=high, dtype=np.float32)
        self.action_space = spaces.Discrete(4)

        # Race config — populated by reset()
        self._circuit:            str   = ""
        self._year:               int   = 2025
        self._total_laps:         int   = 57
        self._two_compound_rule:  bool  = True
        self._weather:            dict  = {}
        self._overtaking_factor:  float = _DEFAULT_OVERTAKING_FACTOR

        # Rival pace baseline for pace_reward (set by reset())
        self._baseline_pace_s1:  float = 90.0
        self._baseline_pace_s2:  float = 90.0
        self._baseline_pit_lap:  int   = 25

        # Lap counter (1-indexed, incremented in step())
        self._lap_num: int = 1

        # Grid state
        self._grid: list[Car] = []
        self._ego: Car | None = None

        # Previous ego position for position_delta reward
        self._prev_ego_position: int = 1

        # Year-specific weather means for XGBoost in-distribution inference
        self._infer_air:   float | None = None
        self._infer_track: float | None = None
        self._infer_hum:   float | None = None

        self._styles_df: pd.DataFrame = _load_driver_styles()

    # ── reset ──────────────────────────────────────────────────────────────────

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict]:
        """Initialise a new race episode.

        Required config keys (via options):
            circuit                 : full EventName string ("Bahrain Grand Prix")
            year                    : int
            total_laps              : int
            ego_driver              : 3-letter code ("VER")
            ego_starting_position   : int (1-20)
            starting_grid           : ordered list of 20 driver codes (P1 first)
            starting_compounds      : dict {driver: compound}

        Optional:
            weather                     : dict air_temp/track_temp/humidity/is_wet
            two_compound_rule_enforced  : bool (default True)
        """
        super().reset(seed=seed)
        cfg = options or {}

        required = [
            "circuit", "year", "total_laps",
            "ego_driver", "ego_starting_position",
            "starting_grid", "starting_compounds",
        ]
        missing = [k for k in required if k not in cfg]
        if missing:
            raise ValueError(f"GridRaceEnv.reset() missing config keys: {missing}")

        circuit            = str(cfg["circuit"])
        year               = int(cfg["year"])
        total_laps         = int(cfg["total_laps"])
        ego_driver         = str(cfg["ego_driver"])
        ego_start_pos      = int(cfg["ego_starting_position"])
        starting_grid      = list(cfg["starting_grid"])
        starting_compounds = {k: str(v).upper() for k, v in cfg["starting_compounds"].items()}
        weather            = dict(cfg.get("weather", {}))
        two_compound_rule  = bool(cfg.get("two_compound_rule_enforced", True))

        if len(starting_grid) != _GRID_SIZE:
            raise ValueError(
                f"starting_grid must have {_GRID_SIZE} drivers, got {len(starting_grid)}"
            )
        if len(set(starting_grid)) != _GRID_SIZE:
            raise ValueError("starting_grid contains duplicate driver codes")
        if ego_driver not in starting_grid:
            raise ValueError(f"ego_driver {ego_driver!r} not in starting_grid")
        actual_pos = starting_grid.index(ego_driver) + 1
        if actual_pos != ego_start_pos:
            raise ValueError(
                f"{ego_driver!r} is at grid P{actual_pos} "
                f"but ego_starting_position={ego_start_pos}"
            )

        missing_styles = [d for d in starting_grid if d not in self._styles_df.index]
        if missing_styles:
            logger.warning("No style features for drivers: %s", missing_styles)

        self._circuit           = circuit
        self._year              = year
        self._total_laps        = total_laps
        self._two_compound_rule = two_compound_rule
        self._weather           = weather
        self._lap_num           = 1
        self._overtaking_factor = CIRCUIT_OVERTAKING_FACTOR.get(
            circuit, _DEFAULT_OVERTAKING_FACTOR
        )

        # Rival baseline profile for pace_reward
        s1, s2, pit_lap = _circuit_rival_baseline(circuit, year)
        self._baseline_pace_s1 = s1
        self._baseline_pace_s2 = s2
        self._baseline_pit_lap = pit_lap

        # Year-specific weather for XGBoost in-distribution inference
        train = _load_training_laps()
        sub_cy = train[(train["EventName"] == circuit) & (train["Year"] == year)]
        if len(sub_cy) >= 5:
            self._infer_air   = float(sub_cy["air_temp"].mean())
            self._infer_track = float(sub_cy["track_temp"].mean())
            self._infer_hum   = float(sub_cy["humidity"].mean())
        else:
            sub_c = train[train["EventName"] == circuit]
            if len(sub_c) >= 5:
                self._infer_air   = float(sub_c["air_temp"].mean())
                self._infer_track = float(sub_c["track_temp"].mean())
                self._infer_hum   = float(sub_c["humidity"].mean())
            else:
                self._infer_air = self._infer_track = self._infer_hum = None

        self._grid = []
        for pos, driver in enumerate(starting_grid, start=1):
            if driver in self._styles_df.index:
                row = self._styles_df.loc[driver]
                sv: dict = {k: float(v) for k, v in row.items()}
            else:
                sv = {k: float("nan") for k in self._styles_df.columns}

            compound = starting_compounds.get(driver, "SOFT")
            car = Car(
                driver                = driver,
                style_vector          = sv,
                starting_position     = pos,
                current_position      = pos,
                cumulative_race_time  = 0.0,
                compound              = compound,
                tire_age              = 1,
                stint_number          = 1,
                fuel_estimate_kg      = _INITIAL_FUEL_KG,
                has_used_2nd_compound = False,
                pit_history           = [],
                starting_compound     = compound,
            )
            self._grid.append(car)

        self._ego = self._grid[starting_grid.index(ego_driver)]
        self._prev_ego_position = ego_start_pos

        return self._obs(), {}

    # ── step ───────────────────────────────────────────────────────────────────

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        """Advance the race by one lap.

        Order of operations
        -------------------
        (a) Validate ego action — pit into same compound → invalid, treat as stay
        (b) Determine rival pit decisions (TEMPORARY placeholder — Part 3 replaces)
        (c) Compute lap time for every car via XGBoost + compound dynamics
        (d) Apply pit penalties; update compound/tire/stint for pitting cars
        (e) Update fuel and cumulative race time for every car
        (f) Naive position sort by cumulative_race_time (overtaking friction in Part 3)
        (g) Compute ego reward
        (h) Increment lap counter; tire_age for non-pitted cars
        (i) Return obs, reward, terminated, False, info
        """
        assert self.action_space.contains(action), f"Invalid action {action}"
        assert self._ego is not None, "step() called before reset()"

        completed_lap  = self._lap_num
        laps_remaining = self._total_laps - completed_lap  # after this lap

        ego            = self._ego
        original_action = action
        action_was_invalid = False

        # (a) Validate ego action
        if action in _ACTION_COMPOUND and _ACTION_COMPOUND[action] == ego.compound:
            action_was_invalid = True
            action = 0

        # Capture ego state BEFORE any mutations (for reward computation)
        ego_laps_past_cliff = max(
            0, ego.tire_age - COMPOUND_CLIFF_LAP.get(ego.compound, 999)
        )
        prev_ego_pos = self._prev_ego_position

        # (b) Rival pit decisions — TEMPORARY cliff-threshold placeholder.
        #     Part 3 replaces with predict_pit_probability() for stochastic,
        #     style-aware, calibrated decisions.
        rival_new_compound: dict[str, str | None] = {}
        for car in self._grid:
            if car is ego:
                continue
            if _placeholder_rival_pit_decision(car, laps_remaining):
                rival_new_compound[car.driver] = _rival_pit_compound_choice(
                    car, laps_remaining
                )
            else:
                rival_new_compound[car.driver] = None

        # (c) Compute lap times for all 20 cars
        is_wet    = bool(self._weather.get("is_wet", False))
        air_temp  = self._weather.get("air_temp")  or self._infer_air
        track_temp = self._weather.get("track_temp") or self._infer_track
        humidity  = self._weather.get("humidity")  or self._infer_hum

        lap_times: dict[str, float] = {}
        for car in self._grid:
            lt = predict_lap_time(
                driver        = car.driver,
                circuit       = self._circuit,
                compound      = car.compound,
                tire_age      = car.tire_age,
                stint_number  = car.stint_number,
                fuel_load     = car.fuel_estimate_kg,
                position      = float(car.current_position),
                laps_remaining = float(laps_remaining),
                is_wet        = is_wet,
                air_temp      = air_temp,
                track_temp    = track_temp,
                humidity      = humidity,
                year          = self._year,
            )
            # Compound dynamics: fresh-tire speed bonus + post-cliff degradation
            lt += COMPOUND_FRESH_TIRE_OFFSET_S.get(car.compound, 0.0)
            lpc = max(0, car.tire_age - COMPOUND_CLIFF_LAP.get(car.compound, 999))
            lt += lpc * COMPOUND_CLIFF_PENALTY_S.get(car.compound, 0.0)
            lap_times[car.driver] = lt

        # (d) Apply pit penalties; update pitting cars' state
        ego_pitting   = action != 0
        pitted_drivers: set[str] = set()
        num_rivals_pitted = 0

        for car in self._grid:
            if car is ego:
                pitting     = ego_pitting
                new_compound = _ACTION_COMPOUND[action] if ego_pitting else None
            else:
                new_compound = rival_new_compound.get(car.driver)
                pitting      = new_compound is not None

            if pitting and new_compound:
                lap_times[car.driver] += _PIT_LOSS_S
                car.compound              = new_compound
                car.tire_age              = 1   # fresh tyre (not incremented below)
                car.stint_number         += 1
                if new_compound != car.starting_compound:
                    car.has_used_2nd_compound = True
                car.pit_history.append((completed_lap, new_compound))
                pitted_drivers.add(car.driver)
                if car is not ego:
                    num_rivals_pitted += 1

        # (e) Fuel burn + cumulative time update
        for car in self._grid:
            car.fuel_estimate_kg     = max(0.0, car.fuel_estimate_kg - _FUEL_BURN_KG_PER_LAP)
            car.cumulative_race_time += lap_times[car.driver]

        # (f) Naive position sort — cumulative_race_time ascending → position 1-20.
        #     No overtaking friction yet; Part 3 adds circuit-scaled resistance.
        self._grid.sort(key=lambda c: c.cumulative_race_time)
        for rank, car in enumerate(self._grid, start=1):
            car.current_position = rank

        # (h) Increment tire_age for non-pitted cars; increment lap counter
        for car in self._grid:
            if car.driver not in pitted_drivers:
                car.tire_age += 1

        self._lap_num += 1

        # Terminal and two-compound rule check
        terminated = self._lap_num > self._total_laps
        violated_rule = False
        if terminated and self._two_compound_rule:
            ego_dry = ({ego.starting_compound} | {c for _, c in ego.pit_history}) & _DRY_COMPOUNDS
            violated_rule = len(ego_dry) < 2

        # (g) Reward
        position_delta    = prev_ego_pos - ego.current_position  # + = gained
        position_reward   = position_delta * 0.5
        pit_cost          = -0.05 if original_action != 0 else 0.0
        cliff_penalty     = -0.10 * ego_laps_past_cliff
        invalid_penalty   = -2.0 if action_was_invalid else 0.0

        baseline_lt  = self._rival_baseline_lap_time(completed_lap)
        pace_reward  = (baseline_lt - lap_times[ego.driver]) * 0.05

        step_reward = (
            position_reward
            + pit_cost
            + cliff_penalty
            + invalid_penalty
            + pace_reward
        )
        if terminated:
            step_reward += (-ego.current_position * 2.0)
            step_reward += (10.0 if not violated_rule else -100.0)

        self._prev_ego_position = ego.current_position

        # Info
        race_leader = self._grid[0].driver  # already sorted
        info: dict[str, Any] = {
            "ego_lap_time":               lap_times[ego.driver],
            "ego_cumulative_time":        ego.cumulative_race_time,
            "ego_position":               ego.current_position,
            "ego_compound":               ego.compound,
            "ego_tire_age":               ego.tire_age,
            "num_rivals_pitted_this_lap": num_rivals_pitted,
            "race_winner_so_far":         race_leader,
        }

        if self.render_mode == "human":
            self.render()

        return self._obs(), step_reward, terminated, False, info

    # ── helpers ────────────────────────────────────────────────────────────────

    def _rival_baseline_lap_time(self, lap: int) -> float:
        """Reference 1-stop circuit lap time for pace_reward (mirrors SandboxRaceEnv)."""
        if lap < self._baseline_pit_lap:
            return self._baseline_pace_s1
        elif lap == self._baseline_pit_lap:
            return self._baseline_pace_s1 + _PIT_LOSS_S
        else:
            return self._baseline_pace_s2

    def _obs(self) -> np.ndarray:
        """Build the 13-dim ego observation vector."""
        if self._ego is None:
            return np.zeros(13, dtype=np.float32)

        ego = self._ego
        compound_oh = np.zeros(5, dtype=np.float32)
        compound_oh[_COMPOUND_IDX.get(ego.compound, 0)] = 1.0

        laps_remaining  = float(max(0, self._total_laps - self._lap_num + 1))
        laps_past_cliff = float(
            max(0, ego.tire_age - COMPOUND_CLIFF_LAP.get(ego.compound, 999))
        )
        lap_fraction = float(
            min(1.0, (self._lap_num - 1) / max(1, self._total_laps))
        )

        return np.array([
            lap_fraction,
            *compound_oh,
            float(ego.tire_age),
            float(ego.stint_number),
            float(ego.fuel_estimate_kg),
            float(ego.current_position),
            laps_remaining,
            laps_past_cliff,
            float(int(ego.has_used_2nd_compound)),
        ], dtype=np.float32)

    # ── render ─────────────────────────────────────────────────────────────────

    def render(self) -> str | None:
        """Print top-10 grid state (always to stdout when called directly)."""
        if not self._grid:
            return None

        if all(c.cumulative_race_time == 0.0 for c in self._grid):
            sorted_grid = sorted(self._grid, key=lambda c: c.starting_position)
        else:
            sorted_grid = sorted(self._grid, key=lambda c: c.cumulative_race_time)

        lap_display  = max(0, self._lap_num - 1)
        leader_time  = sorted_grid[0].cumulative_race_time

        lines = [f"Lap {lap_display}/{self._total_laps} | {self._circuit}"]
        for rank, car in enumerate(sorted_grid[:10], start=1):
            gap     = car.cumulative_race_time - leader_time
            gap_str = f"+{gap:.1f}s" if gap > 0 else "LEAD"
            ego_tag = " <EGO>" if self._ego and car.driver == self._ego.driver else ""
            lines.append(
                f"  P{rank:<2} {car.driver:<3}  "
                f"{car.compound[0]}  "
                f"age {car.tire_age:2d}  "
                f"{gap_str}{ego_tag}"
            )

        output = "\n".join(lines)
        print(output)
        return output

    def close(self) -> None:
        pass
