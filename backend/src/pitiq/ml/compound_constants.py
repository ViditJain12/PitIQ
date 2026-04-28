"""Compound dynamics constants for Phase 4 RaceEnv.

These are hardcoded modifiers applied ON TOP of the XGBoost lap-time
predictions to capture compound dynamics that the lap-time model doesn't
distinguish. Phase 3.3 found that MEDIUM and HARD produce identical XGBoost
predictions (Compound_HARD gain ≈ 0.000036, below the model's split
threshold). The pace model is accurate for SOFT vs non-SOFT and for overall
lap-time magnitudes; MEDIUM/HARD differentiation and post-cliff degradation
are handled here.

This mirrors real F1 strategy software architecture: separate models for
pace and tyre durability, combined at the simulator layer.

Usage (Phase 4 RaceEnv):
    from pitiq.ml.compound_constants import (
        COMPOUND_CLIFF_LAP,
        COMPOUND_CLIFF_PENALTY_S,
        COMPOUND_FRESH_TIRE_OFFSET_S,
    )
    base_lap_time = xgb_model.predict(...)
    offset        = COMPOUND_FRESH_TIRE_OFFSET_S[compound]
    cliff_lap     = COMPOUND_CLIFF_LAP[compound]
    penalty_per_lap = COMPOUND_CLIFF_PENALTY_S[compound]
    laps_past_cliff = max(0, tire_age - cliff_lap)
    lap_time = base_lap_time + offset + laps_past_cliff * penalty_per_lap
"""

# Approximate stint lap at which performance cliff begins, by compound.
# Sourced from industry standard strategy estimates (Pirelli guidance, Heilmeier
# et al. 2020, Motorsport analyst consensus). Actual cliff varies by circuit and
# ambient conditions; these are representative mid-field values.
COMPOUND_CLIFF_LAP: dict[str, int] = {
    "SOFT":         18,
    "MEDIUM":       32,
    "HARD":         45,
    "INTERMEDIATE": 25,
    "WET":          20,
}

# Lap-time penalty (seconds) added per lap PAST the cliff.
# Represents the degradation acceleration once the tyre leaves its thermal
# operating window. Applied multiplicatively with laps_past_cliff.
COMPOUND_CLIFF_PENALTY_S: dict[str, float] = {
    "SOFT":         0.15,
    "MEDIUM":       0.10,
    "HARD":         0.06,
    "INTERMEDIATE": 0.20,
    "WET":          0.20,
}

# Lap-time offset on a FRESH tyre vs MEDIUM baseline (seconds).
# Negative = faster than MEDIUM on a new set; positive = slower.
# Applied once at tire_age = 1, fading as the tyre ages (handled by the
# cliff model above converging compounds toward the same pace post-cliff).
COMPOUND_FRESH_TIRE_OFFSET_S: dict[str, float] = {
    "SOFT":         -0.4,
    "MEDIUM":        0.0,
    "HARD":         +0.3,
    "INTERMEDIATE": +2.0,
    "WET":          +5.0,
}
