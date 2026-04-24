# Phase Notes — Per-Chunk Retrospectives

> Append after every chunk you complete. Keep entries short — what was built, what worked, what didn't, what to remember.

**Format:**
```
## Phase X.Y — [Chunk title] (YYYY-MM-DD)
**Built:** Brief list of what got done
**Worked well:** What went smoothly
**Pain points:** What was hard / what to avoid next time
**Metrics (if applicable):** Concrete numbers
**Open questions:** What you didn't resolve, to revisit later
```

---

## Phase 0.1 — Project Scaffold (2026-04-22)
**Built:**
- Full folder structure: `backend/src/pitiq/{data,features,styles,ml,envs,api}`, `backend/tests/`, `frontend/src/`, `data/`, `models/`, `notebooks/`, `docs/`
- `.gitignore` covering data, models, venv, node_modules, caches, `.env`
- `backend/pyproject.toml` with all base + dev deps, `setuptools.build_meta` build backend
- Python venv at `.venv/` (Python 3.13.2), package installed in editable mode
- `docker-compose.yml` stub
- FastF1 cache dir created at `data/raw/fastf1_cache/`, `fastf1.Cache.enable_cache()` confirmed working

**Worked well:** pip editable install pulled all deps in one shot; `data/` and `models/` correctly gitignored before any data lands there.

**Pain points:**
- `pyproject.toml` initially had wrong build backend (`setuptools.backends.legacy:build` → should be `setuptools.build_meta`); quick fix.
- XGBoost on macOS ARM requires `libomp` via Homebrew — not obvious from pip output. Required `brew install libomp`.
- Python 3.11 not available; using 3.13 (satisfies `>=3.11` requirement, no issues).

**Metrics:** All 8 core packages import cleanly; FastF1 3.8.2, XGBoost 3.2.0, SB3 2.8.0, Gymnasium 1.2.3.

**Open questions:** None — clean slate for Phase 0.2.

---

## Phase 0.2 — Frontend Scaffold (2026-04-22)
**Built:**
- Vite 8 + React 19 + TypeScript scaffold in `frontend/`
- Tailwind CSS v4 via `@tailwindcss/vite` plugin (no `tailwind.config.js` needed)
- Deps: `react-router-dom` 7, `recharts` 3, `axios` 1
- `src/index.css` — F1 dark design tokens as CSS custom properties: 10 team colors, surface tokens (`--bg-base/surface/elevated/card`), text tokens, accent (F1 red), tire compound colors
- `src/App.tsx` — `BrowserRouter` with routes for `/`, `/sandbox`, `/optimizer`, `/results`; 404 → redirect to `/`
- `src/pages/Landing.tsx` — Hero with PITIQ branding, two mode cards (Sandbox / Optimizer) with hover effects using team colors, navigation on click
- `src/pages/Sandbox.tsx` — Stub 3-step panel (circuit → driver → pit windows)
- `src/pages/Optimizer.tsx` — Stub info cards showing grid simulation metadata
- `src/pages/Results.tsx` — Stub with tire compound legend using real CSS vars
- `src/components/PageShell.tsx` — Shared nav bar with active-route underline indicator
- `vite.config.ts` — `/api` proxy to `:8000` wired up for Phase 6 backend

**Worked well:** Tailwind v4 + Vite plugin is zero-config; `tsc --noEmit` passed clean first try with strict mode.

**Pain points:**
- Vite refuses to scaffold into a non-empty directory — worked around by scaffolding into a temp dir and merging.
- Vite template used a non-standard `index.css` with its own design system; had to replace entirely rather than patch.
- `package.json` name was set to `frontend-tmp` from temp dir workaround — corrected to `pitiq-frontend`.

**Metrics:** `npm run dev` responds 200 at `:5173`; `tsc --noEmit` clean; 0 ESLint errors on generated files.

**Open questions:** None — Phase 1.1 starts the data pipeline.

---

## Phase 1.1 — FastF1 Client + Cache (2026-04-23)
**Built:**
- `backend/src/pitiq/data/client.py` — `load_session(year, race_name, session_type)` wrapping FastF1
- Persistent disk cache at `data/raw/fastf1_cache/` via `fastf1.Cache.enable_cache()` called on module import (lazy, idempotent)
- Cache path resolved from `Path(__file__).parents[4]` — works regardless of cwd
- Retry with exponential backoff: `max_retries=4`, `base_delay=2.0s`, doubles each attempt, capped at 60s
- Fatal error detection (`ValueError`, `TypeError`, "invalid session" strings) skips retries immediately
- `load_telemetry=False` default — opt-in for Phase 1.2 which needs it per-driver
- `backend/tests/test_client.py` — 5 tests: cache dir exists, returns Session, has laps, cache hit speed, invalid session raises

