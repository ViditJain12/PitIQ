# PitIQ — How It Works
---

## The Problem

F1 pit strategy is genuinely hard. You're deciding when to swap tires under time pressure, with incomplete information about what 19 rivals are doing, on a track where a 2-second pit window can flip the race result. Real teams have dedicated strategy engineers running simulations on proprietary tools.

PitIQ recreates a simplified but mechanically honest version of that system:

- **Sandbox mode** — single-car simulation. Pick a driver, circuit, and pit strategy. Get a predicted finish position.
- **Optimizer mode** — full 20-car simulation. A reinforcement learning agent recommends the optimal pit strategy for your chosen driver, accounting for rival behavior, undercut/overcut windows, and traffic.

The technical novelty is **driver style fingerprinting**: every lap time prediction is personalized to the specific driver's tire degradation habits, cornering aggression, and wet-weather skill. This makes the models behave differently for Verstappen vs Zhou at the same circuit — which is what actually happens in real life.

---

## System Architecture

```
FastF1 API (historical race data)
    │
    ▼
Data Pipeline          → laps_all.parquet (~108K clean laps, 2021–2025)
    │
    ▼
Feature Engineering    → lap_features.parquet (39 columns per lap)
    │
    ├──────────────────────────────────────────────────┐
    ▼                                                  ▼
Driver Style Module    →  driver_styles.parquet     XGBoost Lap Time Model
(11 features/driver)      (33 drivers × 11 dims)   (trained on lap_features)
    │                                                  │
    └─────────────────────────────────────────────────►│
                                                       ▼
                                            Styled XGBoost (61 features)
                                            MAE: 1.32s overall, 1.07s stable
                                                       │
                              ┌────────────────────────┼──────────────────────┐
                              ▼                         ▼                      ▼
                    SandboxRaceEnv           GridRaceEnv              Rival Pit Policy
                    (1-car, 13-dim obs)      (20-car, 25-dim obs)     (XGBClassifier)
                              │                         │
                              ▼                         ▼
                    PPO Sandbox Agent        PPO Grid Agent
                    (500K–1M steps)          (1.5M steps, 3-stage curriculum)
                              │                         │
                              └────────────┬────────────┘
                                           ▼
                                    FastAPI Backend
                                    (14 endpoints, Uvicorn)
                                           │
                                           ▼
                                    React Frontend
```

---

## 1. Data Pipeline

**Source:** FastF1, a Python library that pulls official F1 timing and telemetry data.

**What's collected per lap:**
- Lap time, compound (SOFT/MEDIUM/HARD/INTERMEDIATE/WET), tire age (laps on current set), stint number, track status (green/VSC/SC/red flag), weather (air temp, track temp, humidity, wet/dry)
- Telemetry summaries: average throttle %, average brake %, average speed — aggregated to one row per lap to keep the dataset manageable
- Context: driver, circuit, year, round number, grid position, final position

**Cleaning decisions:**
- FastF1 marks each lap `IsAccurate: bool`. Pit laps, out-laps, in-laps, and laps behind a safety car are marked inaccurate. These are dropped.
- Fuel correction: real F1 cars are about 110 kg at race start and burn ~1.8 kg/lap. A full tank is worth roughly 3.2 seconds of lap time across the race. Every lap time is corrected back to a "zero-fuel" equivalent: `corrected_time = raw_lap_time - fuel_kg_remaining × 0.035`. This removes the fuel performance gradient so the model learns tire behavior, not fuel load.
- Result: ~108,000 clean laps across 5 seasons (2021–2025).

**Train/val/test split — by race, not randomly:**
- Train: 2021–2024 (89 races, ~85K laps)
- Val: 2025 R1–R12
- Test: 2025 R13–R24

Random splitting would create data leakage — the model would see some laps from a race in training and others in test. Race-based splitting means the model must generalize to entire unseen races.

---

## 2. Driver Style Fingerprinting

The core insight is that two drivers on the same car, at the same circuit, with the same tire will have different lap time trajectories because their driving style interacts with the tire differently.

**11 features computed per driver across all 5 seasons:**

