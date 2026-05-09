# PitIQ — Claude Code Context

> **Read this file first at the start of every session.** It's your persistent memory for this project.

---

## What PitIQ Is

A two-mode F1 race strategy ML platform:

1. **Sandbox Mode** — User picks a past race + driver, plays with pit windows, sees predicted finish position. Single-car simulation.
2. **Optimizer Mode** — Engine simulates the *entire grid* with personalized driver style models, then recommends the optimal pit strategy for the chosen driver accounting for rival behavior, undercut/overcut windows, and traffic.

The technical novelty: **driver style fingerprinting** (per-driver tire degradation, cornering aggression, throttle smoothness derived from FastF1 telemetry) + **multi-agent race simulation** + **PPO reinforcement learning** trained in that simulation.

---

## Architecture

```
FastF1 API
    ↓
[Data Pipeline]  →  Cleaned lap + telemetry data
    ↓
[Driver Style Module]  →  Per-driver style vectors (tire deg, aggression, smoothness)
    ↓
[XGBoost Model]  →  Driver-style-aware lap time prediction
    ↓
    ├─→ [Single-Car RaceEnv]  →  [PPO Sandbox Agent]
    └─→ [Multi-Agent GridRaceEnv]  →  [PPO Optimizer Agent]
                                         (rivals use behavior-cloned policies)
    ↓
[FastAPI Backend]  →  /sandbox + /optimize endpoints
    ↓
[React + TypeScript Frontend]  →  Two UI modes
```

---

## Tech Stack

| Layer | Tech |
|---|---|
| Data | FastF1, Pandas, Parquet (local storage) |
| ML | scikit-learn, XGBoost, Stable-Baselines3 (PPO), Gymnasium |
| Backend | FastAPI, Pydantic, Uvicorn |
| Frontend | Vite + React + TypeScript, TailwindCSS, Recharts |
| Infra | Docker, docker-compose |

---

## Project Conventions

- **Python:** 3.11+, type hints required, `ruff` for linting, `pytest` for tests
- **TypeScript:** strict mode, functional React components only, no class components
- **Folder structure:** see `ROADMAP.md` Phase 0
- **Commits:** end of every phase, format: `Phase X.Y complete: <summary>`
- **Models saved to:** `models/` — never committed (in `.gitignore`)
- **Data saved to:** `data/raw/`, `data/processed/`, `data/features/` — never committed
- **Notebooks:** `notebooks/` — exploratory only, never imported by app code

---

## Current Status