**Worked well:** FastF1's own cache layer handles all the per-endpoint granularity automatically — every data stream (session info, driver list, timing, etc.) is cached individually, so partial fetches are never re-downloaded.

**Pain points:**
- `Path(__file__).parents` index was off by two on first attempt (used `[6]` instead of `[4]`) — always verify with a quick print before committing path arithmetic.
- 117 pytest warnings from `url_normalize` deprecation inside FastF1 internals — not our code, harmless, no action needed.

**Metrics:**
- Cold fetch (2024 Monza R): **5.7s**, 1008 laps, 20 drivers
- Cache hit (same session): **0.4s** — **14× faster**
- 5/5 pytest tests green in 2.09s

**Open questions:** None — Phase 1.2 will use `load_telemetry=True` selectively per driver for the telemetry summary columns.

---

## Phase 1.2 — Lap & Telemetry Ingestion (2026-04-23)
**Built:**
- `backend/src/pitiq/data/ingest.py` — `ingest_season(year, max_races=None)` iterates `fastf1.get_event_schedule()`, loads each race with `load_telemetry=True`, extracts laps and telemetry summaries, concatenates and saves Parquet
- `_extract_session()` — 17 lap columns from FastF1 laps DataFrame + `Year`, `RoundNumber`, `EventName` context; all timedelta columns converted to float seconds
- `_telemetry_summary()` — per-lap scalar features: `tel_speed_avg`, `tel_speed_max`, `tel_throttle_pct`, `tel_brake_pct`; returns `{}` on any failure — missing telemetry is skipped and logged, never a crash
- `backend/src/pitiq/data/__main__.py` — enables `python -m pitiq.data.ingest --season 2024`
- `--max-races N` flag for fast dev/test iteration
- `backend/tests/test_ingest.py` — 7 tests: DataFrame returned, expected columns, row count sanity, LapTime in valid range, telemetry cols are float, Parquet written, Parquet readable

**Worked well:** FastF1's `"Car data is incomplete"` warnings (e.g. Jeddah driver 55, missing safety car laps) pass through harmlessly — the `_telemetry_summary` try/except absorbs them at the lap level without any special casing. Zero nulls in telemetry columns on complete-data laps.

**Pain points:**
- FastF1 returns timedeltas for `LapTime`, `Sector*Time`, `PitInTime`, `PitOutTime` — Parquet doesn't support `timedelta64` natively; must convert to float seconds before writing (see DECISIONS.md).
- `python -m pitiq.data.ingest` requires a `__main__.py` in the package directory, not just an `if __name__ == "__main__"` block in `ingest.py` — added `data/__main__.py` as a thin wrapper.

**Metrics:**
- Smoke test (2 races: Bahrain + Saudi 2024): **2,030 laps**, 21 drivers, 24 columns
- Zero telemetry nulls on fully-present races; partial telemetry handled gracefully
- 7/7 pytest tests green in 2:10 (Bahrain cache hit, Saudi network fetch)
- Full 2024 + multi-season backfill deferred to Phase 1.3

**Open questions:** None — Phase 1.3 runs the full backfill and adds the cleaning module.

---

## Phase 1.3 — Multi-Season Backfill + Cleaning (2026-04-23)
**Built:**
- `backend/src/pitiq/data/clean.py` — `drop_inaccurate()`, `drop_in_out_laps()`, `fuel_correct()`, `clean_season()`, `build_combined()`; CLI via `python -m pitiq.data.clean`
- Fuel correction adds `LapTimeCorrected` and `FuelCorrectionS` columns; `--no-fuel-correction` flag for debugging
- Backfill script ran all 5 seasons sequentially in background, logging to `data/backfill.log`
- `backend/tests/test_clean.py` — 9 tests covering all cleaning steps + edge cases

**Worked well:** FastF1's `"Failed to align laps"` and `"all laps marked as inaccurate"` warnings are normal for backmarker drivers in specific sessions — `drop_inaccurate` handles them cleanly. Partial backfills work without code changes (missing season files logged and skipped).