| Feature | What it measures |
|---|---|
| `pace_trend_soft/medium/hard` | OLS slope of lap time vs tire age for each compound (s/lap). Negative slope = pace improving as track rubbers in outweighs degradation. Less-negative = tire saver. |
| `cornering_aggression` | Average peak brake pressure across all accurate laps. Higher = harder on brakes = harder on tires in braking zones. |
| `throttle_smoothness` | 1 / std(throttle %). Higher = smoother throttle application = less wheelspin = better tire preservation. |
| `wet_skill_delta` | Driver's median lap time vs grid median on WET/INTERMEDIATE compounds. Negative = faster than average in wet. NaN if fewer than 20 wet laps. |
| `tire_saving_coef` | Median of (early-stint pace / late-stint pace) across all stints. > 1.0 = driver runs slower early to preserve tires for later. |
| `overall_pace_rank` | Mean sector ranking across S1/S2/S3 (lower = faster overall). This turns out to carry ~100% of the style model's improvement over the baseline. |
| `sector_relative_s1/s2/s3` | Per-sector rank minus overall rank. Negative = driver specializes in that sector type relative to their own average. Sums to zero. |

**Important nuance on pace_trend:** The slope captures net pace change = tire degradation minus track evolution (rubber build-up onto the racing surface). In Stint 1, track evolution often dominates, so slopes can be negative (pace improving). The relative ordering between drivers is still a valid signal — a less-negative slope means either better tire management or a circuit with weaker track evolution.

**Why this matters:** The XGBoost model trained with these features predicts a VER long-stint MEDIUM as ~1.4 seconds per lap faster than a ZHO long-stint MEDIUM at the same circuit — which matches real-world data. Without style features, both get the same prediction.

---

## 3. Lap Time Prediction (XGBoost)

**Architecture:** A single XGBoost regression model predicting lap time in seconds.

**Input features (61 total):**
- Lap state: `tire_age`, `stint_number`, `fuel_load_estimate`, `laps_remaining`, `position`
- Circuit metadata: `length_km`, `pit_loss_s`, `circuit_type` (street/permanent), `is_wet`, `track_temp`, `air_temp`
- Circuit one-hot: `EventName` one-hot encoded (29 circuits)
- Year and round number (to capture tire compound allocations that change year-to-year)
- All 11 driver style features from Section 2

**Performance:**
- Overall MAE: 1.32s (13.4% better than baseline without style)
- Stable subset (circuits with ≥3 training years): 1.07s MAE
- Sparse subset (Las Vegas, <3 training years): 2.77s MAE

**The MEDIUM/HARD problem:** XGBoost found that `Compound_HARD` has a feature gain of ~0.000036 — essentially zero. The model can't distinguish MEDIUM from HARD lap times from the data alone, because real teams often run similar stint lengths on both compounds and the net pace difference is within the model's noise floor.

**Solution: compound dynamics layer** applied on top of XGBoost predictions:

```
lap_time = xgb_prediction
         + FRESH_TIRE_OFFSET[compound]   # SOFT=-0.4s, MEDIUM=0.0s, HARD=+0.3s
         + max(0, tire_age - CLIFF_LAP[compound]) × CLIFF_PENALTY[compound]
```

Cliff laps: SOFT=18, MEDIUM=32, HARD=45. Cliff penalties: SOFT=0.15s/lap, MEDIUM=0.10s/lap, HARD=0.06s/lap. These are sourced from Pirelli guidance and motorsport analyst consensus. This two-layer approach (statistical model for pace, constants for compound durability) mirrors how real F1 strategy software is structured.

---

## 4. Rival Pit Decision Model

**Problem:** In the GridRaceEnv (Section 6), 19 rivals need to make realistic pit decisions every lap. Hard-coding a fixed pit lap would make the simulation unrealistically predictable — the RL agent would learn to exploit the fixed pattern.

**Approach:** Train an XGBClassifier to predict `pitted_next_lap` (binary: will this driver pit on the following lap?).

**Label construction:** A lap has `pitted_next_lap=1` if the next lap by the same driver in the same race has a different Stint number. Since pit/out-laps are already dropped during cleaning, a Stint change reliably indicates a real pit stop.

