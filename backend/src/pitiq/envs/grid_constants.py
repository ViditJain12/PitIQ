"""Circuit-level constants for GridRaceEnv.

OVERTAKING_DIFFICULTY: maximum positions a car can gain per lap ON TRACK.
Pit-cycle swaps are exempt — a pitting car can drop (or recover) any number
of positions as it cycles through the pit lane.

Values:
  1   — easy overtaking (multiple DRS zones, big braking points)
  0.5 — moderate (some DRS but physical overtaking is risky)
  0.3 — hard (street-circuit character, few passing opportunities)
  0.1 — near-impossible (Monaco)
"""
from __future__ import annotations

OVERTAKING_DIFFICULTY: dict[str, float] = {
    # Easy overtaking — multiple DRS zones, big braking
    "Bahrain Grand Prix":         1,
    "Italian Grand Prix":         1,
    "Belgian Grand Prix":         1,
    "Saudi Arabian Grand Prix":   1,
    "Azerbaijan Grand Prix":      1,
    "United States Grand Prix":   1,
    "Las Vegas Grand Prix":       1,
    # Moderate overtaking
    "Australian Grand Prix":      0.5,
    "Japanese Grand Prix":        0.5,
    "Spanish Grand Prix":         0.5,
    "British Grand Prix":         0.5,
    "Dutch Grand Prix":           0.5,
    "Chinese Grand Prix":         0.5,
    "Canadian Grand Prix":        0.5,
    "São Paulo Grand Prix":       0.5,
    "Mexico City Grand Prix":     0.5,
    "Abu Dhabi Grand Prix":       0.5,
    "Austrian Grand Prix":        0.5,
    "Qatar Grand Prix":           0.5,
    "Emilia Romagna Grand Prix":  0.5,
    "French Grand Prix":          0.5,
    "Turkish Grand Prix":         0.5,
    "Portuguese Grand Prix":      0.5,
    "Styrian Grand Prix":         0.5,
    # Hard overtaking — street circuits, tight layouts
    "Monaco Grand Prix":          0.1,
    "Singapore Grand Prix":       0.3,
    "Miami Grand Prix":           0.3,
    "Hungarian Grand Prix":       0.3,
    "Russian Grand Prix":         0.3,
    # Default fallback
    "DEFAULT":                    0.5,
}