**Pain points:**
- `drop_in_out_laps` removed 0 rows after `drop_inaccurate` — turns out `IsAccurate=False` already flags all in/out laps in FastF1's model, so the two steps are somewhat redundant. Keeping both for explicitness and defensiveness against FastF1 API changes.
- 2021 season had the fewest rounds (21) because the Belgian GP was cancelled mid-session — counted as a round in the schedule but yielded minimal clean laps.

**Metrics — 5-season breakdown:**

| Year | Raw laps | After clean | Races | Drivers |
|------|----------|-------------|-------|---------|
| 2021 | 23,758   | 20,735      | 21    | 21      |
| 2022 | 23,577   | 19,639      | 22    | 22      |
| 2023 | 24,422   | 21,283      | 22    | 22      |
| 2024 | 26,606   | 23,557      | 24    | 24      |
| 2025 | 26,692   | 23,043      | 24    | 21      |
| **Total** | **125,055** | **108,257** | **113** | **35** |

**Fuel correction validation:**
- Mean correction: **1.659 s** (lap 1 at 110 kg load → lap ~61 at 0 kg)
- Correction range: **0.000 – 3.246 s**
- Monotonicity check: `LapTimeCorrected ≤ LapTime` passed on **all 108,257 rows**

**Null counts on clean dataset:** Only `TyreLife` (887) and `Stint` (382) have any nulls — FastF1 source gaps on specific laps. All other core columns, all 4 telemetry summaries, and both corrected-time columns are fully populated.

**Open questions:** `TyreLife` and `Stint` nulls (~1% of rows each) — may need imputation strategy in Phase 2 feature engineering. Will decide there.

---

## Phase 2.1 — Core Lap Features + Circuit Metadata + Weather (2026-04-23)
**Built:**
- `backend/src/pitiq/features/build.py` — `build_features()` pipeline + CLI (`python -m pitiq.features.build`)
- Per-lap computed features: `tire_age` (=TyreLife), `stint_number` (=Stint), `fuel_load_estimate` (same constants as fuel correction), `laps_remaining` (max LapNumber per race minus current), `position` (=Position)
- Circuit metadata: hardcoded lookup for all 29 unique EventNames in dataset — `length_km`, `circuit_type` (permanent/street), `pit_loss_s`, `is_street_circuit` (bool)
- Weather: per-session aggregate from FastF1 weather data — `air_temp`, `track_temp`, `humidity` (session means), `is_wet` (any Rainfall==True)
- Output: `data/features/lap_features.parquet` — 39 columns, 108,257 rows (no rows lost from laps_all.parquet)
- `backend/tests/test_features.py` — 14 tests covering schema, ranges, circuit metadata consistency, weather sanity, known wet/dry race checks, fuel formula unit test

**New feature columns:**
`tire_age`, `stint_number`, `fuel_load_estimate`, `laps_remaining`, `position`, `length_km`, `circuit_type`, `pit_loss_s`, `is_street_circuit`, `air_temp`, `track_temp`, `humidity`, `is_wet`

**Three verification checks passed:**
1. **Circuit lookup coverage:** 29/29 EventNames matched — zero `length_km` nulls. Australian GP corrected from street → permanent mid-check (Albert Park is semi-permanent, FIA classifies as permanent).
2. **Position field validity:** 2024 Italian GP spot-check confirmed `position` is dynamic track position, not grid position. Piastri (PIA) led from lap 2 after jumping Leclerc off the line — matches race reality exactly. Position changes through pit windows (PIA→SAI→VER→PER) also verified correct.
3. **Weather data integrity:** `describe()` on air_temp, track_temp, humidity — no NaNs, no zeros, all ranges within plausible F1 conditions (air: 10.6–36.6°C, track: 16.8–54.5°C, humidity: 7.1–93.5%). Low end matches desert circuits, high end matches Singapore.

**Worked well:** All 113 sessions loaded from cache in ~100s. FastF1's Ergast 429 rate-limit errors during weather loading fell back to cached responses correctly — no data loss, no crashes.