**Features (55 total):** Race state (tire_age, laps_past_cliff, laps_remaining, position, fuel_estimate, is_wet, track_temp) + EventName one-hot + Compound one-hot + all 11 driver style features.

**Class imbalance:** Only 3.28% of laps end in a pit stop. This is handled with `scale_pos_weight = n_stay / n_pit ≈ 29.4` — XGBoost internally upweights the minority class. No SMOTE or resampling.

**Calibration:** Raw XGBoost probabilities are overconfident. The model is wrapped in isotonic regression calibration (fitted on the validation set). This matters because during simulation, rivals SAMPLE from the calibrated probability rather than taking the argmax — uncalibrated probabilities would produce either too-frequent or too-rare pitting.

**Performance:** AUC-ROC 0.777. All 11 driver style features appear in the importance ranking — this is the first task where driver style produces a clear, direct contribution (aggressive drivers pit earlier in high-degradation stints, tire savers extend stints longer).

---

## 5. Single-Car Race Environment (Sandbox Mode)

**Type:** Custom Gymnasium environment. Follows the standard `reset() → step() → terminated` Gymnasium API so it works as a drop-in with any RL library.

**Observation space (13 dimensions, float32):**

| Dim | Feature | Range |
|---|---|---|
| 0 | `lap_fraction` | [0, 1] — how far through the race |
| 1–5 | `compound_one_hot` | one-hot over SOFT/MEDIUM/HARD/INTERMEDIATE/WET |
| 6 | `tire_age` | [1, 50] laps on current set |
| 7 | `stint_number` | [1, 8] |
| 8 | `fuel_estimate_kg` | [0, 110] |
| 9 | `position` | [1, 20] |
| 10 | `laps_remaining` | [0, 100] |
| 11 | `laps_past_cliff` | max(0, tire_age − cliff_lap) |
| 12 | `has_used_2nd_compound` | 0 or 1 — F1 two-compound rule compliance |

**Action space:** Discrete(4) — stay, pit for SOFT, pit for MEDIUM, pit for HARD.

**Step logic (in order each lap):**
1. Predict lap time via styled XGBoost + compound dynamics layer
2. If pit action: add 22s pit stop time, reset tire_age to 1, change compound. Block same-compound pitting (invalid action).
3. Fuel decreases by 1.8 kg/lap
4. Position updated via cumulative time delta: ego's cumulative race time vs 19 static rival pace estimates (sourced from historical training data for the chosen circuit and year). If ego is faster by enough laps to theoretically overtake, position improves.
5. Reward computed (see below)
6. Terminated when `laps_remaining == 0`

**Reward function:**
```
per_step = (positions_gained_this_lap × 0.5)
         + (-0.05 if pitted else 0)            # discourage unnecessary stops
         + (-0.10 × laps_past_cliff)            # penalize tire abuse
         + (-2.0 if invalid_action else 0)      # heavy penalty for illegal moves

terminal = (-final_position × 2.0)             # P1 → -2, P20 → -40
         + (+10 if two_compound_rule_met else -100)
```

**Limitation:** Rivals are static — they follow a precomputed average pace profile, not a real agent. This means the env correctly simulates tire strategy decisions but can't model undercuts or traffic dynamics. That's what the GridRaceEnv (Section 6) is for.

---

## 6. Multi-Car Grid Environment (Optimizer Mode)

**Type:** Same Gymnasium interface as Sandbox, but all 20 cars run simultaneously.

**Observation space (25 dimensions):** The 13 ego-state dims from Sandbox, plus 12 rival-context dims:

| Dims | Feature |
|---|---|
| 13 | gap to rival directly ahead (seconds) |
| 14 | rival ahead's compound index |
| 15 | rival ahead's tire age |
| 16 | rival ahead's pace rank (from driver style) |
| 17 | rival ahead's tire saving coefficient |
| 18–22 | same five features for rival directly behind |
| 23 | `undercut_window_open` — gap ahead < 2.5s and rival is on older tires |
| 24 | `defending_against_undercut` — rival behind < 1.5s behind on fresh tires |

Sentinel values are used when ego is P1 (no rival ahead) or P20 (no rival behind).

