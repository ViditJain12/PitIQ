"""SandboxRaceEnv — single-car F1 race simulation (Phase 4.1).

Observation space (13 dims, float32):
    [0]   lap_fraction          laps_completed / total_laps  ∈ [0, 1]
    [1-5] compound_one_hot      SOFT / MEDIUM / HARD / INTERMEDIATE / WET
    [6]   tire_age              laps on current set  ∈ [1, 50]
    [7]   stint_number          1-indexed  ∈ [1, 8]
    [8]   fuel_estimate_kg      kg remaining  ∈ [0, 110]
    [9]   position              race position (1 = lead)  ∈ [1, 20]
    [10]  laps_remaining        laps left including next  ∈ [0, 100]
    [11]  laps_past_cliff       max(0, tire_age - cliff_lap)  ∈ [0, 50]
    [12]  has_used_2nd_compound 0 or 1

Action space (Discrete 4):
    0 = stay   1 = pit_soft   2 = pit_medium   3 = pit_hard

Usage:
    env = SandboxRaceEnv()
    obs, _ = env.reset(options={
        'circuit': 'Italian Grand Prix',
        'driver': 'VER',
        'year': 2025,
        'total_laps': 53,
        'starting_position': 1,
        'starting_compound': 'MEDIUM',
        'weather': {'air_temp': 26, 'track_temp': 40, 'humidity': 45, 'is_wet': False},
        'two_compound_rule_enforced': True,
    })
    obs, reward, terminated, truncated, info = env.step(0)
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

_REPO_ROOT    = Path(__file__).parents[4]
_FEATURES_DIR = _REPO_ROOT / "data" / "features"

# Action index → compound name
_ACTION_COMPOUND: dict[int, str] = {1: "SOFT", 2: "MEDIUM", 3: "HARD"}

# Compound → one-hot slot (positions 1-5 in obs)
_COMPOUNDS_ORDER = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]
_COMPOUND_IDX: dict[str, int] = {c: i for i, c in enumerate(_COMPOUNDS_ORDER)}

_PIT_LOSS_S          = 22.0
_FUEL_BURN_KG_PER_LAP = 1.8
_INITIAL_FUEL_KG     = 110.0
_GRID_SIZE           = 20
_N_RIVALS            = _GRID_SIZE - 1
_GAP_PER_POS_S       = 1.5   # initial headway between adjacent grid positions


# ── Rival profile (pitting model) ─────────────────────────────────────────────

@lru_cache(maxsize=1)
def _training_data() -> pd.DataFrame:
    """Load training-split lap features once, cache indefinitely."""
    from pitiq.features.split import TEST_RACES, VAL_RACES
    df = pd.read_parquet(_FEATURES_DIR / "lap_features.parquet")
    held_out = TEST_RACES | VAL_RACES
    df["_key"] = list(zip(df["Year"].astype(int), df["RoundNumber"].astype(int)))
    return df[~df["_key"].isin(held_out)].drop(columns=["_key"])


def _profile_from_subset(sub: pd.DataFrame) -> tuple[float, float, int] | None:
    """Compute (pace_s1, pace_s2, median_pit_lap) from a circuit/year slice."""
    top10 = sub[sub["position"] <= 10]
    if len(top10) < 10:
        return None

    pace_s1 = float(top10[top10["stint_number"] == 1]["LapTimeCorrected"].mean())
    s2_laps = top10[top10["stint_number"] == 2]["LapTimeCorrected"]
    pace_s2 = float(s2_laps.mean()) if len(s2_laps) > 0 else pace_s1

    pit_laps: list[int] = []
    for _, grp in top10.groupby("Driver"):
        if grp["stint_number"].max() >= 2:
            last_s1 = grp[grp["stint_number"] == 1]["LapNumber"].max()
            if not pd.isna(last_s1):
                pit_laps.append(int(last_s1))

    if not pit_laps:
        total = int(sub["LapNumber"].max())
        return pace_s1, pace_s1, int(total * 0.55)   # no-stop race fallback

    return pace_s1, pace_s2, int(np.median(pit_laps))


@lru_cache(maxsize=64)
def load_circuit_rival_profile(circuit: str, year: int) -> tuple[float, float, int]:
    """Return (pace_s1_s, pace_s2_s, median_pit_lap) for a representative rival.

    Represents a "typical top-10 driver" doing a 1-stop strategy at this circuit.
    All paces are mean LapTimeCorrected for top-10 finishers from training data.

    Fallback behaviour:
    - Exact (circuit, year): use it.
    - Circuit exists for other years: use closest year, warn.
    - Unknown circuit: use grand mean pace, pit at lap 25.
    """
    train = _training_data()

    sub = train[(train["EventName"] == circuit) & (train["Year"] == year)]
    if len(sub) > 0:
        result = _profile_from_subset(sub)
        if result is not None:
            return result

    available = sorted(train[train["EventName"] == circuit]["Year"].unique())
    if available:
        closest = int(min(available, key=lambda y: abs(y - year)))
        logger.warning(
            "No rival profile for %r/%d — falling back to year %d", circuit, year, closest
        )
        sub = train[(train["EventName"] == circuit) & (train["Year"] == closest)]
        result = _profile_from_subset(sub)
        if result is not None:
            return result

    logger.warning("Circuit %r unknown — using grand-mean rival profile", circuit)
    top10 = train[train["position"] <= 10]
    return (
        float(top10[top10["stint_number"] == 1]["LapTimeCorrected"].mean()),
        float(top10[top10["stint_number"] == 2]["LapTimeCorrected"].mean()),
        25,
    )


def rival_reference_time(circuit: str, year: int, total_laps: int) -> float:
    """Expected race duration for a median-rival 1-stop strategy (seconds).

    Used as the reference for ±N% sanity checks in tests.
    """
    pace_s1, pace_s2, pit_lap = load_circuit_rival_profile(circuit, year)
    pit_lap = min(pit_lap, total_laps - 1)
    return pace_s1 * pit_lap + _PIT_LOSS_S + pace_s2 * (total_laps - pit_lap)


# ── Environment ────────────────────────────────────────────────────────────────

class SandboxRaceEnv(gym.Env):
    """Single-car Gymnasium F1 race environment for Sandbox Mode.

    See module docstring for observation / action space details.
    """

    metadata = {"render_modes": ["human", "ansi"]}

    def __init__(self, render_mode: str | None = None) -> None:
        super().__init__()
        if render_mode is not None and render_mode not in self.metadata["render_modes"]:
            raise ValueError(f"Unsupported render_mode {render_mode!r}")
        self.render_mode = render_mode

        # Observation space
        low = np.array([
            0.0,                          # [0]  lap_fraction
            0.0, 0.0, 0.0, 0.0, 0.0,     # [1-5] compound one-hot
            1.0,                          # [6]  tire_age
            1.0,                          # [7]  stint_number
            0.0,                          # [8]  fuel_estimate_kg
            1.0,                          # [9]  position
            0.0,                          # [10] laps_remaining
            0.0,                          # [11] laps_past_cliff
            0.0,                          # [12] has_used_2nd_compound
        ], dtype=np.float32)

        high = np.array([
            1.0,                          # [0]
            1.0, 1.0, 1.0, 1.0, 1.0,     # [1-5]
            50.0,                         # [6]
            8.0,                          # [7]
            110.0,                        # [8]
            20.0,                         # [9]
            100.0,                        # [10]
            50.0,                         # [11]
            1.0,                          # [12]
        ], dtype=np.float32)

        self.observation_space = spaces.Box(low=low, high=high, dtype=np.float32)
        self.action_space = spaces.Discrete(4)

        # Race config — set by reset()
        self._circuit: str         = ""
        self._driver:  str         = ""
        self._year:    int         = 2025
        self._total_laps: int      = 53
        self._weather: dict        = {}
        self._two_compound_rule: bool = True

        # Race state
        self._lap_num:    int   = 1   # next lap to run (1-indexed)
        self._compound:   str   = "MEDIUM"
        self._tire_age:   int   = 1   # laps on current set (1 = brand new)
        self._stint_num:  int   = 1
        self._fuel_kg:    float = _INITIAL_FUEL_KG
        self._position:   int   = 10
        self._cum_time:   float = 0.0
        self._has_2nd:    bool  = False
        self._used_cpds:  set[str] = set()
        self._start_cpd:  str   = "MEDIUM"

        # Rivals — 19 cars following a 1-stop rival profile
        self._rival_pace_s1: float    = 90.0   # stint-1 mean pace
        self._rival_pace_s2: float    = 90.0   # stint-2 mean pace after pit
        self._rival_pit_lap: int      = 25     # lap on which all rivals pit
        self._rival_cum:  np.ndarray  = np.zeros(_N_RIVALS, dtype=np.float64)

        # Year-specific inferred weather (set by reset(); None = fall back to circuit mean)
        self._infer_air:   float | None = None
        self._infer_track: float | None = None
        self._infer_hum:   float | None = None

        # Info carried into render() / info dict
        self._last_lap_time:   float = 0.0
        self._last_pit:        bool  = False
        self._last_completed_lap: int = 0
        self._violated_rule:   bool  = False

    # ── reset ──────────────────────────────────────────────────────────────────

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)

        cfg = options or {}
        self._circuit   = str(cfg.get("circuit", "Italian Grand Prix"))
        self._driver    = str(cfg.get("driver",  "VER"))
        self._year      = int(cfg.get("year",    2025))
        self._total_laps  = int(cfg.get("total_laps",        53))
        start_pos         = int(cfg.get("starting_position",  1))
        start_cpd         = str(cfg.get("starting_compound",  "MEDIUM")).upper()
        self._weather     = dict(cfg.get("weather", {}))
        self._two_compound_rule = bool(cfg.get("two_compound_rule_enforced", True))

        self._lap_num    = 1
        self._compound   = start_cpd
        self._start_cpd  = start_cpd
        self._tire_age   = 1
        self._stint_num  = 1
        self._fuel_kg    = _INITIAL_FUEL_KG
        self._position   = start_pos
        self._cum_time   = 0.0
        self._has_2nd    = False
        self._used_cpds  = {start_cpd}
        self._violated_rule = False
        self._last_lap_time = 0.0
        self._last_pit      = False
        self._last_completed_lap = 0

        # Rival 1-stop profile for this circuit/year
        pace_s1, pace_s2, rival_pit_lap = load_circuit_rival_profile(
            self._circuit, self._year
        )
        self._rival_pace_s1 = pace_s1
        self._rival_pace_s2 = pace_s2
        self._rival_pit_lap = rival_pit_lap

        # Year-specific weather — use exact (circuit, year) mean from training data so
        # XGBoost operates in-distribution. Falls back to circuit-wide mean if no match.
        train = _training_data()
        sub_cy = train[(train["EventName"] == self._circuit) & (train["Year"] == self._year)]
        if len(sub_cy) >= 5:
            self._infer_air   = float(sub_cy["air_temp"].mean())
            self._infer_track = float(sub_cy["track_temp"].mean())
            self._infer_hum   = float(sub_cy["humidity"].mean())
        else:
            sub_c = train[train["EventName"] == self._circuit]
            if len(sub_c) >= 5:
                self._infer_air   = float(sub_c["air_temp"].mean())
                self._infer_track = float(sub_c["track_temp"].mean())
                self._infer_hum   = float(sub_c["humidity"].mean())
            else:
                self._infer_air = self._infer_track = self._infer_hum = None

        # Rival initial cumulative times encode starting grid positions.
        # A rival at grid P(k) relative to ego at P(start_pos):
        #   - ahead (k < start_pos): negative offset → lower cum time → "already ahead"
        #   - behind (k > start_pos): positive offset → higher cum time → "already behind"
        rival_positions = [p for p in range(1, _GRID_SIZE + 1) if p != start_pos]
        self._rival_cum = np.array(
            [(rp - start_pos) * _GAP_PER_POS_S for rp in rival_positions],
            dtype=np.float64,
        )

        return self._obs(), {}

    # ── step ───────────────────────────────────────────────────────────────────

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        assert self.action_space.contains(action), f"Invalid action: {action}"
        completed_lap = self._lap_num
        action_was_invalid = False

        # (a) Validate — pitting into the same compound is illegal, treat as stay
        if action in _ACTION_COMPOUND:
            target = _ACTION_COMPOUND[action]
            if target == self._compound:
                logger.debug(
                    "Invalid pit action %d: already on %s — treating as stay",
                    action, self._compound,
                )
                action_was_invalid = True
                action = 0

        # (b) Predict lap time with XGBoost + compound dynamics
        laps_left_after = self._total_laps - self._lap_num   # laps remaining after this one
        lap_time = predict_lap_time(
            driver=self._driver,
            circuit=self._circuit,
            compound=self._compound,
            tire_age=self._tire_age,
            stint_number=self._stint_num,
            fuel_load=self._fuel_kg,
            position=float(self._position),
            laps_remaining=float(laps_left_after),
            is_wet=bool(self._weather.get("is_wet", False)),
            air_temp=self._weather.get("air_temp") or self._infer_air,
            track_temp=self._weather.get("track_temp") or self._infer_track,
            humidity=self._weather.get("humidity") or self._infer_hum,
            year=self._year,
        )
        # Fresh-tyre offset (applied uniformly each lap, matching Phase 3.3 convention)
        lap_time += COMPOUND_FRESH_TIRE_OFFSET_S.get(self._compound, 0.0)
        # Post-cliff degradation penalty
        laps_past_cliff = max(0, self._tire_age - COMPOUND_CLIFF_LAP.get(self._compound, 999))
        lap_time += laps_past_cliff * COMPOUND_CLIFF_PENALTY_S.get(self._compound, 0.0)

        # (c) Handle pit action: add 22s penalty, change compound
        #     Set tire_age=0 now; the unconditional increment below will make it 1
        pit_this_lap = action != 0
        if pit_this_lap:
            lap_time += _PIT_LOSS_S
            new_cpd = _ACTION_COMPOUND[action]
            self._compound  = new_cpd
            self._tire_age  = 0   # becomes 1 after increment
            self._stint_num += 1
            self._used_cpds.add(new_cpd)
            if new_cpd != self._start_cpd:
                self._has_2nd = True

        # (d) Burn fuel
        self._fuel_kg = max(0.0, self._fuel_kg - _FUEL_BURN_KG_PER_LAP)

        # (e) Advance lap counters — tire_age increments regardless (0→1 after pit, k→k+1 otherwise)
        self._cum_time  += lap_time
        self._lap_num   += 1
        self._tire_age  += 1

        # (f) Update position via cumulative-time rank against pitting rivals.
        #     Rivals run pace_s1 until their pit lap, absorb 22s on that lap,
        #     then run pace_s2 for the remainder.
        if completed_lap < self._rival_pit_lap:
            rival_this_lap = self._rival_pace_s1
        elif completed_lap == self._rival_pit_lap:
            rival_this_lap = self._rival_pace_s1 + _PIT_LOSS_S
        else:
            rival_this_lap = self._rival_pace_s2
        self._rival_cum += rival_this_lap
        n_ahead = int(np.sum(self._rival_cum < self._cum_time))
        self._position  = n_ahead + 1

        # Cache for render / info
        self._last_lap_time      = lap_time
        self._last_pit           = pit_this_lap
        self._last_completed_lap = completed_lap

        # (g) Reward placeholder — Phase 4.2
        reward = -lap_time

        # (h) Terminal / truncated
        terminated = self._lap_num > self._total_laps
        truncated  = False

        if terminated and self._two_compound_rule:
            dry_used = self._used_cpds & {"SOFT", "MEDIUM", "HARD"}
            self._violated_rule = len(dry_used) < 2

        # (i) Info
        info: dict[str, Any] = {
            "lap_time":                   self._last_lap_time,
            "cumulative_race_time":       self._cum_time,
            "tire_age":                   self._tire_age,
            "compound":                   self._compound,
            "position":                   self._position,
            "pit_this_lap":               pit_this_lap,
            "violated_two_compound_rule": self._violated_rule,
            "action_was_invalid":         action_was_invalid,
            "laps_past_cliff":            laps_past_cliff,
            "fuel_kg":                    self._fuel_kg,
        }

        if self.render_mode == "human":
            self.render()

        return self._obs(), reward, terminated, truncated, info

    # ── helpers ────────────────────────────────────────────────────────────────

    def _obs(self) -> np.ndarray:
        compound_oh = np.zeros(5, dtype=np.float32)
        compound_oh[_COMPOUND_IDX.get(self._compound, 0)] = 1.0

        laps_remaining   = float(max(0, self._total_laps - self._lap_num + 1))
        laps_past_cliff  = float(
            max(0, self._tire_age - COMPOUND_CLIFF_LAP.get(self._compound, 999))
        )
        lap_fraction = float(
            min(1.0, (self._lap_num - 1) / max(1, self._total_laps))
        )

        return np.array([
            lap_fraction,
            *compound_oh,
            float(self._tire_age),
            float(self._stint_num),
            float(self._fuel_kg),
            float(self._position),
            laps_remaining,
            laps_past_cliff,
            float(int(self._has_2nd)),
        ], dtype=np.float32)

    # ── render ─────────────────────────────────────────────────────────────────

    def render(self) -> str | None:
        cum_m  = int(self._cum_time // 60)
        cum_s  = self._cum_time % 60
        line = (
            f"Lap {self._last_completed_lap:2d}/{self._total_laps} | "
            f"P{self._position:<2d} | "
            f"{self._compound} (age {self._tire_age}) | "
            f"Fuel {self._fuel_kg:5.1f}kg | "
            f"Lap {self._last_lap_time:.3f}s | "
            f"Cum {cum_m}:{cum_s:06.3f}"
            + (" [PIT]" if self._last_pit else "")
        )
        if self.render_mode == "human":
            print(line)
        return line

    def close(self) -> None:
        pass