- ✅ **Phase 0.1 complete (2026-04-22):** Folder structure, `.gitignore`, `pyproject.toml`, Python venv at `.venv/` (Python 3.13), all base deps installed and verified.
- ✅ **Phase 0.2 complete (2026-04-22):** Vite + React + TypeScript frontend, Tailwind v4, React Router, Recharts, Axios. Dark F1 design tokens. Stub pages for Landing, Sandbox, Optimizer, Results with working routing. `npm run dev` confirmed at `:5173`.
- ✅ **Phase 1.1 complete (2026-04-23):** `pitiq.data.client` — `load_session()` with persistent FastF1 cache, retry + exponential backoff. Cache hit 0.4s vs 5.7s cold (14×). 5/5 tests green.
- ✅ **Phase 1.2 complete (2026-04-23):** `pitiq.data.ingest` — `ingest_season()` + CLI. 24-column schema (17 lap cols + 4 telemetry summaries + 3 context cols), timedeltas as float seconds. Smoke test: 2 races, 2,030 laps, 7/7 tests green.
- ✅ **Phase 1.3 complete (2026-04-23):** 5-season backfill (2021–2025) + `pitiq.data.clean` — `laps_all.parquet` with 108,257 clean laps. Fuel correction validated (mean 1.659s, range 0–3.246s, monotonicity check passed on all rows). 9/9 tests green.
- ✅ **Phase 1 complete.** Data pipeline end-to-end: FastF1 → per-session cache → per-season Parquet → cleaned combined dataset.
- ✅ **Phase 2.1 complete (2026-04-23):** `pitiq.features.build` — 39-column `lap_features.parquet` (108,257 rows). Features: tire_age, stint_number, fuel_load_estimate, laps_remaining, position + circuit metadata (29/29 matched) + session-level weather. Three verification checks passed. 14/14 tests green.
- ✅ **Phase 2.2 complete (2026-04-24):** `pitiq.features.split` — race-based train/val/test split (train: 2021–2024 85,214 laps 89 races; val: 2025 R1–12 11,103 laps; test: 2025 R13–24 11,940 laps). 8/8 tests green. `notebooks/01_eda.ipynb` — 6-section EDA: missing data audit, compound usage, tire degradation (controlled conditions with documented limitations), lap time distributions, wet vs dry (compound-based), split summary. Wet penalty validated at +8.13s overall, all 11 wet-circuit deltas positive.
- ✅ **Phase 2 complete.** Feature engineering end-to-end: cleaned laps → 39-column feature set → race-based splits → EDA validated.
- ✅ **Phase 2.5.1 complete (2026-04-24):** `pitiq.styles.build` — 33-driver style vectors, 11 features: `pace_trend_{soft,medium,hard}`, `cornering_aggression`, `throttle_smoothness`, `wet_skill_delta` (race-normalised, ≥20 wet laps), `tire_saving_coef`, `overall_pace_rank`, `sector_relative_{s1,s2,s3}`. Saved to `data/features/driver_styles.parquet`. Wet delta validated: VER −1.11s, rookies ~+0.4s, ZHO +3.6s confirmed genuine.
- ✅ **Phase 2.5.2 complete (2026-04-24):** `notebooks/02_driver_styles.ipynb` — full validation suite: summary table, 4 radar comparisons, k-means clustering (k=4, silhouette 0.151), PCA scatter, correlation heatmap. Caught and fixed sector_profile redundancy (3 features r=0.99 → decomposed into overall_pace_rank + sector_relative×3, now r=−0.40 to −0.55). Feature set finalised at 11 dimensions.
- ✅ **Phase 2.5 complete.** Driver style fingerprinting end-to-end: feature computation → race-normalised deltas → validation notebook.
- ✅ **Phase 3.1 complete (2026-04-26):** `pitiq.ml.train_xgboost` — XGBoost baseline lap time model (no driver style features). 50 features: numeric lap/circuit features + EventName one-hot + Year/RoundNumber. Test set: 6 stratified races (2024–2025). **Stable subset MAE (≥3 train years, 5 circuits, 4,402 laps): 1.11s. Sparse subset MAE (<3 train years, Las Vegas only, 760 laps): 3.91s. Overall: 1.53s.** Artifacts: `models/xgb_baseline.pkl`, `models/xgb_baseline_meta.json`, `models/figures/baseline_feature_importance.png`. Split restructured to explicit stratified race selection in `pitiq.features.split`.
- ✅ **Phase 3.2 complete (2026-04-27):** `pitiq.ml.train_xgboost --styled` — driver-style-aware XGBoost (61 features: baseline + 11 style vectors). **Overall MAE: 1.32s (−13.4% vs baseline). Stable: 1.07s. Sparse: 2.77s.** Ablation confirmed `overall_pace_rank` carries ~100% of improvement; other 10 style features retained for Phase 4.5+ behavioral tasks. Production model: `models/xgb_styled.pkl`. Ablation artifact: `models/xgb_styled_no_pace_rank.pkl`.
- ✅ **Phase 3.3 complete (2026-04-27):** `pitiq.ml.predict` — `load_model()`, `predict_lap_time()`, `predict_degradation_curve()`, `degradation_curve_to_json()`. `pitiq.ml.compound_constants` — COMPOUND_CLIFF_LAP/PENALTY/FRESH_TIRE_OFFSET dicts. Validated: VER vs HAM +1.391s over 25-lap MEDIUM stint at Monza. MEDIUM=HARD identical in pure model (by design — Compound_HARD gain ≈ 0.000036). With `apply_compound_dynamics=True`: SOFT cliff visible by lap 23, MEDIUM vs HARD differentiated by −0.300s at lap 1, HARD +0.30s offset. Artifacts: `models/figures/degradation_curves_validation.png`.
- ✅ **Phase 3 complete.** XGBoost lap-time prediction end-to-end: baseline → style-augmented → ablation-verified → degradation curve API + compound dynamics layer. Styled model is the production predictor for Sandbox/Optimizer.
- ✅ **Phase 4.1 complete (2026-04-28):** `pitiq.envs.sandbox` — `SandboxRaceEnv` Gymnasium env. 13-dim obs (lap_fraction, compound one-hot×5, tire_age, stint_num, fuel_kg, position, laps_remaining, laps_past_cliff, has_2nd_compound), Discrete(4) actions. Rival model: 1-stop profile (pace_s1, pace_s2, median_pit_lap) from top-10 training data with year fallback; year-specific weather lookup to keep XGBoost in-distribution. Two-compound rule, invalid-action guard, compound dynamics (fresh-tire offset + cliff penalty). Validation: 10/10 checks passed across Monza (4-strategy) + 5-circuit polesitter test. `pitiq.envs.test_sandbox_manual` — manual validation script.
- ✅ **Phase 4.2 complete (2026-04-30):** Reward function in `SandboxRaceEnv.step()` — `position_delta×0.5 + pit_cost(−0.05) + cliff_penalty(−0.10/lap) + invalid_action_penalty(−2.0) + pace_reward(pace_delta×0.05) + terminal(−pos×2 ± rule_bonus)`. `RewardLogger` helper for per-step component logging. `notebooks/03_sandbox_env.ipynb` — 4-scenario validation (Monza, Bahrain, Monaco, reward shape). All assertions pass with pace_reward. SNR=7.2× (well above PPO threshold). Known limitation: cumulative-time position model over-penalises aggressive strategies at Monaco/Singapore (deferred to Phase 4.5 GridRaceEnv). Reward shape figure: `models/figures/reward_shape_monza_optimal.png`.
- ✅ **Phase 4 complete.** Single-car race environment end-to-end: env skeleton → reward function → validated across 4 strategic scenarios.
- ✅ **Phase 4.5.1 complete (2026-05-01):** `pitiq.ml.rival_policy` — XGBClassifier rival pit-decision model. Label: `pitted_next_lap` from Stint changes in lap_features. 55 features: race state (tire_age, laps_past_cliff, laps_remaining, position, fuel_estimate, is_wet, track_temp) + EventName one-hot + Compound one-hot + all 11 driver style features. scale_pos_weight=29.4 (3.28% pit rate). Isotonic calibration on val set + probability clipped to [0.001, 0.95] for stochastic sampling. **AUC-ROC: 0.777 (target >0.75).** All 4 domain sanity checks pass. All 11 style features in importance ranking — first task where Phase 2.5 driver style work shows clear contribution. Artifacts: `models/rival_pit_policy.pkl`, `models/rival_pit_policy_meta.json`, `models/figures/rival_pit_*.png`.
- ✅ **Phase 4.5.2 complete (2026-05-02):** `pitiq.envs.grid` — `GridRaceEnv` 20-car Gymnasium environment for Optimizer Mode. Built in 4 parts: (1) `Car` dataclass + `reset()` with style-vector initialisation; (2) full `step()` — per-car XGBoost lap times, compound dynamics, pit penalties, cumulative-time position sort; (3) `rival_pit_policy` integration + per-circuit overtaking friction (`pitiq.envs.grid_constants.OVERTAKING_DIFFICULTY`); (4) validation against actual 2024 Bahrain GP results across 5 seeds. **Accuracy: 70% of drivers within ±3 positions, 95% within ±5, mean |delta| 2.06.** Race time −2.2% vs actual 5408s. VER P1 in 5/5 runs. 20/20 two-compound rule compliance. Stochastic rival behavior confirmed: pit laps vary by seed, ZHO pits earlier than NOR on average (driver style signal). Validation scripts: `test_grid_part1/2/3/4.py`. `pitiq.envs.grid_constants` — `OVERTAKING_DIFFICULTY` per-circuit dict.
- ✅ **Phase 4.5.3 complete (2026-05-03):** `GridRaceEnv` ego observation expanded from 13-dim to 25-dim with 12 new rival-context features. New dims [13-24]: `gap_to_rival_ahead_s`, `rival_ahead_cmp_idx`, `rival_ahead_tire_age`, `rival_ahead_pace_rank`, `rival_ahead_tire_save` (×1 for rival ahead) + mirrored set for rival behind + `undercut_window_open` + `defending_against_undercut` boolean flags. Sentinel values for P1 (no rival ahead) and P20 (no rival behind): gap=30.0, compound=0, tire_age=0, pace_rank=33, tire_saving=0.5. `_compute_rival_context()` method with NaN-safe style-vector lookup. Validation: 16/16 assertions pass across 2 races (VER P1 at laps 1/10/17/19/30/56 + PER P4 at lap 5). `test_grid_part5.py` — labeled 25-dim observation printer.
- ✅ **Phase 4 + Phase 4.5 fully complete.** End-to-end: SandboxRaceEnv (13-dim obs, reward function) → rival behavior cloning (XGBClassifier AUC=0.777) → GridRaceEnv (20-car simulation, 70%/±3 Bahrain accuracy) → rival-aware 25-dim observation space for PPO training.
- ✅ **Phase 5.1 complete (2026-05-04):** `pitiq.ml.train_ppo_sandbox` — PPO agent trained on `SandboxRaceEnv`. Curriculum: Stage 1 (0–300K, Bahrain VER P1, converged to +7.46 eval reward at 100K), Stage 2 (300K–1M, 4 circuits × 5 drivers × P1–P10, stabilised +7.64–8.15). 52-minute total training run. **Baseline comparison (Bahrain VER P1, 10 eps):** PPO +8.15 ≈ cliff-pit +8.67 (both P1 10/10 wins), never-pit −231, random −104. Near-identical PPO vs cliff-pit is correct — Bahrain P1 VER is the simplest possible scenario where a well-timed SOFT cliff pit is near-optimal; PPO discovered this independently from reward signal. 239-point margin vs never-pit confirms genuine strategy learning. Artifacts: `models/ppo_sandbox_final.zip`, `models/ppo_sandbox_best.zip`, `models/figures/sandbox_training_curve.png`, `models/figures/sandbox_baseline_comparison.png`. macOS Apple Silicon fix: `KMP_DUPLICATE_LIB_OK=TRUE` + `OMP_NUM_THREADS=1` before imports (Homebrew libomp × PyTorch OpenMP conflict).
- ✅ **Phase 5.2 complete (2026-05-06):** `pitiq.ml.train_ppo_grid` — PPO agent trained on `GridRaceEnv` (rival-aware 25-dim obs). 3-stage curriculum: Stage 1 (0–200K, Bahrain VER P1 fixed grid), Stage 2 (200K–600K, Bahrain 5 drivers P1–P10), Stage 3 (600K–1.5M, 4 circuits 5 drivers P1–P15). 3.29-hour training run, 126 fps (achieved via `predict_lap_times_batch` + `predict_pit_probabilities_batch` — 17.6× speedup over naive per-car XGBoost calls). **Best eval: +14.89 at 1M steps** (plateau +14.81–14.89 from 600K onward). Stage 1→2 dip to −22.64 recovered within 100K steps; Stage 2→3 clean (no regression). **Baseline comparison (Bahrain VER P1, 10 eps):** Grid PPO +14.87 / P1.0 / 10/10 wins, Sandbox PPO +14.23 / P1.0 / 10/10 wins, Fixed (lap 18) +14.67 / P1.0 / 10/10 wins, Random −93.22 / P20.0 / 0/10. **ZHO P15:** Grid PPO P8.5, Sandbox PPO P7.3, Fixed P10.4 — learned policies outperform heuristics by ~3 positions in complex scenario. Batch prediction functions added to `pitiq.ml.predict` and `pitiq.ml.rival_policy`. Artifacts: `models/ppo_grid_final.zip`, `models/ppo_grid_best.zip`, `models/figures/grid_training_curve.png`, `models/figures/grid_baseline_comparison.png`.
- ✅ **Phase 5.3 complete (2026-05-06):** `pitiq.ml.evaluate` — comprehensive evaluation harness. 8 scenarios (4 sandbox + 4 grid) × 4 policies × 20 episodes = 640 total episodes. **Grid PPO results:** Italian NOR P3 +9.47/P1/100% (vs Fixed +6.88/P1.8/35%), Belgian HAM P6 +11.54/P1.4/70% (vs Fixed +3.88/P4.0/0%), Bahrain ZHO P15 P8.3/+6.7 gained (both learned policies beat Fixed P10.3/+4.7). **Sandbox PPO:** correctly solves Bahrain VER P1 (+8.15, P1, 100%) but defaults to never-pit at out-of-distribution circuits (Italian P3, Belgian P6 MEDIUM starts). **Key finding:** GridRaceEnv required for mid-grid evaluation — SandboxRaceEnv degenerates all policies to P20 for P15 starts (static rival model limitation). `docs/RESULTS.md` written. Artifacts: `models/evaluation_results.json`, `models/figures/eval_position_gains.png`, `models/figures/eval_reward_comparison.png`.
- ✅ **Phase 5 complete.** Full RL pipeline end-to-end: SandboxRaceEnv → PPO Sandbox agent → GridRaceEnv (20-car, rival-aware) → PPO Grid agent → comprehensive evaluation harness + RESULTS.md.
- ✅ **Phase 6.1 complete (2026-05-06):** `pitiq.api.main` + `pitiq.api.schemas` — FastAPI backend, data/lookup endpoints. 8 endpoints: `GET /health`, `/api/circuits`, `/api/circuits/{name}`, `/api/drivers`, `/api/drivers/{code}`, `/api/historical/{year}/{circuit}`, `/api/historical/{year}/{circuit}/grid`. Parquet files loaded into `app.state` at startup — response times 1–2ms (lookup) / 12ms (historical reconstruction). Data validated against actual 2024 Bahrain GP: correct VER winner, correct 20-car grid order, correct final positions, correct 3-stint strategy. VSC artifact fix: stints < 5 laps filtered from winner_strategy. Swagger UI at `/docs`.
- ✅ **Phase 6.2 complete (2026-05-06):** 3 new ML inference endpoints added to `pitiq.api.main`. `POST /api/sandbox/degradation-curve` — XGBoost stint simulation with compound dynamics, cliff_lap + confidence fields. `POST /api/sandbox/simulate` — user-specified pit strategy executed through SandboxRaceEnv via thread pool (returns per-lap compound/tire_age/lap_time/position). `POST /api/sandbox/recommend` — PPO Sandbox agent run deterministically, returns recommended pit stops + full lap-by-lap trace. ThreadPoolExecutor(max_workers=4) for sync env execution in async handlers. Validated: VER Bahrain SOFT→HARD@18 = P1/5411s; PPO recommends 2-stop (MEDIUM@20, SOFT@50) = P1/5415s.
- ✅ **Phase 6.3 complete (2026-05-07):** 3 Optimizer Mode endpoints complete. `POST /api/optimizer/simulate` — user-specified ego strategy through GridRaceEnv (full 20-car sim, rival pit history, undercut window detection). `POST /api/optimizer/recommend` — PPO Grid agent deterministic rollout with `strategy_rationale` template generation referencing actual rivals and tire ages. `GET /api/optimizer/historical-validation/{year}/{circuit}` — GridRaceEnv sim vs actual finishing positions, `X-Simulation-Time-Ms` response header. Validated: ZHO P15 → P7 (+8 positions, 2-stop MEDIUM@22/SOFT@43); SAI undercut windows correctly detected (age 26–28, gap 1.26–1.32s); historical validation 55% within ±3 (single-seed, 448ms response). **Phase 6 backend complete — 14 endpoints total.** See `ROADMAP.md` Phase 7 for frontend.
- ✅ **Phase 7.1 complete (2026-05-07):** Shared frontend infrastructure. Design system: `tokens.css` (--color-accent #E8002D, --font-display Barlow Condensed 900, --font-mono JetBrains Mono, --radius 0px), Google Fonts loaded, global CSS resets + scanline/scan-bar keyframes. API client: `src/api/client.ts` — typed fetch wrapper for all 13 endpoints. TypeScript types: `src/api/types.ts` mirrors all Phase 6 Pydantic schemas. Zustand store: circuits, drivers, selectedCircuit/Driver/Year/Mode. 6 shared components: `TireBadge` (SVG tire icon + compound color), `DriverBadge` (team-color left border), `LapTimeline` (Recharts AreaChart + pit stop reference lines), `StatCard`, `LoadingState` (scan-bar animation), `ConfidenceBadge`. `App.tsx` updated: `/historical` route + global `getCircuits/getDrivers` on mount. `Landing.tsx` rewritten: CSS grid background, animated scanline, "WHAT'S YOUR STRATEGY?" headline, live stat strip, two mode cards. TypeScript 0 errors. API verified: 29 circuits returned from browser console.
- ✅ **Phase 7.2 complete (2026-05-08):** Sandbox Mode UI at `/sandbox`. 40/60 split layout. Season-aware dropdowns (circuit + driver filtered by year via `/api/season/{year}/circuits|drivers`). 3-step form: Race Selection, Driver Setup, Pit Stop Configuration (up to 4 stops). SIMULATE and GET AI PICK buttons. Results panel: mode badge + confidence + ppo_note, stat cards (position/time/delta/stops), pit stop summary chips, compound-colored stint bar, Recharts lap time chart (compound ReferenceAreas + pit ReferenceLine markers), stint summary table with deg/lap. Backend additions: `_validate_and_fix_strategy()` PPO output post-processor, `_ppo_note()` agent quality signal, position gain sanity cap, two new season endpoints. Bugs fixed: OOD never-pit, negative deg/lap, season-agnostic dropdowns, position cap for multi-stop.
- ✅ **Phase 8.1 complete (2026-05-08):** Optimizer Mode UI at `/optimizer`. 35/65 split layout. Season-aware form (circuit, year, ego driver, grid position, starting compound). Two actions: OPTIMIZE STRATEGY (PPO Grid agent via `/api/optimizer/recommend`) and SIMULATE MY STRATEGY (modal pit configurator → `/api/optimizer/simulate`). Loading spinner with 4 cycling messages (1.5s interval): RUNNING GRID SIMULATION → MODELING RIVAL BEHAVIOR → COMPUTING UNDERCUT WINDOWS → OPTIMIZING YOUR STRATEGY. Results: strategy header (mode badge + confidence + strategy rationale), stat cards, pit stop chips, compound stint bar, lap time chart, Grid Position Tracker (Recharts LineChart, 20 lines, ego=red/2.5px, rivals=grey/1px, Y-axis domain [1,20] reversed, custom tooltip top-6 by position), Rival Predictions (sorted by finish, with disclaimer, pit history TireBadges), Undercut Windows (gap < 0.5s → TIGHT BATTLE in orange, ≥0.5s → UNDERCUT in yellow). Bug fixed: historical grids with <20 drivers (e.g. Australian GP 2024 returns 19) now padded to 20 from season roster — GridRaceEnv requires exactly 20.
- ✅ **Phase 8.2 complete (2026-05-09):** Driver Style Inspector — slide-in panel (`src/components/DriverStylePanel.tsx`) accessible from both Sandbox and Optimizer pages via "VIEW STYLE →" link below the driver dropdown. Panel content: comparison driver dropdown (defaults to next-slower by pace rank), Recharts RadarChart (6 axes: Pace, Tire Saving, Wet Skill, Smoothness, Aggression, Consistency — normalized min/max against full 33-driver roster from `store.drivers`, not season-filtered list; ego=red/30% fill, comparison=grey/12% fill overlaid), auto-generated insight line (3 cases: faster by >5 ranks / better tire manager / similar profiles), two-column driver detail (cluster badge, 5 metric bars with normalized fill, sector profile S1–S3 in green/white, pace trends per compound). Closes on × button, Escape, or mousedown outside (uses document mousedown listener so form elements behind panel still receive click events). Wet Skill invert: more-negative delta (faster in wet) maps to higher normalized bar. Bug fixes post-initial-commit: (1) normalization was scoped to ~20 season drivers instead of 33 → midfield drivers all normalized to ~0.5 on every axis → fixed by adding `normDrivers` prop sourced from global `store.drivers`; (2) RadarChart rendered tiny with no explicit `outerRadius` or `domain` → fixed with `outerRadius={100}`, `height={300}`, `PolarRadiusAxis domain={[0,1]}`; (3) Optimizer position change ignored → `buildGridParams()` now swaps ego driver to user-specified position before sending grid array to backend (GridRaceEnv asserts `starting_grid[ego_starting_position-1] === ego_driver`); (4) SIMULATE MY STRATEGY "failed to fetch" was the position mismatch causing a backend ValueError.
- ✅ **Phase 9.1 complete (2026-05-09):** Historical Validation page at `/historical`. Full-width layout (no sidebar). Race picker (year + circuit dropdowns, season-aware). `GET /api/optimizer/historical-validation/{year}/{circuit}` on submit. Accuracy stat cards with `valueColor` (≥60% green, 40–60% yellow, <40% red). Color-coded delta badges: exact=green "✓", ±1–2=green, ±3=yellow, ±4–5=orange, >5=red "±N ✗". Side-by-side actual vs simulated results table with `ResultRow` component. `LargeDeltaCallout` for drivers with |delta| > 3 — looks up `KNOWN_INCIDENTS` dict keyed by `"${year}_${circuit}"` for specific notes (RIC 2024 Bahrain, RUS/VER/NOR 2024 Austrian GP, HAM/NOR 2024 British GP, LEC 2024 Monaco), falls back to generic text. `CHAOTIC_RACE_NOTES` dict drives a yellow warning banner (shown on circuit select, before running) for known high-variance races. Context note paragraph below table explains single-seed variance. Navigation additions: HISTORICAL → link added to Sandbox and Optimizer navbars; Landing page updated from 2-column to 3-column mode cards with HISTORICAL as third card.
- ⏭️ Phase 10 next — Polish + deploy. See `ROADMAP.md`.

_Update this section at the end of every phase._

---

## Key Decisions Log Pointer

See `docs/DECISIONS.md` for architectural choices and their rationale.
See `docs/PHASE_NOTES.md` for per-phase retrospectives.

---

## Working Style With Me (Claude Code)

- One phase chunk per session — don't bleed into the next
- After every chunk: update this file's Current Status, append to PHASE_NOTES.md, commit
- When metrics are bad, ask me to explain what's happening before changing code
- Reference ROADMAP.md for the next chunk's scope — don't improvise scope
- **Commit authorship:** Do not add `Co-Authored-By: Claude` lines. All commits should be authored solely by me.