**Per-step logic:**
1. Ego agent acts (stay or pit to compound X)
2. All 19 rivals query the calibrated rival pit policy (Section 4) — each rival samples pit/stay from its predicted probability. This stochasticity means the same race plays out differently across seeds, which is realistic and critical for RL generalization.
3. XGBoost lap times predicted for all 20 cars **in a single batch call** (17.6× faster than 20 individual calls)
4. Compound dynamics applied per car
5. Pit penalties applied for cars that pitted this lap
6. Cumulative race times updated
7. Position sorted from cumulative race times — the car with the lowest total time leads
8. Overtaking friction applied: position changes are gated by a per-circuit probability factor (Monaco = 0.05, Monza = 0.90). This prevents simulated Monza from being a free-pass zone and simulated Monaco from ever seeing an overtake.
9. Rival-context observation assembled for ego's next state
10. Undercut/overcut windows detected and logged for the API

**Validation (2024 Bahrain GP, 5 seeds):** 70% of drivers finish within ±3 positions of actual results, 95% within ±5, mean absolute delta 2.06. Verstappen P1 in all 5 seeds.

---

## 7. PPO Training

**Library:** Stable-Baselines3 (PPO implementation). The RL algorithm itself is standard PPO — the novelty is entirely in the environment design and curriculum.

### Sandbox PPO

**Curriculum:**
- Stage 1 (0–300K steps): Bahrain GP, Verstappen, P1 start — the simplest possible scenario
- Stage 2 (300K–1M steps): 4 circuits × 5 drivers × P1–P10 — forced generalization

**Result:** Agent converges to +7.46 eval reward at 100K steps. Near-identical performance to the "cliff-pit" heuristic on the training scenario (pit just before SOFT cliff) — which is correct, because Bahrain P1 with Verstappen IS close to optimal with a single well-timed stop. The 239-point reward gap over never-pit confirms genuine strategy learning.

**Key bug:** On macOS Apple Silicon, PyTorch and Homebrew's libomp conflict, causing a segfault at import time. Fix: `KMP_DUPLICATE_LIB_OK=TRUE` and `OMP_NUM_THREADS=1` set before any imports.

### Grid PPO

**Curriculum:**
- Stage 1 (0–200K steps): Bahrain GP, Verstappen, fixed grid
- Stage 2 (200K–600K steps): Bahrain, 5 drivers, P1–P10
- Stage 3 (600K–1.5M steps): 4 circuits, 5 drivers, P1–P15

**Training speed:** 126 fps (frames per second) — achieved by batching all 20 rival XGBoost calls into one matrix operation per step. Without batching: ~7 fps.

**Result:** Best eval reward +14.89 at 1M steps. On a hard test (Zhou, P15 start, Belgian GP), Grid PPO finishes P8.5 average vs Fixed-strategy P10.4 — the rival-aware agent gains ~2 extra positions by timing undercuts correctly.

### Why two separate agents?

The Sandbox agent can only see its own car's state. The Grid agent sees the 12 additional rival-context dimensions. On mid-grid scenarios (P10–P15), the Sandbox agent degenerates all policies to P20 — it has no information about rivals so it can't identify undercut opportunities. The Grid agent uses that information correctly.

---

## 8. API Layer

**Framework:** FastAPI with Uvicorn. All ML models are loaded once at startup into `app.state` and reused across requests. This avoids cold-start latency on each call.

**14 endpoints across 4 categories:**

**Data lookups** (1–12ms):
- `GET /api/circuits` — 29 circuits with metadata (length, type, pit loss, SVG map points)
- `GET /api/drivers` — 33 drivers with style vectors and cluster assignments
- `GET /api/historical/{year}/{circuit}` — actual race results reconstructed from lap data
- `GET /api/historical/{year}/{circuit}/grid` — starting grid for a given race

**Sandbox simulation:**
- `POST /api/sandbox/simulate` — run user-defined pit strategy through SandboxRaceEnv, returns lap-by-lap trace
- `POST /api/sandbox/recommend` — run PPO Sandbox agent deterministically, returns recommended strategy + trace
- `POST /api/sandbox/degradation-curve` — XGBoost stint simulation for tire degradation preview