**Known limitations:**
- `is_wet` is session-level (any rain during the session), not lap-level. A race with a brief shower will flag all laps as wet. **Revisit in Phase 3 if wet-race prediction accuracy is poor** — lap-level `Rainfall` merging by timestamp is possible but adds complexity.
- **Lap 1 is systematically absent** from the dataset (dropped by `IsAccurate=False` in Phase 1.3). This makes `laps_remaining` off by 1 for every race (reads 51 at Monza instead of 52). Not a modeling concern — consistent across all races — but the `RaceEnv` in Phase 4 should initialise `laps_remaining` from the known total, not from the feature dataset.

**Open questions:** `TyreLife`/`Stint` nulls propagate into `tire_age`/`stint_number` (887 and 382 rows respectively, ~1% each). Imputation strategy TBD in Phase 3 when we see whether XGBoost handles them natively or needs explicit filling.

---

## Phase 2.2 — Train/Test Split + EDA Notebook (2026-04-24)
**Built:**
- `backend/src/pitiq/features/split.py` — `split_features()` + `save_splits()` + CLI (`python -m pitiq.features.split`)
- Race-based split: train = 2021–2024 (85,214 laps, 89 races), val = 2025 R1–12 (11,103 laps, 12 races), test = 2025 R13–24 (11,940 laps, 12 races)
- `_verify_no_overlap()` asserts no (Year, RoundNumber) key shared across splits — fires at runtime not just in tests
- `backend/tests/test_split.py` — 8/8 tests green
- `notebooks/01_eda.ipynb` — 6 sections: missing data audit, compound usage, tire degradation, lap time distributions, wet vs dry delta, split summary

**Worked well:**
- Wet vs dry fix (compound-based indicator instead of session-level `is_wet`) worked cleanly: +8.13s overall penalty, all 11 wet-circuit deltas positive, Monaco (+18s) and Singapore (+22s) highest as expected.
- Split summary validates cleanly: 89 + 12 + 12 = 113 races, zero overlap.
- Null audit confirms pipeline integrity: only `tire_age`/`TyreLife` have nulls (~0.17%), all other columns 0.

**Pain points — tire degradation visualization (three-iteration debugging process):**

1. **First attempt (absolute LapTimeCorrected):** Curves were inverted at 3/5 circuits. Diagnosed as survivorship bias + fuel load confound: longer stints are run by faster drivers in clean air, inflating apparent late-stint pace.

2. **Second attempt (per-stint relative degradation):** Subtracted each stint's baseline lap from subsequent laps. Produced empty plots. Root cause: `tire_age == 1` rows are dropped by `IsAccurate=False` cleaning (pit-out laps), so the `tire_age == 1` filter matched zero rows, `stint_baseline` was all-NaN. Fixed to use min `tire_age` per stint instead. Then hit `KeyError: nan` — the 183 null `tire_age` rows caused `idxmin()` to return `NaN` as a DataFrame index. Fixed by pre-filtering nulls. Curves then rendered but remained physically impossible (Monaco Medium −2.5s at lap 20): tire warm-up in laps 2–5 means the baseline lap is genuinely slow, making all subsequent warmed-up laps look faster.

3. **Third attempt (controlled conditions, absolute LapTimeCorrected):** Stint 1 only, top-10 finishers, green-flag filter (median + 3σ), minimum 10 laps per tire_age bucket. Belgian GP produced a clean upward curve. Other circuits revealed compound-allocation bias: each circuit has one dominant stint-1 compound (Bahrain = Soft, Monza/Singapore = Medium), so only one curve renders per circuit. Remaining V-shapes at Monaco/Bahrain are warm-up effect (cold tire laps 1–3 appear slow, improve as tire comes into window) and traffic clearing (cars ahead pit, driver gains clean air mid-stint).

**Decision:** Accept EDA limitations. Belgian GP is sufficient proof of real degradation signal in the data. The confounds (warm-up, traffic, allocation bias) are lap-level context the XGBoost model will learn directly from features — they don't require resolution at the EDA stage. Documented honestly in the notebook markdown. Revisit if Phase 3 MAE is poor on high-deg circuits.

**Metrics:**
- Split: 85,214 train / 11,103 val / 11,940 test (107,257 total — 765 rows excluded at notebook load for Compound=None/nan)
- Wet penalty: +8.13s overall; 11 circuits with wet-compound laps, all positive deltas
- 8/8 split tests green

**Open questions:** Whether XGBoost handles the warm-up effect implicitly (early `tire_age` laps may need a `is_warmup_lap` feature). Defer to Phase 3 feature importance analysis.
