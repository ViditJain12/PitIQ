"""Pydantic request/response schemas for PitIQ API (Phase 6.1 + 6.2)."""

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


# ── Phase 6.2 — Sandbox inference schemas ─────────────────────────────────────

class DegradationCurveRequest(BaseModel):
    driver: str
    circuit: str
    compound: str
    stint_start_lap: int = 1
    stint_length: int = 30
    total_race_laps: int | None = None
    year: int | None = None


class DegradationCurveResponse(BaseModel):
    driver: str
    circuit: str
    compound: str
    lap_times: list[float]
    cliff_lap: int
    confidence: str


class PitStop(BaseModel):
    lap: int
    compound: str


class LapData(BaseModel):
    lap: int
    compound: str
    tire_age: int
    lap_time: float
    position: int


class SimulateRequest(BaseModel):
    driver: str
    circuit: str
    starting_compound: str
    starting_position: int = 1
    pit_stops: list[PitStop] = []
    year: int | None = None
    total_laps: int | None = None


class SimulateResponse(BaseModel):
    final_position: int
    race_time_s: float
    pit_stops_executed: list[PitStop]
    lap_by_lap: list[LapData]


class PPORecommendRequest(BaseModel):
    driver: str
    circuit: str
    starting_compound: str
    starting_position: int = 1
    year: int | None = None
    total_laps: int | None = None


class PPORecommendResponse(BaseModel):
    recommended_pit_stops: list[PitStop]
    final_position: int
    race_time_s: float
    lap_by_lap: list[LapData]
