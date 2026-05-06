"""Pydantic request/response schemas for PitIQ API (Phase 6.1)."""

from pydantic import BaseModel


class CircuitInfo(BaseModel):
    name: str
    length_km: float
    circuit_type: str
    pit_loss_s: float
    is_street_circuit: bool
    total_laps_typical: int
    available_years: list[int]


class DriverInfo(BaseModel):
    code: str
    full_name: str
    team_2024: str
    style_vector: dict[str, float | None]
    cluster: int


class HistoricalRace(BaseModel):
    year: int
    circuit: str
    round_number: int
    winner: str
    winner_strategy: list[dict]
    total_laps: int
    race_time_s: float
    grid: list[str]
    results: list[dict]


class HealthResponse(BaseModel):
    status: str
    version: str
