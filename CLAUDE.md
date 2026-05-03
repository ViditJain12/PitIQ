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
- ⏭️ Phases 4.5.3–11 planned — see `ROADMAP.md`

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