**Optimizer simulation:**
- `POST /api/optimizer/simulate` — user-defined strategy through GridRaceEnv, returns lap-by-lap trace + rival predictions + undercut windows
- `POST /api/optimizer/recommend` — PPO Grid agent rollout, returns recommended strategy + strategy rationale text + rival predictions

**Historical validation:**
- `GET /api/optimizer/historical-validation/{year}/{circuit}` — runs GridRaceEnv against actual historical results, returns accuracy metrics (% within ±3/±5 positions)

**Execution model:** The Gymnasium environments are synchronous (they use blocking NumPy operations). FastAPI is async. To avoid blocking the event loop, env simulations run in a `ThreadPoolExecutor` (4 workers). Each request gets its own environment instance — no shared state between concurrent requests.

---

## 9. Key Design Decisions

**Why XGBoost for lap times, not a neural network?**
XGBoost trains in minutes, is interpretable (feature importance is meaningful), and generalizes well on the ~85K training rows we have. A neural network would need careful regularization to avoid overfitting on this dataset size, and the interpretability loss isn't worth it for a feature that needs to be debugged frequently.

**Why PPO, not another RL algorithm?**
PPO is the default workhorse for continuous-action and discrete-action problems with moderate state dimensions. It's stable, well-understood, and has a reliable SB3 implementation. The problem doesn't have any characteristics that would favor SAC (continuous actions, off-policy efficiency) or DQN (the state space benefits from the value function baseline PPO provides).

**Why behavior-cloned rivals instead of rule-based?**
Rule-based rivals (e.g., "pit every N laps") produce systematic exploits — the RL agent learns to time its pit one lap after the rival's fixed window. Real rivals don't have fixed windows. Behavior cloning from 5 seasons of actual pit decisions produces stochastic, style-dependent rivals that are harder to exploit and generalize better to novel circuits.

**Why a two-layer compound model (XGBoost + constants)?**
XGBoost can't learn MEDIUM vs HARD differentiation from the data alone — real teams also run similar stint lengths on both, so the pure-pace signal is too weak. Separating the model into "overall pace prediction" (data-driven) and "compound durability" (domain-knowledge constants) is how real strategy software works. This also makes the constants easy to update when Pirelli releases new compound allocations without retraining the model.

**Why race-based train/val/test splits?**
Random splits create data leakage. If lap 34 of the 2024 Bahrain GP is in training and lap 37 is in test, the model can effectively memorize race-specific conditions (specific track temperature, degradation profile that day) rather than learning generalizable patterns. Race-based splits are stricter — the model must generalize to entire unseen races.

**The single-seed historical validation limitation:**
Historical validation calls the GridRaceEnv once per request (~450ms). The reported 70% within ±3 figure in RESULTS.md is a 5-seed average. Single-seed results are 55–70%, with high variance from stochastic rival behavior. Running 5 seeds in parallel would improve accuracy to ~70% but increase response time to ~1.5s. This is a known trade-off accepted for the demo.

---

## If You Want to Build Your Own Variation

**Easier wins:**
- Swap the XGBoost lap time model for a per-circuit LightGBM model — circuits like Monaco and Singapore have sufficiently different characteristics that a shared model is a meaningful limitation
- Add a safety car model: sample VSC/SC deployment from historical frequency per circuit, apply a randomized lap penalty. This dramatically improves historical validation accuracy on high-chaos races.
- Expand driver style to include qualifying pace delta (how much faster a driver is in qualifying vs race trim) — useful for predicting undercut threat from fast qualifiers stuck in traffic

**Harder extensions:**
- Live race mode: pipe live timing from FastF1's live session API into the GridRaceEnv and run PPO inference in real time during an actual race
- Weather adaptation: train a separate XGBoost model on wet-only laps and switch models mid-race when `is_wet` flips. The current model handles wet conditions but was predominantly trained on dry data.
- Multi-compound stint prediction: the rival pit policy predicts only whether a rival will pit, not which compound they'll switch to. A multi-class extension (stay / SOFT / MEDIUM / HARD) would improve undercut window detection.
