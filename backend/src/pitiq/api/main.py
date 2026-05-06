"""PitIQ FastAPI application — Phase 6.2: data/lookup + sandbox inference endpoints.

Run:
    uvicorn pitiq.api.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from stable_baselines3 import PPO

from pitiq.api.schemas import (
    CircuitInfo,
    DegradationCurveRequest,
    DegradationCurveResponse,
    DriverInfo,
    HealthResponse,
    HistoricalRace,
    LapData,
    PitStop,
    PPORecommendRequest,
    PPORecommendResponse,
    SimulateRequest,
    SimulateResponse,
)
from pitiq.envs.sandbox import SandboxRaceEnv
from pitiq.ml.compound_constants import COMPOUND_CLIFF_LAP
from pitiq.ml.predict import load_model, predict_degradation_curve

_REPO_ROOT  = Path(__file__).parents[4]
_DATA_DIR   = _REPO_ROOT / "data" / "features"
_MODELS_DIR = _REPO_ROOT / "models"

# ── Static lookup tables ──────────────────────────────────────────────────────

_CIRCUIT_META: dict[str, dict] = {
    "Bahrain Grand Prix":        {"length_km": 5.412, "type": "permanent", "pit_loss_s": 22.0},
    "Saudi Arabian Grand Prix":  {"length_km": 6.174, "type": "street",    "pit_loss_s": 24.0},
    "Australian Grand Prix":     {"length_km": 5.278, "type": "permanent", "pit_loss_s": 24.0},
    "Japanese Grand Prix":       {"length_km": 5.807, "type": "permanent", "pit_loss_s": 22.0},
    "Chinese Grand Prix":        {"length_km": 5.451, "type": "permanent", "pit_loss_s": 22.0},
    "Miami Grand Prix":          {"length_km": 5.412, "type": "street",    "pit_loss_s": 24.0},
    "Emilia Romagna Grand Prix": {"length_km": 4.909, "type": "permanent", "pit_loss_s": 22.0},
    "Monaco Grand Prix":         {"length_km": 3.337, "type": "street",    "pit_loss_s": 28.0},
    "Canadian Grand Prix":       {"length_km": 4.361, "type": "street",    "pit_loss_s": 24.0},
    "Spanish Grand Prix":        {"length_km": 4.675, "type": "permanent", "pit_loss_s": 21.0},
    "Austrian Grand Prix":       {"length_km": 4.318, "type": "permanent", "pit_loss_s": 20.0},
    "Styrian Grand Prix":        {"length_km": 4.318, "type": "permanent", "pit_loss_s": 20.0},
    "British Grand Prix":        {"length_km": 5.891, "type": "permanent", "pit_loss_s": 21.0},
    "Hungarian Grand Prix":      {"length_km": 4.381, "type": "permanent", "pit_loss_s": 22.0},
    "Belgian Grand Prix":        {"length_km": 7.004, "type": "permanent", "pit_loss_s": 21.0},
    "Dutch Grand Prix":          {"length_km": 4.259, "type": "permanent", "pit_loss_s": 20.0},
    "Italian Grand Prix":        {"length_km": 5.793, "type": "permanent", "pit_loss_s": 23.0},
    "Azerbaijan Grand Prix":     {"length_km": 6.003, "type": "street",    "pit_loss_s": 25.0},
    "Singapore Grand Prix":      {"length_km": 4.940, "type": "street",    "pit_loss_s": 28.0},
    "United States Grand Prix":  {"length_km": 5.513, "type": "permanent", "pit_loss_s": 22.0},
    "Mexico City Grand Prix":    {"length_km": 4.304, "type": "permanent", "pit_loss_s": 22.0},
    "São Paulo Grand Prix":      {"length_km": 4.309, "type": "permanent", "pit_loss_s": 22.0},
    "Las Vegas Grand Prix":      {"length_km": 6.201, "type": "street",    "pit_loss_s": 26.0},
    "Qatar Grand Prix":          {"length_km": 5.380, "type": "permanent", "pit_loss_s": 22.0},
    "Abu Dhabi Grand Prix":      {"length_km": 5.281, "type": "permanent", "pit_loss_s": 22.0},
    "Portuguese Grand Prix":     {"length_km": 4.684, "type": "permanent", "pit_loss_s": 21.0},
    "French Grand Prix":         {"length_km": 5.842, "type": "permanent", "pit_loss_s": 21.0},
    "Turkish Grand Prix":        {"length_km": 5.338, "type": "permanent", "pit_loss_s": 22.0},
    "Russian Grand Prix":        {"length_km": 5.848, "type": "street",    "pit_loss_s": 24.0},
}

# Derived from actual race data (median max lap number per circuit)
_TOTAL_LAPS_TYPICAL: dict[str, int] = {
    "Abu Dhabi Grand Prix":      58,
    "Australian Grand Prix":     57,
    "Austrian Grand Prix":       71,
    "Azerbaijan Grand Prix":     51,
    "Bahrain Grand Prix":        57,
    "Belgian Grand Prix":        44,
    "British Grand Prix":        52,
    "Canadian Grand Prix":       70,
    "Chinese Grand Prix":        56,
    "Dutch Grand Prix":          72,
    "Emilia Romagna Grand Prix": 63,
    "French Grand Prix":         53,
    "Hungarian Grand Prix":      70,
    "Italian Grand Prix":        53,
    "Japanese Grand Prix":       53,
    "Las Vegas Grand Prix":      50,
    "Mexico City Grand Prix":    71,
    "Miami Grand Prix":          57,
    "Monaco Grand Prix":         78,
    "Portuguese Grand Prix":     66,
    "Qatar Grand Prix":          57,
    "Russian Grand Prix":        53,
    "Saudi Arabian Grand Prix":  50,
    "Singapore Grand Prix":      62,
    "Spanish Grand Prix":        66,
    "Styrian Grand Prix":        71,
    "São Paulo Grand Prix":      71,
    "Turkish Grand Prix":        58,
    "United States Grand Prix":  56,
}

# Driver code → (full name, team as of 2024 or last known team)
_DRIVER_META: dict[str, tuple[str, str]] = {
    "VER": ("Max Verstappen",        "Red Bull Racing"),
    "PER": ("Sergio Perez",          "Red Bull Racing"),
    "LEC": ("Charles Leclerc",       "Ferrari"),
    "SAI": ("Carlos Sainz",          "Ferrari"),
    "HAM": ("Lewis Hamilton",        "Mercedes"),
    "RUS": ("George Russell",        "Mercedes"),
    "NOR": ("Lando Norris",          "McLaren"),
    "PIA": ("Oscar Piastri",         "McLaren"),
    "ALO": ("Fernando Alonso",       "Aston Martin"),
    "STR": ("Lance Stroll",          "Aston Martin"),
    "OCO": ("Esteban Ocon",          "Alpine"),
    "GAS": ("Pierre Gasly",          "Alpine"),
    "BOT": ("Valtteri Bottas",       "Kick Sauber"),
    "ZHO": ("Guanyu Zhou",           "Kick Sauber"),
    "TSU": ("Yuki Tsunoda",          "RB"),
    "RIC": ("Daniel Ricciardo",      "RB"),
    "ALB": ("Alexander Albon",       "Williams"),
    "SAR": ("Logan Sargeant",        "Williams"),
    "MAG": ("Kevin Magnussen",       "Haas"),
    "HUL": ("Nico Hulkenberg",       "Haas"),
    "VET": ("Sebastian Vettel",      "Aston Martin"),
    "RAI": ("Kimi Raikkonen",        "Alfa Romeo"),
    "GIO": ("Antonio Giovinazzi",    "Alfa Romeo"),
    "MSC": ("Mick Schumacher",       "Haas"),
    "MAZ": ("Nikita Mazepin",        "Haas"),
    "LAT": ("Nicholas Latifi",       "Williams"),
    "ANT": ("Andrea Kimi Antonelli", "Mercedes"),
    "LAW": ("Liam Lawson",           "Racing Bulls"),
    "HAD": ("Isack Hadjar",          "Racing Bulls"),
    "BEA": ("Oliver Bearman",        "Haas"),
    "BOR": ("Gabriel Bortoleto",     "Sauber"),
    "DEV": ("Nyck de Vries",         "Williams"),
    "COL": ("Franco Colapinto",      "Williams"),
}

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="PitIQ API",
    description="F1 Race Strategy ML Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    lap_features   = pd.read_parquet(_DATA_DIR / "lap_features.parquet")
    driver_styles  = pd.read_parquet(_DATA_DIR / "driver_styles.parquet")

    # Per-circuit available years (computed once)
    circuit_years: dict[str, list[int]] = {
        name: sorted(int(y) for y in grp["Year"].unique())
        for name, grp in lap_features.groupby("EventName")
    }

    # K-means cluster assignments (k=4, matches Phase 2.5.2)
    style_cols = driver_styles.columns.tolist()
    X_raw = driver_styles[style_cols].copy()
    X_filled = X_raw.fillna(X_raw.median())
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X_filled)
    km = KMeans(n_clusters=4, random_state=42, n_init=10)
    labels = km.fit_predict(X_scaled)
    cluster_map: dict[str, int] = {
        code: int(labels[i]) for i, code in enumerate(driver_styles.index)
    }

    # XGBoost model — warms lru_cache; circuit_defaults used for weather fallback
    _, _, _, xgb_circuit_defaults = load_model()

    # PPO Sandbox agent
    ppo_sandbox = PPO.load(_MODELS_DIR / "ppo_sandbox_best.zip")

    # Thread pool for synchronous env execution in async handlers
    executor = ThreadPoolExecutor(max_workers=4)

    app.state.lap_features        = lap_features
    app.state.driver_styles       = driver_styles
    app.state.circuit_years       = circuit_years
    app.state.cluster_map         = cluster_map
    app.state.xgb_circuit_defaults = xgb_circuit_defaults
    app.state.ppo_sandbox         = ppo_sandbox
    app.state.executor            = executor


@app.on_event("shutdown")
async def shutdown() -> None:
    app.state.executor.shutdown(wait=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _circuit_info(name: str) -> CircuitInfo:
    meta = _CIRCUIT_META[name]
    return CircuitInfo(
        name=name,
        length_km=meta["length_km"],
        circuit_type=meta["type"],
        pit_loss_s=meta["pit_loss_s"],
        is_street_circuit=(meta["type"] == "street"),
        total_laps_typical=_TOTAL_LAPS_TYPICAL.get(name, 57),
        available_years=app.state.circuit_years.get(name, []),
    )


def _driver_info(code: str) -> DriverInfo:
    styles = app.state.driver_styles
    if code not in styles.index:
        raise HTTPException(status_code=404, detail=f"Driver '{code}' not found")
    row = styles.loc[code]
    full_name, team = _DRIVER_META.get(code, (code, "Unknown"))
    style_vector = {
        col: (None if pd.isna(val) else float(val))
        for col, val in row.items()
    }
    return DriverInfo(
        code=code,
        full_name=full_name,
        team_2024=team,
        style_vector=style_vector,
        cluster=app.state.cluster_map.get(code, -1),
    )


def _find_circuit(name_raw: str) -> str:
    """Case-insensitive exact match against known circuit names."""
    for known in _CIRCUIT_META:
        if known.lower() == name_raw.lower():
            return known
    raise HTTPException(status_code=404, detail=f"Circuit '{name_raw}' not found")


def _reconstruct_strategy(df_winner: pd.DataFrame, min_stint_laps: int = 5) -> list[dict]:
    """Return pit-stop entries from genuine stint transitions.

    Stints shorter than min_stint_laps are skipped — these are VSC artifacts
    or FastF1 data glitches where a driver briefly shows a new Stint number
    without a real pit stop having occurred.

    Each entry: {"lap": N, "compound": "X"} where N is the lap the driver
    pitted at the end of (new compound starts on lap N+1).
    """
    df_sorted = df_winner.sort_values("LapNumber").drop_duplicates("LapNumber")

    # First lap of each stint + stint length
    stint_firsts = df_sorted.drop_duplicates("Stint", keep="first").sort_values("LapNumber")
    stint_lengths = df_sorted.groupby("Stint")["LapNumber"].count()

    strategy: list[dict] = []

    for _, row in stint_firsts.iterrows():
        stint   = row["Stint"]
        compound = str(row["Compound"])
        lap      = int(row["LapNumber"])

        if stint_lengths.get(stint, 0) < min_stint_laps:
            continue  # VSC artifact or data glitch — not a real pit stop

        if not strategy:
            strategy.append({"lap": 1, "compound": compound})
        else:
            strategy.append({"lap": lap - 1, "compound": compound})

    return strategy


def _build_grid(df_race: pd.DataFrame) -> list[str]:
    first = df_race.sort_values("LapNumber").groupby("Driver").first().reset_index()
    return (
        first.sort_values("Position")["Driver"].tolist()
    )


def _build_results(df_race: pd.DataFrame) -> list[dict]:
    last  = df_race.sort_values("LapNumber").groupby("Driver").last().reset_index()
    first = df_race.sort_values("LapNumber").groupby("Driver").first().reset_index()
    start_pos = first.set_index("Driver")["Position"].to_dict()

    rows = []
    for _, row in last.iterrows():
        driver = row["Driver"]
        rows.append({
            "driver":   driver,
            "position": int(row["Position"]),
            "start":    int(start_pos.get(driver, row["Position"])),
        })
    return sorted(rows, key=lambda x: x["position"])


def _confidence(circuit_name: str) -> str:
    """Predict confidence based on number of training seasons for this circuit."""
    years = app.state.circuit_years.get(circuit_name, [])
    train_years = [y for y in years if y <= 2024]
    if len(train_years) >= 3:
        return "high"
    elif len(train_years) <= 1:
        return "low"
    return "medium"


def _weather_for(circuit: str, year: int | None) -> dict:
    """Best-effort weather lookup: exact (circuit, year) → circuit mean → defaults."""
    defaults = app.state.xgb_circuit_defaults.get(circuit, {})
    if year is not None:
        df = app.state.lap_features
        sub = df[(df["EventName"] == circuit) & (df["Year"] == year)]
        if len(sub) >= 5:
            return {
                "air_temp":   float(sub["air_temp"].mean()),
                "track_temp": float(sub["track_temp"].mean()),
                "humidity":   float(sub["humidity"].mean()),
                "is_wet":     bool(sub["is_wet"].mode().iloc[0]) if "is_wet" in sub.columns else False,
            }
    return {
        "air_temp":   defaults.get("air_temp",   25.0),
        "track_temp": defaults.get("track_temp", 35.0),
        "humidity":   defaults.get("humidity",   50.0),
        "is_wet":     False,
    }


# ── Sync env runners (executed in thread pool) ────────────────────────────────

def _run_simulate_sync(
    driver: str,
    circuit: str,
    starting_compound: str,
    starting_position: int,
    pit_action_map: dict[int, int],
    total_laps: int,
    year: int,
) -> dict:
    env = SandboxRaceEnv()
    obs, _ = env.reset(options={
        "circuit":             circuit,
        "driver":              driver,
        "year":                year,
        "total_laps":          total_laps,
        "starting_position":   starting_position,
        "starting_compound":   starting_compound,
        "two_compound_rule_enforced": True,
    })

    lap_by_lap: list[dict] = []
    pit_stops_executed: list[dict] = []
    lap_num = 1
    terminated = truncated = False
    info: dict = {}

    while not (terminated or truncated):
        action = pit_action_map.get(lap_num, 0)
        obs, _, terminated, truncated, info = env.step(action)
        lap_by_lap.append({
            "lap":      lap_num,
            "compound": info["compound"],
            "tire_age": int(info["tire_age"]),
            "lap_time": round(float(info["lap_time"]), 3),
            "position": int(info["position"]),
        })
        if info.get("pit_this_lap"):
            pit_stops_executed.append({"lap": lap_num, "compound": info["compound"]})
        lap_num += 1

    env.close()
    return {
        "final_position":    int(info.get("position", 20)),
        "race_time_s":       round(float(info.get("cumulative_race_time", 0.0)), 1),
        "pit_stops_executed": pit_stops_executed,
        "lap_by_lap":        lap_by_lap,
    }


def _run_recommend_sync(
    driver: str,
    circuit: str,
    starting_compound: str,
    starting_position: int,
    total_laps: int,
    year: int,
    ppo_model: PPO,
) -> dict:
    env = SandboxRaceEnv()
    obs, _ = env.reset(options={
        "circuit":             circuit,
        "driver":              driver,
        "year":                year,
        "total_laps":          total_laps,
        "starting_position":   starting_position,
        "starting_compound":   starting_compound,
        "two_compound_rule_enforced": True,
    })

    lap_by_lap: list[dict] = []
    pit_stops: list[dict] = []
    lap_num = 1
    terminated = truncated = False
    info: dict = {}

    while not (terminated or truncated):
        action, _ = ppo_model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(int(action))
        lap_by_lap.append({
            "lap":      lap_num,
            "compound": info["compound"],
            "tire_age": int(info["tire_age"]),
            "lap_time": round(float(info["lap_time"]), 3),
            "position": int(info["position"]),
        })
        if info.get("pit_this_lap"):
            pit_stops.append({"lap": lap_num, "compound": info["compound"]})
        lap_num += 1

    env.close()
    return {
        "recommended_pit_stops": pit_stops,
        "final_position":        int(info.get("position", 20)),
        "race_time_s":           round(float(info.get("cumulative_race_time", 0.0)), 1),
        "lap_by_lap":            lap_by_lap,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")


@app.get("/api/circuits", response_model=list[CircuitInfo])
async def get_circuits() -> list[CircuitInfo]:
    return [_circuit_info(name) for name in sorted(_CIRCUIT_META)]


@app.get("/api/circuits/{circuit_name}", response_model=CircuitInfo)
async def get_circuit(circuit_name: str) -> CircuitInfo:
    name = _find_circuit(circuit_name)
    return _circuit_info(name)


@app.get("/api/drivers", response_model=list[DriverInfo])
async def get_drivers() -> list[DriverInfo]:
    return [_driver_info(code) for code in sorted(app.state.driver_styles.index)]


@app.get("/api/drivers/{driver_code}", response_model=DriverInfo)
async def get_driver(driver_code: str) -> DriverInfo:
    return _driver_info(driver_code.upper())


@app.get("/api/historical/{year}/{circuit_name}", response_model=HistoricalRace)
async def get_historical_race(year: int, circuit_name: str) -> HistoricalRace:
    circuit = _find_circuit(circuit_name)
    df = app.state.lap_features
    race = df[(df["Year"] == year) & (df["EventName"] == circuit)]

    if race.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data for {year} {circuit}",
        )

    round_number = int(race["RoundNumber"].iloc[0])
    total_laps   = int(race["LapNumber"].max())

    # Winner: driver with position 1 at their last recorded lap
    last_laps = race.sort_values("LapNumber").groupby("Driver").last()
    winner    = last_laps["Position"].idxmin()

    # Strategy from stint transitions
    df_winner = race[race["Driver"] == winner]
    winner_strategy = _reconstruct_strategy(df_winner)

    # Race time: sum of winner's lap times
    race_time_s = float(df_winner["LapTime"].dropna().sum())

    grid    = _build_grid(race)
    results = _build_results(race)

    return HistoricalRace(
        year=year,
        circuit=circuit,
        round_number=round_number,
        winner=winner,
        winner_strategy=winner_strategy,
        total_laps=total_laps,
        race_time_s=round(race_time_s, 1),
        grid=grid,
        results=results,
    )


@app.get("/api/historical/{year}/{circuit_name}/grid", response_model=list[str])
async def get_historical_grid(year: int, circuit_name: str) -> list[str]:
    circuit = _find_circuit(circuit_name)
    df = app.state.lap_features
    race = df[(df["Year"] == year) & (df["EventName"] == circuit)]

    if race.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No data for {year} {circuit}",
        )

    return _build_grid(race)


# ── Phase 6.2 — Sandbox inference endpoints ───────────────────────────────────

@app.post("/api/sandbox/degradation-curve", response_model=DegradationCurveResponse)
async def sandbox_degradation_curve(
    req: DegradationCurveRequest,
) -> DegradationCurveResponse:
    circuit       = _find_circuit(req.circuit)
    total_laps    = req.total_race_laps or _TOTAL_LAPS_TYPICAL.get(circuit, 57)
    weather       = _weather_for(circuit, req.year)
    compound_up   = req.compound.upper()

    lap_times = predict_degradation_curve(
        driver=req.driver.upper(),
        circuit=circuit,
        compound=compound_up,
        stint_start_lap=req.stint_start_lap,
        stint_length=req.stint_length,
        total_race_laps=total_laps,
        apply_compound_dynamics=True,
        air_temp=weather["air_temp"],
        track_temp=weather["track_temp"],
        humidity=weather["humidity"],
        is_wet=weather["is_wet"],
        year=req.year or 2024,
    )

    return DegradationCurveResponse(
        driver=req.driver.upper(),
        circuit=circuit,
        compound=compound_up,
        lap_times=[round(t, 3) for t in lap_times],
        cliff_lap=COMPOUND_CLIFF_LAP.get(compound_up, 999),
        confidence=_confidence(circuit),
    )


@app.post("/api/sandbox/simulate", response_model=SimulateResponse)
async def sandbox_simulate(req: SimulateRequest) -> SimulateResponse:
    circuit    = _find_circuit(req.circuit)
    total_laps = req.total_laps or _TOTAL_LAPS_TYPICAL.get(circuit, 57)
    year       = req.year or 2024

    _COMPOUND_ACTION = {"SOFT": 1, "MEDIUM": 2, "HARD": 3}
    pit_action_map: dict[int, int] = {}
    for ps in req.pit_stops:
        compound_up = ps.compound.upper()
        if compound_up not in _COMPOUND_ACTION:
            raise HTTPException(status_code=422, detail=f"Unknown compound: {ps.compound}")
        pit_action_map[ps.lap] = _COMPOUND_ACTION[compound_up]

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        app.state.executor,
        lambda: _run_simulate_sync(
            driver=req.driver.upper(),
            circuit=circuit,
            starting_compound=req.starting_compound.upper(),
            starting_position=req.starting_position,
            pit_action_map=pit_action_map,
            total_laps=total_laps,
            year=year,
        ),
    )
    return SimulateResponse(**result)


@app.post("/api/sandbox/recommend", response_model=PPORecommendResponse)
async def sandbox_recommend(req: PPORecommendRequest) -> PPORecommendResponse:
    circuit    = _find_circuit(req.circuit)
    total_laps = req.total_laps or _TOTAL_LAPS_TYPICAL.get(circuit, 57)
    year       = req.year or 2024
    ppo_model  = app.state.ppo_sandbox

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        app.state.executor,
        lambda: _run_recommend_sync(
            driver=req.driver.upper(),
            circuit=circuit,
            starting_compound=req.starting_compound.upper(),
            starting_position=req.starting_position,
            total_laps=total_laps,
            year=year,
            ppo_model=ppo_model,
        ),
    )
    return PPORecommendResponse(**result)
