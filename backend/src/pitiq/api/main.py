"""PitIQ FastAPI application — data/lookup and ML inference endpoints.

Run:
    uvicorn pitiq.api.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import os
import time
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from stable_baselines3 import PPO

from pitiq.api.schemas import (
    CircuitInfo,
    DegradationCurveRequest,
    DegradationCurveResponse,
    DriverInfo,
    GridSimulateRequest,
    GridSimulateResponse,
    HealthResponse,
    HistoricalRace,
    HistoricalValidationResponse,
    LapData,
    OptimizerRecommendRequest,
    OptimizerRecommendResponse,
    PitStop,
    PPORecommendRequest,
    PPORecommendResponse,
    RivalPrediction,
    SimulateRequest,
    SimulateResponse,
)
from pitiq.envs.grid import GridRaceEnv
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

_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ───────────────────────────────────────────────────────────────────

# Load parquet data, cluster drivers, warm model caches, and store state on app startup.
@app.on_event("startup")
async def startup() -> None:
    import json as _json
    lap_features   = pd.read_parquet(_DATA_DIR / "lap_features.parquet")
    driver_styles  = pd.read_parquet(_DATA_DIR / "driver_styles.parquet")
    circuit_maps_path = _DATA_DIR / "circuit_maps.json"
    circuit_maps: dict[str, dict] = {}
    if circuit_maps_path.exists():
        with open(circuit_maps_path) as f:
            circuit_maps = _json.load(f)

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

    # PPO Grid agent (Optimizer Mode)
    ppo_grid = PPO.load(_MODELS_DIR / "ppo_grid_best.zip")

    # Thread pool for synchronous env execution in async handlers
    executor = ThreadPoolExecutor(max_workers=4)

    app.state.lap_features         = lap_features
    app.state.driver_styles        = driver_styles
    app.state.circuit_years        = circuit_years
    app.state.cluster_map          = cluster_map
    app.state.circuit_maps         = circuit_maps
    app.state.xgb_circuit_defaults = xgb_circuit_defaults
    app.state.ppo_sandbox          = ppo_sandbox
    app.state.ppo_grid             = ppo_grid
    app.state.executor             = executor


# Shut down the thread pool executor gracefully on app shutdown.
@app.on_event("shutdown")
async def shutdown() -> None:
    app.state.executor.shutdown(wait=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

# Build a CircuitInfo response object for the given circuit name.
def _circuit_info(name: str) -> CircuitInfo:
    meta = _CIRCUIT_META[name]
    cmap = app.state.circuit_maps.get(name, {})
    return CircuitInfo(
        name=name,
        length_km=meta["length_km"],
        circuit_type=meta["type"],
        pit_loss_s=meta["pit_loss_s"],
        is_street_circuit=(meta["type"] == "street"),
        total_laps_typical=_TOTAL_LAPS_TYPICAL.get(name, 57),
        available_years=app.state.circuit_years.get(name, []),
        svg_points=cmap.get("svg_points"),
        viewBox=cmap.get("viewBox"),
    )


# Build a DriverInfo response object for the given driver code, raising 404 if not found.
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


# Return the ordered starting grid as a list of driver codes sorted by first-lap position.
def _build_grid(df_race: pd.DataFrame) -> list[str]:
    first = df_race.sort_values("LapNumber").groupby("Driver").first().reset_index()
    return (
        first.sort_values("Position")["Driver"].tolist()
    )


# Build a sorted list of result dicts with driver, final position, and starting position.
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


_GRID_ACTION_COMPOUND: dict[int, str] = {1: "SOFT", 2: "MEDIUM", 3: "HARD"}


# ── Sync env runners (executed in thread pool) ────────────────────────────────

# ── Grid helpers ──────────────────────────────────────────────────────────────

# Extract rival driver predictions from a completed GridRaceEnv grid state.
def _rival_predictions_from_grid(
    grid: list,
    ego_driver: str,
    styles_df: pd.DataFrame,
) -> list[dict]:
    preds = []
    for car in grid:
        if car.driver == ego_driver:
            continue
        style_summary: dict = {}
        if car.driver in styles_df.index:
            row = styles_df.loc[car.driver]
            style_summary = {
                "overall_pace_rank": None if pd.isna(row.get("overall_pace_rank", float("nan"))) else float(row["overall_pace_rank"]),
                "tire_saving_coef":  None if pd.isna(row.get("tire_saving_coef",  float("nan"))) else float(row["tire_saving_coef"]),
            }
        preds.append({
            "driver":            car.driver,
            "starting_position": car.starting_position,
            "final_position":    float(car.current_position),
            "pit_history":       [{"lap": lap, "compound": cmp} for lap, cmp in car.pit_history],
            "style_summary":     style_summary,
        })
    return preds


def _check_undercut_window(env: GridRaceEnv, lap_num: int, action: int) -> dict | None:
    """Return undercut window dict if gap < 1.5s, rival ahead tire_age > 20, ego not pitting."""
    if action != 0 or env._ego is None:
        return None
    ego = env._ego
    pos_map = {car.current_position: car for car in env._grid}
    rival_ahead = pos_map.get(ego.current_position - 1)
    if rival_ahead is None:
        return None
    gap = float(max(0.0, ego.cumulative_race_time - rival_ahead.cumulative_race_time))
    if gap < 1.5 and rival_ahead.tire_age > 20:
        return {
            "lap":             lap_num,
            "gap_s":           round(gap, 2),
            "rival_driver":    rival_ahead.driver,
            "rival_tire_age":  int(rival_ahead.tire_age),
        }
    return None


# Generate a natural-language strategy rationale string for the optimizer recommendation.
def _generate_rationale(
    driver: str,
    circuit: str,
    starting_position: int,
    starting_compound: str,
    strategy: list[dict],
    ego_style: dict,
    undercut_windows: list[dict],
    confidence: str,
) -> str:
    parts: list[str] = [f"{driver} starting P{starting_position} on {starting_compound}."]
    if strategy:
        p = strategy[0]
        parts.append(f"Optimal strategy: pit to {p['compound']} on lap {p['lap']}.")
    else:
        parts.append("No pit stops recommended.")
    if undercut_windows:
        uw = undercut_windows[0]
        parts.append(
            f"Rival ahead ({uw.get('rival_driver', 'rival')}) on aging tires "
            f"(age {uw.get('rival_tire_age', 0)}) — undercut window open."
        )
    tsave = ego_style.get("tire_saving_coef")
    if tsave is not None and isinstance(tsave, float) and not pd.isna(tsave) and tsave > 0.99:
        parts.append(f"Tire saving coefficient ({tsave:.3f}) suggests extended stint viable.")
    parts.append(f"Circuit confidence: {confidence} ({circuit}).")
    return " ".join(parts)


# Run a GridRaceEnv episode with a fixed pit action map and return lap-by-lap results.
def _run_grid_simulate_sync(
    ego_driver: str,
    circuit: str,
    starting_compound: str,
    starting_position: int,
    pit_action_map: dict[int, int],
    total_laps: int,
    year: int,
    starting_grid: list[str],
    starting_compounds: dict[str, str],
    weather: dict | None,
    styles_df: pd.DataFrame,
) -> dict:
    env = GridRaceEnv()
    obs, _ = env.reset(options={
        "circuit":               circuit,
        "year":                  year,
        "total_laps":            total_laps,
        "ego_driver":            ego_driver,
        "ego_starting_position": starting_position,
        "starting_grid":         starting_grid,
        "starting_compounds":    starting_compounds,
        "weather":               weather or {},
        "two_compound_rule_enforced": True,
    })

    lap_by_lap: list[dict] = []
    ego_strategy: list[dict] = []
    undercut_windows: list[dict] = []
    lap_num = 1
    terminated = truncated = False
    info: dict = {}

    while not (terminated or truncated):
        action = pit_action_map.get(lap_num, 0)
        uw = _check_undercut_window(env, lap_num, action)
        if uw:
            undercut_windows.append(uw)
        obs, _, terminated, truncated, info = env.step(action)
        lap_by_lap.append({
            "lap":      lap_num,
            "compound": info["ego_compound"],
            "tire_age": int(info["ego_tire_age"]),
            "lap_time": round(float(info["ego_lap_time"]), 3),
            "position": int(info["ego_position"]),
        })
        if action != 0:
            ego_strategy.append({"lap": lap_num, "compound": _GRID_ACTION_COMPOUND[action]})
        lap_num += 1

    ego_car = env._ego
    rival_preds = _rival_predictions_from_grid(env._grid, ego_driver, styles_df)
    env.close()
    return {
        "ego_strategy":                ego_strategy,
        "ego_predicted_position":      float(ego_car.current_position),
        "ego_race_time_s":             round(float(ego_car.cumulative_race_time), 1),
        "ego_lap_by_lap":              lap_by_lap,
        "rival_predictions":           rival_preds,
        "positions_gained":            starting_position - int(ego_car.current_position),
        "undercut_windows_identified": undercut_windows,
    }


# Run a GridRaceEnv episode using the PPO Grid agent and return the recommended strategy.
def _run_grid_recommend_sync(
    ego_driver: str,
    circuit: str,
    starting_compound: str,
    starting_position: int,
    total_laps: int,
    year: int,
    starting_grid: list[str],
    starting_compounds: dict[str, str],
    weather: dict | None,
    ppo_model: PPO,
    styles_df: pd.DataFrame,
) -> dict:
    env = GridRaceEnv()
    obs, _ = env.reset(options={
        "circuit":               circuit,
        "year":                  year,
        "total_laps":            total_laps,
        "ego_driver":            ego_driver,
        "ego_starting_position": starting_position,
        "starting_grid":         starting_grid,
        "starting_compounds":    starting_compounds,
        "weather":               weather or {},
        "two_compound_rule_enforced": True,
    })

    lap_by_lap: list[dict] = []
    recommended_strategy: list[dict] = []
    undercut_windows: list[dict] = []
    lap_num = 1
    terminated = truncated = False
    info: dict = {}

    while not (terminated or truncated):
        action, _ = ppo_model.predict(obs, deterministic=True)
        action = int(action)
        uw = _check_undercut_window(env, lap_num, action)
        if uw:
            undercut_windows.append(uw)
        obs, _, terminated, truncated, info = env.step(action)
        lap_by_lap.append({
            "lap":      lap_num,
            "compound": info["ego_compound"],
            "tire_age": int(info["ego_tire_age"]),
            "lap_time": round(float(info["ego_lap_time"]), 3),
            "position": int(info["ego_position"]),
        })
        if action != 0:
            recommended_strategy.append({"lap": lap_num, "compound": _GRID_ACTION_COMPOUND[action]})
        lap_num += 1

    ego_car = env._ego
    rival_preds = _rival_predictions_from_grid(env._grid, ego_driver, styles_df)
    env.close()
    return {
        "recommended_strategy":        recommended_strategy,
        "predicted_finish_position":   float(ego_car.current_position),
        "race_time_s":                 round(float(ego_car.cumulative_race_time), 1),
        "positions_gained":            starting_position - int(ego_car.current_position),
        "rival_predictions":           rival_preds,
        "undercut_windows_identified": undercut_windows,
        "ego_lap_by_lap":              lap_by_lap,
    }


# Simulate a historical race with GridRaceEnv and compare to actual results for accuracy metrics.
def _run_historical_validation_sync(
    year: int,
    circuit: str,
    lap_features: pd.DataFrame,
    styles_df: pd.DataFrame,
) -> dict:
    race_df = lap_features[(lap_features["Year"] == year) & (lap_features["EventName"] == circuit)]
    if race_df.empty:
        raise ValueError(f"No data for {year} {circuit}")

    total_laps = int(race_df["LapNumber"].max())

    # Build starting grid from first-lap positions
    first_laps = race_df.sort_values("LapNumber").groupby("Driver").first().reset_index()
    starting_grid: list[str] = first_laps.sort_values("Position")["Driver"].tolist()[:20]
    pad_idx = 0
    while len(starting_grid) < 20:
        starting_grid.append(f"PAD{pad_idx:02d}")
        pad_idx += 1

    # Starting compounds per driver
    starting_compounds: dict[str, str] = {}
    for driver in starting_grid:
        if driver.startswith("PAD"):
            starting_compounds[driver] = "SOFT"
            continue
        dlaps = race_df[race_df["Driver"] == driver].sort_values("LapNumber")
        if not dlaps.empty:
            cmp = str(dlaps.iloc[0]["Compound"]).upper()
            starting_compounds[driver] = cmp if cmp in {"SOFT", "MEDIUM", "HARD"} else "SOFT"
        else:
            starting_compounds[driver] = "SOFT"

    # Actual final results
    last_laps  = race_df.sort_values("LapNumber").groupby("Driver").last().reset_index()
    start_pos_map = first_laps.set_index("Driver")["Position"].to_dict()
    actual_results: list[dict] = [
        {
            "driver":            row["Driver"],
            "position":          int(row["Position"]),
            "starting_position": int(start_pos_map.get(row["Driver"], 0)),
        }
        for _, row in last_laps.sort_values("Position").iterrows()
    ]
    actual_pos = {r["driver"]: r["position"] for r in actual_results}

    # Ego = P1 on grid; use cliff-based heuristic (rivals drive via behavior-cloned policy)
    ego_driver = starting_grid[0]
    env = GridRaceEnv()
    env.reset(options={
        "circuit":               circuit,
        "year":                  year,
        "total_laps":            total_laps,
        "ego_driver":            ego_driver,
        "ego_starting_position": 1,
        "starting_grid":         starting_grid,
        "starting_compounds":    starting_compounds,
        "two_compound_rule_enforced": True,
    })

    terminated = truncated = False
    while not (terminated or truncated):
        ego = env._ego
        laps_past_cliff = max(0, ego.tire_age - COMPOUND_CLIFF_LAP.get(ego.compound, 999))
        action = 3 if (laps_past_cliff > 3 and not ego.has_used_2nd_compound) else 0
        _, _, terminated, truncated, _ = env.step(action)

    sim_pos = {car.driver: int(car.current_position) for car in env._grid}
    simulated_results: list[dict] = sorted(
        [{"driver": d, "position": p} for d, p in sim_pos.items() if not d.startswith("PAD")],
        key=lambda x: x["position"],
    )
    env.close()

    # Accuracy vs actuals
    common = [d for d in actual_pos if d in sim_pos and not d.startswith("PAD")]
    if common:
        deltas    = [abs(sim_pos[d] - actual_pos[d]) for d in common]
        within_3  = sum(1 for d in deltas if d <= 3) / len(deltas) * 100.0
        within_5  = sum(1 for d in deltas if d <= 5) / len(deltas) * 100.0
        mean_delta = sum(deltas) / len(deltas)
    else:
        within_3 = within_5 = mean_delta = 0.0

    return {
        "actual_results":        actual_results,
        "simulated_results":     simulated_results,
        "accuracy_pct_within_3": round(within_3, 1),
        "accuracy_pct_within_5": round(within_5, 1),
        "mean_absolute_delta":   round(mean_delta, 2),
    }


# Run a SandboxRaceEnv episode with a fixed pit action map and return lap-by-lap results.
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


def _validate_and_fix_strategy(
    strategy: list[dict],
    starting_compound: str,
    total_laps: int,
) -> tuple[list[dict], bool]:
    """Ensure PPO output satisfies the two-compound rule. Returns (strategy, overridden)."""
    cliff_lap = COMPOUND_CLIFF_LAP.get(starting_compound, 25)

    # Fix 1: agent never pitted
    if len(strategy) == 0:
        fallback = "HARD" if starting_compound != "HARD" else "MEDIUM"
        pit_lap = min(cliff_lap - 2, total_laps - 10)
        strategy = [{"lap": max(2, pit_lap), "compound": fallback}]
        return strategy, True

    # Fix 2: only one compound used across entire race
    compounds_used = {starting_compound} | {s["compound"] for s in strategy}
    if len(compounds_used) < 2:
        fallback = "HARD" if starting_compound == "SOFT" else "SOFT"
        strategy = list(strategy) + [{"lap": total_laps - 8, "compound": fallback}]
        return strategy, True

    return strategy, False


_PPO_MODERATE = frozenset({
    "Italian Grand Prix",
    "Belgian Grand Prix",
    "Abu Dhabi Grand Prix",
    "Australian Grand Prix",
})

# Return a human-readable note about the PPO agent's familiarity with this circuit.
def _ppo_note(circuit: str) -> str:
    if circuit == "Bahrain Grand Prix":
        return "PPO agent trained extensively on this circuit."
    if circuit in _PPO_MODERATE:
        return "PPO agent has moderate familiarity with this circuit."
    return "PPO agent has limited training on this circuit — recommendation may be adjusted."


# Run a SandboxRaceEnv episode using the PPO Sandbox agent and return the recommended strategy.
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

    pit_stops, overridden = _validate_and_fix_strategy(pit_stops, starting_compound, total_laps)

    return {
        "recommended_pit_stops": pit_stops,
        "final_position":        int(info.get("position", 20)),
        "race_time_s":           round(float(info.get("cumulative_race_time", 0.0)), 1),
        "lap_by_lap":            lap_by_lap,
        "strategy_overridden":   overridden,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

# Return API health status.
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0")


# Return all circuit configurations sorted by name.
@app.get("/api/circuits", response_model=list[CircuitInfo])
async def get_circuits() -> list[CircuitInfo]:
    return [_circuit_info(name) for name in sorted(_CIRCUIT_META)]


# Return configuration for a single circuit by name (case-insensitive).
@app.get("/api/circuits/{circuit_name}", response_model=CircuitInfo)
async def get_circuit(circuit_name: str) -> CircuitInfo:
    name = _find_circuit(circuit_name)
    return _circuit_info(name)


# Return all driver info objects sorted by driver code.
@app.get("/api/drivers", response_model=list[DriverInfo])
async def get_drivers() -> list[DriverInfo]:
    return [_driver_info(code) for code in sorted(app.state.driver_styles.index)]


# Return info for a single driver by three-letter code.
@app.get("/api/drivers/{driver_code}", response_model=DriverInfo)
async def get_driver(driver_code: str) -> DriverInfo:
    return _driver_info(driver_code.upper())


# Return historical race data including winner strategy, grid, and results for a given year and circuit.
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


# Return the starting grid as an ordered list of driver codes for a given year and circuit.
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


# Return drivers who competed in a given season, sorted by pace rank.
@app.get("/api/season/{year}/drivers", response_model=list[DriverInfo])
async def get_season_drivers(year: int) -> list[DriverInfo]:
    df = app.state.lap_features
    codes = df[df["Year"] == year]["Driver"].dropna().unique().tolist()
    styles = app.state.driver_styles
    drivers = [_driver_info(code) for code in codes if code in styles.index]
    drivers.sort(key=lambda d: (d.style_vector.get("overall_pace_rank") or 99.0))
    return drivers


# Return circuits included in a given season, sorted alphabetically.
@app.get("/api/season/{year}/circuits", response_model=list[CircuitInfo])
async def get_season_circuits(year: int) -> list[CircuitInfo]:
    df = app.state.lap_features
    names = df[df["Year"] == year]["EventName"].dropna().unique().tolist()
    circuits = [_circuit_info(name) for name in names if name in _CIRCUIT_META]
    return sorted(circuits, key=lambda c: c.name)


# ── Phase 6.2 — Sandbox inference endpoints ───────────────────────────────────

# Return a predicted tire degradation curve for the given driver, circuit, and compound.
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


# Simulate a user-specified pit strategy through SandboxRaceEnv and return lap-by-lap results.
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

    # Position gain sanity cap — static rival model cannot model counter-strategies
    starting_pos = req.starting_position
    max_realistic_gain = int((20 - starting_pos) * 0.4)
    raw_gain = starting_pos - result["final_position"]
    position_capped = raw_gain > max_realistic_gain
    if position_capped:
        result["final_position"] = starting_pos - max_realistic_gain
    result["position_capped"] = position_capped

    return SimulateResponse(**result)


# Run the PPO Sandbox agent deterministically and return the recommended strategy.
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
    result["confidence"] = _confidence(circuit)
    result["ppo_note"]   = _ppo_note(circuit)
    return PPORecommendResponse(**result)


# ── Phase 6.3 — Optimizer Mode endpoints ──────────────────────────────────────

# Simulate a user-specified strategy through GridRaceEnv with all 20 rivals and return results.
@app.post("/api/optimizer/simulate", response_model=GridSimulateResponse)
async def simulate_grid(req: GridSimulateRequest) -> GridSimulateResponse:
    circuit = _find_circuit(req.circuit)

    _COMPOUND_ACTION_LOCAL = {"SOFT": 1, "MEDIUM": 2, "HARD": 3}
    pit_action_map: dict[int, int] = {}
    for ps in req.pit_stops:
        compound_up = str(ps.get("compound", "")).upper()
        lap = int(ps.get("lap", 0))
        if compound_up not in _COMPOUND_ACTION_LOCAL:
            raise HTTPException(status_code=422, detail=f"Unknown compound: {ps.get('compound')}")
        pit_action_map[lap] = _COMPOUND_ACTION_LOCAL[compound_up]

    styles_df  = app.state.driver_styles
    loop       = asyncio.get_event_loop()
    result     = await loop.run_in_executor(
        app.state.executor,
        lambda: _run_grid_simulate_sync(
            ego_driver        = req.ego_driver.upper(),
            circuit           = circuit,
            starting_compound = req.starting_compound.upper(),
            starting_position = req.ego_starting_position,
            pit_action_map    = pit_action_map,
            total_laps        = req.total_laps,
            year              = req.year,
            starting_grid     = [d.upper() for d in req.starting_grid],
            starting_compounds = {k.upper(): v.upper() for k, v in req.starting_compounds.items()},
            weather           = req.weather,
            styles_df         = styles_df,
        ),
    )
    return GridSimulateResponse(
        ego_driver                 = req.ego_driver.upper(),
        circuit                    = circuit,
        ego_strategy               = result["ego_strategy"],
        ego_predicted_position     = result["ego_predicted_position"],
        ego_race_time_s            = result["ego_race_time_s"],
        ego_lap_by_lap             = result["ego_lap_by_lap"],
        rival_predictions          = result["rival_predictions"],
        positions_gained           = result["positions_gained"],
        undercut_windows_identified = result["undercut_windows_identified"],
    )


# Run the PPO Grid agent and return the optimal strategy with rationale and rival predictions.
@app.post("/api/optimizer/recommend", response_model=OptimizerRecommendResponse)
async def recommend_optimizer(req: OptimizerRecommendRequest) -> OptimizerRecommendResponse:
    circuit   = _find_circuit(req.circuit)
    ppo_model = app.state.ppo_grid
    styles_df = app.state.driver_styles
    driver_up = req.ego_driver.upper()

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        app.state.executor,
        lambda: _run_grid_recommend_sync(
            ego_driver        = driver_up,
            circuit           = circuit,
            starting_compound = req.starting_compound.upper(),
            starting_position = req.ego_starting_position,
            total_laps        = req.total_laps,
            year              = req.year,
            starting_grid     = [d.upper() for d in req.starting_grid],
            starting_compounds = {k.upper(): v.upper() for k, v in req.starting_compounds.items()},
            weather           = req.weather,
            ppo_model         = ppo_model,
            styles_df         = styles_df,
        ),
    )

    ego_style: dict = {}
    if driver_up in styles_df.index:
        row = styles_df.loc[driver_up]
        ego_style = {k: (None if pd.isna(v) else float(v)) for k, v in row.items()}

    confidence = _confidence(circuit)
    rationale  = _generate_rationale(
        driver            = driver_up,
        circuit           = circuit,
        starting_position = req.ego_starting_position,
        starting_compound = req.starting_compound.upper(),
        strategy          = result["recommended_strategy"],
        ego_style         = ego_style,
        undercut_windows  = result["undercut_windows_identified"],
        confidence        = confidence,
    )

    return OptimizerRecommendResponse(
        ego_driver                 = driver_up,
        circuit                    = circuit,
        recommended_strategy       = result["recommended_strategy"],
        predicted_finish_position  = result["predicted_finish_position"],
        race_time_s                = result["race_time_s"],
        positions_gained           = result["positions_gained"],
        rival_predictions          = result["rival_predictions"],
        undercut_windows_identified = result["undercut_windows_identified"],
        strategy_rationale         = rationale,
        confidence                 = confidence,
        ego_lap_by_lap             = result["ego_lap_by_lap"],
    )


@app.get(
    "/api/optimizer/historical-validation/{year}/{circuit_name}",
    response_model=HistoricalValidationResponse,
)
# Run a full GridRaceEnv simulation of a historical race and compare to actual results.
async def historical_validation(
    year: int,
    circuit_name: str,
    response: Response,
) -> HistoricalValidationResponse:
    # Heavy endpoint — runs full GridRaceEnv simulation (~3-8s). Call sparingly.
    circuit      = _find_circuit(circuit_name)
    lap_features = app.state.lap_features
    styles_df    = app.state.driver_styles

    t0   = time.monotonic()
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            app.state.executor,
            lambda: _run_historical_validation_sync(year, circuit, lap_features, styles_df),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    response.headers["X-Simulation-Time-Ms"] = str(int((time.monotonic() - t0) * 1000))

    return HistoricalValidationResponse(
        year    = year,
        circuit = circuit,
        **result,
    )
