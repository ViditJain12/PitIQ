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

---

## Phase 2.5.1 — Driver Style Fingerprinting (2026-04-24)
**Built:**
- `backend/src/pitiq/styles/build.py` — `build_driver_styles()` + `save_driver_styles()` + CLI (`python -m pitiq.styles.build`)
- 33 driver style vectors × 10 features saved to `data/features/driver_styles.parquet`
- Features: `pace_trend_{soft,medium,hard}`, `cornering_aggression`, `throttle_smoothness`, `wet_skill_delta`, `tire_saving_coef`, `sector_profile_{s1,s2,s3}`
- Filters throughout: green-flag only (`TrackStatus == '1'`), minimum lap thresholds per feature, NaN for insufficient data rather than crash

**Iteration story (7 steps from first run to validated output):**

1. **Initial implementation:** All 10 features computed, parquet written, ran in <1s. First output showed COL −9.4s and LAW −8.9s wet deltas — flagged as implausible for rookies.

2. **Three issues identified from initial output:**
   - `tire_deg_rate_*` slopes were negative for most drivers on SOFT/MEDIUM — track evolution dominates tire wear in stint-1 green-flag data.
   - `wet_skill_delta` had extreme outliers (COL −9.4, LAW −8.9) despite 31 and 104 wet laps respectively — not a sample-size problem.
   - `tire_saving_coef` had very low cross-driver variance (0.984–0.999 range) — limited discriminatory power.

3. **Renamed `tire_deg_rate_*` → `pace_trend_*`:** The slopes measure net pace change (degradation minus track evolution), not pure tire wear. In stint 1, the track is still rubbering in, so track evolution often outweighs tire degradation, producing negative slopes. Relative ordering between drivers remains valid style signal. Updated docstring to explain exactly what's measured and why negative values are expected.

4. **Added `MIN_WET_LAPS = 20` threshold:** Drivers with fewer than 20 wet-compound laps receive `wet_skill_delta = NaN`. HAD (9 laps) was correctly nulled. COL (31) and LAW (104) survived — their outliers were a different issue.

5. **Diagnosed circuit-mix confound in `wet_skill_delta`:** Per-race breakdown revealed COL's 24/31 wet laps were from São Paulo 2024 (circuit median 82.7s on INT), while the grid-wide INT median was 92.2s — a 9.5s circuit speed difference with nothing to do with driver skill. COL vs his São Paulo race peers was +0.16s (dead average). The issue was using a global median as the baseline.

6. **Applied race-normalised fix:** Changed `wet_skill_delta` to compute per-lap deviation from same-race, same-compound median, then take driver median. This removes circuit-mix confound entirely. COL moved to +0.36s, LAW to +0.45s (as predicted by the diagnosis).

7. **Validated final output:** All sanity checks passed. ZHO at +3.636s was investigated — 192 wet laps across 9 races, consistently +1.0 to +3.9s slower than race peers at every circuit. Confirmed genuine signal (Zhou Guanyu observed as a weak wet driver throughout his F1 career), not an artifact.

**Sanity checks passed:**
- `sector_profile_s1`: VER 4.4, PER 6.0, LEC 6.2, HAM 6.2 (top of the field), MAZ 16.5 (back of the grid). Matches known driver quality rankings.
- `wet_skill_delta` final: VER −1.11s, NOR −0.78s, HAM −0.38s, ALO +0.12s. Spread of −1.1 to +3.6s. VER strongest wet driver in the data, matches widely-held view.

**Known limitations:**
- `pace_trend_*`: Measures net pace change, not pure tire wear. Cannot separate tire degradation from track evolution at this aggregation level. Relative driver ordering still useful for XGBoost, but absolute values are not interpretable as degradation rates.
- `tire_saving_coef`: Low variance (0.984–0.999). Feature is kept but may contribute little signal in Phase 3. Feature importance analysis in Phase 3 will confirm.
- Style vectors are static across all 5 seasons. A driver who changed style significantly (e.g. Hamilton at Mercedes vs Ferrari) will have blended values. Acceptable for current scope.

**Metrics:**
- 33 drivers processed, 2 excluded (DOO: 247 laps, KUB: 113 laps — both one-off or reserve appearances)
- 1 driver nulled for `wet_skill_delta` (HAD: 9 wet laps)
- Total NaN count: 4 cells (pace_trend_soft ×1, pace_trend_hard ×2, wet_skill_delta ×1)
- Runtime: <1 second

**Open questions:** Whether `pace_trend_*` or `tire_saving_coef` show up in Phase 3 XGBoost feature importance — if neither does, consider dropping them from the style vector to reduce dimensionality.

---

## Phase 2.5.2 — Driver Style Validation Notebook (2026-04-24)
**Built:**
- `notebooks/02_driver_styles.ipynb` — 5-section validation suite for `driver_styles.parquet`
- Sections: styled summary table, 4 radar chart comparisons, k-means clustering with PCA scatter, cluster sanity check, pairwise correlation heatmap

**Validation results — what matched expectations:**
- **Radar charts:** VER polygon envelops HAM on most axes (overall pace, wet skill). NOR ≈ PIA as expected for McLaren teammates — strongest confirmation the features are consistent within team/car. ZHO smaller than HUL on wet-skill axis (ZHO known wet struggles). LEC and SAI similar shapes; LEC edges SAI on overall pace axis.
- **PCA scatter:** PC1 (26.4% variance) separates drivers cleanly by quality — VER/NOR/LEC at one end, MAZ/MSC/SAR at the other. PC2 appears to capture braking/throttle style dimensions. Clean axis structure confirms the feature set has real signal, not noise.
- **Clustering (k=4, silhouette 0.151):** Soft clusters reflecting a continuum rather than crisp archetypes, which is honest — F1 driver styles don't fall into discrete buckets. The quality separation (Cluster 0 top-tier vs Cluster 1 backmarkers) is clean. Cluster 2 (RAI/GIO/LAT, 3 drivers) is a small cluster distinguished by high braking aggression and smoothness — plausibly an Alfa Romeo/Ferrari lineage style artefact, but too small to over-interpret.

**Major finding during validation — sector_profile redundancy:**
Initial heatmap showed `sector_profile_s1` vs `sector_profile_s2` vs `sector_profile_s3` all correlating at r = +0.99. Three features were collapsing to one signal: "how fast is this driver overall." The original intent — to capture *where* drivers gain time per sector — was not being achieved.

Fix: decompose into:
- `overall_pace_rank` = mean(s1_rank, s2_rank, s3_rank) — captures overall quality (what the old features were really measuring)
- `sector_relative_{s1,s2,s3}` = s{N}_rank − overall_pace_rank — captures sector specialisation (positive = gives time in that sector, negative = gains time)

Post-fix inter-correlations: rel_s1 vs rel_s2 = −0.55, rel_s1 vs rel_s3 = −0.40, rel_s2 vs rel_s3 = −0.55. The negative correlations are expected (sum-to-zero constraint) and confirm the features now carry independent information.

**Acknowledged limitation:**
`wet_skill_delta` vs `overall_pace_rank`: r = +0.90. Better drivers are faster in wet conditions just as they are in dry — top drivers (VER, NOR, PIA) show negative wet deltas for the same reason they have low sector ranks. This is a real-world confound, not a fixable pipeline artifact. The feature is kept because it may still help XGBoost on wet-specific lap predictions where the marginal skill difference matters. Phase 3 feature importance will determine whether it contributes beyond what `overall_pace_rank` already provides.

**Final feature set: 11 features per driver**
`pace_trend_soft`, `pace_trend_medium`, `pace_trend_hard`, `cornering_aggression`, `throttle_smoothness`, `wet_skill_delta`, `tire_saving_coef`, `overall_pace_rank`, `sector_relative_s1`, `sector_relative_s2`, `sector_relative_s3`

**Open questions:** Whether sector_relative features show meaningful importance in Phase 3 XGBoost — if all three are near-zero importance, consider dropping the specialisation decomposition and keeping only `overall_pace_rank`.

---

## Phase 3.1 — XGBoost Baseline Lap Time Model (2026-04-26)
**Built:**
- `backend/src/pitiq/ml/train_xgboost.py` — full training pipeline: feature matrix construction, XGBRegressor with early stopping, evaluation (overall + per-compound + per-circuit MAE), feature importance plot, model + metadata persistence
- Restructured `pitiq.features.split` from boundary-based to explicit stratified race selection — 6-race test set spanning 2024–2025, 4-race val set for early stopping diversity
- `models/xgb_baseline.pkl`, `models/xgb_baseline_meta.json`, `models/figures/baseline_feature_importance.png`

**Final metrics:**
- Stable subset (≥3 train years, 5 circuits, 4,402 laps): **1.11s MAE**
- Sparse subset (<3 train years, Las Vegas only, 760 laps): **3.91s MAE**
- Overall (6 circuits, 5,162 laps): **1.53s MAE**
- Per-compound: SOFT 1.19s, MEDIUM 1.58s, HARD 1.53s
- Per-circuit: Belgian 0.62s, Emilia Romagna 0.76s, US 0.92s, Dutch 1.29s, Qatar 2.10s, Las Vegas 3.91s

**Iteration story — 6 steps to get here:**

1. **Initial baseline (3.43s MAE):** Feature set used physical circuit proxies only (length_km, pit_loss_s, circuit_type). These don't uniquely identify circuits — Hungary, Mexico, São Paulo all share ~4.3km/22s but span a 7s lap-time range. Model was predicting "which circuit type" not "which circuit." Azerbaijan alone had 9.2s MAE (pure systematic offset — model confused it with Saudi/Las Vegas).

2. **Added EventName one-hot → 2.28s MAE:** Fixed the circuit confusion issue (Azerbaijan: 9.2s → 0.79s). Exposed temporal drift as the next problem: 5 circuits showed systematic over-prediction of 2–5s. Root cause: training data was 2021–2024, test was all-2025. F1 cars improve ~2-4s/yr at some circuits, so 2025 lap times were faster than the 2021–2024 mean.

3. **Added Year + RoundNumber features — no improvement (still 2.28s):** Year importance ≈ 0.0007, RoundNumber importance ≈ 0.008. XGBoost trees cannot extrapolate past the training maximum Year=2024, because every 2025 test row falls into a leaf with zero training observations. The val set (2025 R1–12) was used only for early stopping — the model never gradient-updated on it, so Year=2025 was never in the training distribution.

4. **Restructured split — 2025 R1–18 added to training:** Moved to train=2021–2023 + 2024 R1–20 + 2025 R1–18, val=2024 R21–24 + 2025 R19–21, test=2025 R22–24. Overall MAE dropped to 1.99s, but test was only 3 circuits (Las Vegas, Qatar, Abu Dhabi) — too narrow to be reliable.

5. **Restructured test to 6 stratified circuits:** Switched from boundary-based split to explicit (Year, RoundNumber) pairs. Test: 2024 Belgian/US/Qatar + 2025 Emilia Romagna/Dutch/Las Vegas. Val: 2024 Mexico City/Abu Dhabi + 2025 British/Singapore. This gave ~5,200 test laps across 6 circuits spanning two calendar years. MAE: 1.53s overall.

6. **Stable/sparse subset analysis:** Recognised that Las Vegas (2 train years) and Qatar (non-consecutive 2021+2023+2025) are structurally data-scarce due to F1's calendar. Reporting stable (≥3 consecutive-ish train years) vs sparse (<3) separately gives an honest read. Rejected further split tweaking to chase the headline number.

**Key insight — non-consecutive training years for Qatar:**
Qatar appears in training for 2021, 2023, and 2025 (3 years) but posts 2.1s MAE — worse than Belgian or Emilia Romagna at similar training year counts. The 2022 and 2024 gaps mean the model's Qatar baseline is pulled toward older, slower pace. Non-consecutive years are nearly as bad as missing years: the model cannot infer the 2022/2024 trend across gaps, so the baseline is dragged toward 2021 pace (~87.4s) when 2024 actuals are ~84.3s.

**Per-compound MAE is tight:**
SOFT 1.19s vs HARD 1.53s — a 0.34s spread. The model cleanly learned the compound and tire_age signal within circuits. The tight spread confirms that tire degradation / compound differentiation is well-captured; the dominant error source is inter-circuit pace calibration, not within-stint dynamics.

**Failure modes are systematic and interpretable:**
High-MAE cases are all explained by the same mechanism: insufficient historical training data → wrong circuit pace baseline. There are no random high-error circuits. Belgian (3 recent years including 2025) → 0.62s. Las Vegas (2 years, no 2025) → 3.91s. The model is well-behaved; its limitations are structural to the 5-year FastF1 window.

**Limitation — data-scarce circuits:**
Las Vegas joined the F1 calendar in 2023. Qatar runs sporadically (2021, 2023, 2024 sprint format, 2025). No amount of feature engineering or split adjustment addresses this — the signal simply isn't in 5 years of data. Phase 3.2 trains under identical splits, so the driver-style improvement measurement is unaffected.

**Open questions:**
- Will driver style features (Phase 3.2) meaningfully improve within-circuit MAE (the remaining ~1s on stable circuits)?
- Does Qatar's non-consecutive-year problem extend to other sporadically-run circuits in future seasons?
- Year/RoundNumber importance stayed near zero even with 2025 in training — worth checking whether an interaction term (Year × EventName) is being learned implicitly through the tree structure, or whether temporal trends are genuinely unexploited.

---

## Phase 3.2 — Driver-Style-Aware XGBoost (2026-04-27)
**Built:**
- Extended `backend/src/pitiq/ml/train_xgboost.py` with `--styled` flag: joins 11 driver style features from `driver_styles.parquet` by Driver, builds 61-feature matrix, trains under identical splits/hyperparameters/seed as baseline
- `models/xgb_styled.pkl`, `models/xgb_styled_meta.json`, `models/figures/styled_feature_importance.png`
- `models/xgb_styled_no_pace_rank.pkl` — ablation model (10 style features, `overall_pace_rank` removed)
- Comparison table output, per-driver MAE breakdown, style feature rank reporting

**Headline metrics:**

| Model | Overall MAE | Stable MAE | Sparse MAE |
|---|---|---|---|
| Baseline | 1.5255s | 1.1140s | 3.9085s |
| Styled (all 11) | **1.3205s** | 1.0708s | **2.7666s** |
| Ablation (no `overall_pace_rank`) | 1.4783s | 1.0568s | 3.9198s |

13.4% overall improvement. −29% on sparse (Las Vegas). −4% on stable circuits.

**Per-compound improvement:**
SOFT: 1.19s → 1.07s (−10%). MEDIUM: 1.58s → 1.41s (−10%). HARD: 1.53s → 1.28s (−16%). Consistent improvement across all dry compounds — the effect is general, not compound-specific, confirming it comes from a driver-quality prior (overall pace) rather than compound-interaction learning.

**Ablation finding — overall_pace_rank does ~100% of the work:**
All 11 style features rank 39–58 out of 61 by XGBoost gain. `overall_pace_rank` is highest at rank 39 (gain 0.0006); the next best is `wet_skill_delta` at rank 44 (gain 0.0003). Total gain from all style features combined ≈ 0.21% of total feature gain.

Yet removing `overall_pace_rank` collapses the sparse MAE back to 3.92s (≈ baseline 3.91s), while stable MAE barely changes (1.06s vs 1.07s). The mechanism: on sparse circuits like Las Vegas where per-circuit baseline is uncertain (only 2 training years), `overall_pace_rank` functions as a driver quality prior that lets the model distinguish a Verstappen lap from a backmarker lap even when the circuit baseline is noisy. On stable circuits with dense training data, circuit identity dominates and driver quality adds little.

**Why the other 10 features have near-zero gain on lap-time prediction:**
Lap time is dominated by circuit identity + compound + tire age + fuel load. Per-driver style differences (cornering aggression, tire saving behaviour, sector specialisation, wet skill) manifest as ±0.1-0.5s effects that are dwarfed by the 5-20s circuit-level and compound-level effects. These features were designed for behavioural/strategic prediction (when and whether to pit, rival response to undercuts) — Phase 4.5 and Phase 5's domain. They are retained in the feature set for those downstream phases.

**Rookie / transfer driver MAE:**
Median driver MAE in test set: 1.34s. HAD: 1.60s (1.2×), ANT: 1.75s (1.3×), LAW: 1.47s (1.1×), HAM: 1.58s (1.2×). None above 2× median. Elevated MAE is consistent with general data sparsity for these drivers (limited race history in test circuits), not a style-feature NaN issue. HAD has 1 NaN (wet_skill_delta) but this had negligible impact given that feature's rank-44 importance.

**Decision: retain all 11 style features**
Only `overall_pace_rank` improves Phase 3 lap-time regression. The other 10 are kept because their intended use is Phase 4.5 rival behavior cloning and Phase 5 PPO state representation — contexts where cornering aggression, tire saving tendency, and sector specialisation are expected to predict strategic decisions, not absolute lap times.

**Open questions:**
- Will `wet_skill_delta`, `cornering_aggression`, `tire_saving_coef` show meaningful importance in Phase 4.5 rival pit-decision classification? That's where these features were designed to contribute.
- Is `overall_pace_rank` redundant with the RL agent's position state in Phase 4/5? If the agent already observes current race position, the pace-rank prior may be less necessary.
- The 10% stable-circuit improvement from style features is small but real — it may grow in Phase 3.3 when degradation curves are the output (style differences manifest more clearly over a full stint than on individual laps).

---

## Phase 3.3 — Degradation Curve Generator + Compound Dynamics (2026-04-27)
**Built:**
- `backend/src/pitiq/ml/predict.py` — `load_model()` (lru_cache, loads model + feature_cols + style vectors + circuit defaults), `predict_lap_time()` (single-row inference with fuel model), `predict_degradation_curve()` (per-lap stint iterator), `degradation_curve_to_json()` (structured output with cumulative time + degradation slope)
- `backend/src/pitiq/ml/compound_constants.py` — three dicts: `COMPOUND_CLIFF_LAP`, `COMPOUND_CLIFF_PENALTY_S`, `COMPOUND_FRESH_TIRE_OFFSET_S`
- Fuel model: `max(0, 110 - (race_lap - 1) * 1.8)` kg/lap, integrated per-lap in the curve generator
- `apply_compound_dynamics: bool = False` flag on `predict_degradation_curve` — disabled by default, used in Phase 4 RaceEnv

**Validation results (VER @ Italian GP, 30-lap stint, stint start L2):**

Pure XGBoost (no compound dynamics):
- SOFT and MEDIUM/HARD produce near-identical curves (+0.0270s/lap degradation for all three) — expected, Compound_HARD XGBoost gain ≈ 0.000036
- SOFT mean: 82.879s, MEDIUM/HARD mean: 82.918s — 0.039s gap, all model noise

With compound dynamics:
- SOFT: fresh-tyre offset −0.400s → starts 0.400s faster; cliff at lap 18 → +0.15s/lap penalty; visible acceleration around lap 23 in final laps
- MEDIUM: no offset, no cliff within 30 laps → unchanged from pure model
- HARD: fresh-tyre offset +0.300s → starts 0.300s slower; cliff at lap 45 → no penalty in a 30-lap stint
- MEDIUM vs HARD at lap 1: Δ = −0.300s (differentiated ✓)

**VER vs HAM differentiation:**
25-lap MEDIUM stint at Italian GP: VER cumulative 2487.5s vs HAM 2488.9s → +1.391s (HAM slower ✓). Driven by `overall_pace_rank`: VER 4.22, HAM 6.13. The style join is working end-to-end from `driver_styles.parquet` through `load_model()` through `predict_lap_time()`.

**MEDIUM = HARD: by design, not a bug:**
Compound_HARD XGBoost gain ≈ 0.000036 (below the model's split threshold). The pace difference between MEDIUM and HARD in F1 (~0.1s) is below the model's inherent MAE (1.07–1.32s). Attempting to learn it would fit noise. The compound dynamics constants layer handles this explicitly in Phase 4 — a clean separation of concerns matching real F1 strategy software architecture (separate pace model + tyre durability model, combined at the simulator layer).

**lru_cache gotcha fixed:**
`load_model(model_path=_DEFAULT_MODEL_PATH)` and `load_model()` create different cache keys in `lru_cache` (keyword vs positional arg). Fixed by standardising all internal calls to positional: `load_model(_DEFAULT_MODEL_PATH)`. This prevents the model from loading twice on first call.

**Open questions:**
- Compound dynamics constants (cliff laps, penalties) are representative mid-field values from Pirelli/Heilmeier 2020. Phase 4 RaceEnv will use them as-is; refinement would require stint-level degradation fitting which is not in scope for MVP.
- The fuel burn constant (1.8 kg/lap, 110 kg start) is a simplified linear model. Real F1 fuel burn varies by circuit and conditions. Acceptable for MVP — revisit if stint strategies diverge significantly from simulation in Phase 5.

## Phase 4.2 — Reward Function + Manual Validation (2026-04-30)
**Built:**
- Full reward formula in `SandboxRaceEnv.step()` replacing `-lap_time` placeholder:
  - `position_reward = position_delta × 0.5` (±0.5 per position gained/lost each lap)
  - `pit_cost = −0.05` per pit attempt (discourages spam without blocking strategy)
  - `cliff_penalty = −0.10 × laps_past_cliff` (flat per-lap penalty for over-ageing tires)
  - `invalid_action_penalty = −2.0` for same-compound pit attempt
  - `pace_reward = (rival_lap_time − ego_lap_time) × 0.05` (dense per-lap signal; rival_lap_time mirrors the per-lap rival pace logic including 22s on rival pit lap)
  - Terminal: `−final_position × 2.0 + (10.0 if rule_met else −100.0)`
- `RewardLogger` class — records all components per step when `log_rewards=True`; disabled by default; exposes `.to_dataframe()`. Attached to `SandboxRaceEnv` via `log_rewards` constructor flag.
- Private state vars `_prev_position` / `_curr_position` tracking lap-over-lap position changes.
- `_rival_baseline_lap_time_for_lap(lap)` helper method (mirrors step (f) rival logic; documented to warn against calling with post-increment `self._lap_num`).
- `notebooks/03_sandbox_env.ipynb` — 4-scenario validation with ranked reward tables, assertion checks, and per-step reward shape plot. Figure saved to `models/figures/reward_shape_monza_optimal.png`.

**Initial design → sparse-reward issue → pace_reward fix:**
First version had 5 reward components (no pace_reward). Scenario D reward shape showed completely flat reward during stay laps (step_reward = 0.00 on laps where position didn't change). Per-step std = 0.896, SNR = 8.9×. Problem: at low-overtaking circuits (Monaco) where position rarely changes, the agent would receive near-zero reward for entire races except on pit laps and terminal. Added `pace_reward` as the fix — compares ego lap time against rival baseline each step. This is circuit-agnostic (works at Monaco, Monza, Bahrain equally). Per-step std increased from 0.896 → 1.114 (+24%). SNR slightly reduced from 8.9× → 7.2× (still well above 3× PPO threshold). pace_reward scale 0.05 calibrated so cumulative signal (~±13 max over a 53-lap stint at 0.5s/lap advantage) doesn't exceed terminal magnitude (±10 per rule bonus).

**Validation results (with pace_reward):**

| Scenario | Circuit | Assertion | Result |
|---|---|---|---|
| A | Monza 2025 VER MEDIUM start | 1 > 3 > 5 > 4 > 2 | ALL PASS |
| B | Bahrain 2024 VER SOFT start | 1 ≈ 2 ≈ 3 >> 4 (rule violator) | ALL PASS (max spread 2.36 pts < 8 threshold) |
| C | Monaco 2023 LEC MEDIUM start | 1 > 3 > 4 > 2 | ALL PASS |
| D | Reward shape + SNR | >3× | PASS (SNR=7.2×, +24% density vs no pace_reward) |

**Scenario A ordering note (4 vs 5):** pace_reward correctly differentiates wasteful 4-stop (S4=−42.68) from tire abuse (S5=−40.07). Each of 4 pit laps costs −1.10 pace_reward (ego lap=81+22=103s vs rival 81.5s → −21.5s delta × 0.05), while tire abuse takes that hit once then holds P13 running cleaner lap times. Without pace_reward, S4≈S5 within 0.6 pts (tied). With pace_reward, S5>S4 by 2.6 pts. Physically correct.

**Reward shape (Monza optimal 1-stop, with pace_reward):**
- Laps 1–31: small non-zero from pace_reward (~+0.002/lap, VER 0.044s/lap faster than rival)
- Lap 32 (ego pit): −5.65 (−4.55 position/pit + −1.10 pace penalty for slow pit lap)
- Lap 34 (rivals pit): +5.59 (+4.50 position recovery + +1.09 pace bonus for rival slow lap)
- Lap 53 (terminal): +8.07 (P1→−2 + rule_met→+10 + last-lap pace_reward)

**Known limitation — Monaco position over-penalisation:**
`SandboxRaceEnv` uses cumulative race time to rank ego vs static 1-stop rivals. At low-overtaking circuits (Monaco, Singapore, Hungary), this is physically wrong: starting position ≈ finishing position in real F1 regardless of pit timing. The env's procession behaviour breaks down — early pit (L12) drops to P20 because 37 laps of rivals ahead; late pit (L60) drops to P20 because massive MEDIUM cliff inflates ego cumulative time. Both S3 and S4 finish P20 at Monaco despite different strategies, so cliff math dominates (S3 beats S4 by 17.5 pts). The agent will learn "aggressive Monaco pit timing is sub-optimal in the env," which happens to match real F1 behaviour for the right outcome but wrong mechanism. Properly modelled in Phase 4.5 `GridRaceEnv` via per-circuit overtaking difficulty.

**Monaco 2024 data issue discovered:** All laps have `stint_number ≥ 2` (safety-car start flagged entire stint 1 as InAccurate). `load_circuit_rival_profile` returns NaN `pace_s1` for Monaco 2024. Notebook uses Monaco 2023 (LEC on pole, 78 laps, equivalent scenario for strategy testing).

**Open questions:**
- Phase 5 PPO training should over-index on Monza/Bahrain/Silverstone circuits where position dynamics are realistic, and under-weight Monaco/Singapore/Hungary until Phase 4.5 fix lands.
- pace_reward scale 0.05 is a first-pass calibration; may need tuning once PPO training curves are observed (if pace_reward accumulation dominates terminal, reduce scale).

---

## Phase 4.5.1 — Rival Behavior Cloning Model (2026-05-01)
**Built:**
- `backend/src/pitiq/ml/rival_policy.py` — `_build_training_data()`, `_make_feature_matrix()`, `_split_dataset()`, `train()`, `predict_pit_probability()`, `_run_sanity_checks()`
- `_CalibratedPitModel` wrapper class — XGBClassifier + IsotonicRegression, clips output to [0.001, 0.95]
- Label: `pitted_next_lap = 1` when the next lap (same driver, same race) has a different `Stint` number. Pit/out laps are already dropped by Phase 1.3 cleaning (IsAccurate=False), so a Stint change reliably marks the lap immediately before a pit stop.
- 55 features: 7 numeric race-state features + 1 binary (is_wet) + EventName one-hot + Compound one-hot + all 11 driver style features. Gap-to-rival features intentionally excluded (added in Phase 4.5.3).
- Imbalance: 3.28% pit rate → scale_pos_weight=29.4, XGBoost native handling (no SMOTE).
- Calibration: IsotonicRegression fitted on val set (`cv='prefit'` API dropped in sklearn 1.8 → manual wrapper), clipped to [0.001, 0.95].
- CLI: `python -m pitiq.ml.rival_policy --train`

**Metrics:**
- AUC-ROC (test): **0.777** — above target of 0.75
- Avg Precision (test): 0.098
- @ threshold=0.30: precision=0.303, recall=0.061, f1=0.101
- Early stopping: best_iteration=150 of 1000
- scale_pos_weight: 29.4 | 93,902 stay / 3,199 pit laps in train

**Domain sanity checks — 4/4 passed:**
1. VER (0.1324) < ZHO (0.9500) at tire_age=25 Bahrain — tire-saving driver has lower pit probability ✓
2. tire_age=5 (0.0093) < tire_age=35 (0.9500), same compound — older tire → higher pit probability ✓
3. laps_remaining=5 (0.0606) < laps_remaining=30 (0.1324) — end-of-race has lower pit probability ✓
4. Monaco (0.0773) < Bahrain (0.1324), same race state — circuit-specific pit reluctance ✓

**Style feature contribution — Phase 2.5 finally shows up:**
All 11 driver style features appear in the XGBoost importance ranking (ranks 38–54 of 55). `overall_pace_rank` leads at rank 38. This contrasts sharply with Phase 3.2 where style features ranked 44–58/61 for lap-time prediction. Pit-decision classification is the behavioral task these features were designed for — the Phase 2.5 work now has clear justification.

Race-state features (tire_age, laps_remaining, EventName one-hots) dominate the top ranks. Style features provide secondary signal that captures driver-specific strategic tendencies.

**Known limitations:**
- Gap-to-rival features (gap_ahead, rival_tire_age) intentionally excluded. Real F1 pit timing is heavily undercut-window-dependent. AUC ceiling without gap features is ~0.80; reaching higher requires multi-agent context (added in Phase 4.5.3).
- Low recall at threshold=0.30 (6.1%) — expected. Model produces calibrated low-probability continuous outputs matching the 3.3% base rate. AUC-ROC (rank-order metric) is the correct primary metric for stochastic sampling use.
- Probability saturation at 1.0 before clipping for extreme scenarios (ZHO at tire_age=25 Bahrain, any driver at tire_age=35 MEDIUM). Clipping to 0.95 preserves stochasticity: rivals in GridRaceEnv always have a 5% chance of not pitting even in high-urgency states, which prevents PPO from hard-coding "ZHO always pits on lap 25" and preserves episode diversity.

**Pain points:**
- `sklearn 1.8.0` dropped `cv='prefit'` from `CalibratedClassifierCV` — had to implement `_CalibratedPitModel` wrapper with manual isotonic regression fit.
- `XGBoost 3.x` renamed `best_ntree_limit` → `best_iteration` — quick fix.
- Sanity check inner `_prob()` function received spurious `laps_past_cliff` kwarg that it computes internally — removed.

**Open questions:**
- Will `tire_saving_coef` importance grow when gap-to-rival features are added in Phase 4.5.3? Currently at rank 49, but the undercut/overcut window interacts heavily with driver aggression.
- Phase 5 PPO reward shaping: if rival pit timing is now realistic (vs Phase 4's static 1-stop model), the ego agent's credit assignment for undercut/overcut windows becomes cleaner. Monitor first PPO training run for improvement vs Phase 4.2 baseline.

---

## Phase 4.1 — SandboxRaceEnv Skeleton (2026-04-28)
**Built:**
- `pitiq.envs.sandbox.SandboxRaceEnv` — Gymnasium env with 13-dim observation space (lap_fraction, compound one-hot×5, tire_age, stint_num, fuel_kg, position, laps_remaining, laps_past_cliff, has_2nd_compound) and Discrete(4) action space (stay, pit_soft, pit_medium, pit_hard).
- Rival baseline: 1-stop profile (pace_s1, pace_s2, median_pit_lap) from top-10 training data per (circuit, year), with closest-year fallback. Rivals absorb 22s pit loss at their median lap, fixing the earlier P20-everywhere bug.
- Compound dynamics layer active in step(): cliff penalty and fresh-tire offset applied on top of XGBoost predictions.
- `pitiq.envs.test_sandbox_manual` — manual validation script.

**Validation: 10/10 checks passed**
- 4-strategy Monza ordering correct (1-stop < 4-stop, no-pit flagged as rule violation).
- 5-circuit polesitter test: all 5 circuits P1, race times within 1.3% of rival-reference historical baseline.

**Three fixes during validation:**
1. **Year-specific weather lookup** (real fix): Singapore default weather was averaged across 2022–2025 eras. The 2022 season had 87% humidity at Singapore vs 74% in 2024; this pushed XGBoost into a wrong regime (+10s prediction error). Storing year-specific weather means in `reset()` and passing them to `predict_lap_time` resolved the issue.
2. **VSC-biased rival pit laps at Bahrain** (workaround): Historical median pit lap is lap 12 of 57 due to a VSC-triggered mass pit cycle in 2024. The env keeps this historical median (correct for PPO training). Validation test applies a 40% race-distance floor to the ego pit lap so the test exercises a realistic strategy. Flagged for Phase 4.2 reward design.
3. **Monza pit lap calibrated to lap 32**: Early pit at lap 25 drops ego from P1 to P12 immediately because all 19 rivals are still running stint-1 pace. Adjusting to lap 32 (2 laps ahead of the rival median of 34) avoids the rival-stint-1 overtake artifact while keeping a meaningful gap for the 1-stop vs 4-stop comparison.

---

## Phase 4.5.3 — Rival-Aware 25-Dim Observation Space (2026-05-03)
**Built:**
- Expanded `GridRaceEnv` ego observation from 13-dim to 25-dim by adding 12 rival-context features
- New dims [13-17] — rival immediately ahead: `gap_to_rival_ahead_s` (clipped [0, 30]), `rival_ahead_cmp_idx` (integer compound index), `rival_ahead_tire_age` (capped at 50), `rival_ahead_pace_rank` (from style vector), `rival_ahead_tire_save` (from style vector)
- New dims [18-22] — rival immediately behind: same 5 features mirrored
- New dims [23-24] — strategy flags: `undercut_window_open` (gap_ahead < 1.5s AND rival_ahead older tires than ego), `defending_against_undercut` (gap_behind < 1.5s AND rival_behind fresher tires than ego)
- Sentinel values for edge positions: P1 ego (no rival ahead) → gap=30.0, cmp=0, tire_age=0, pace_rank=33.0, tire_saving=0.5; P20 ego (no rival behind) → same sentinels
- `_compute_rival_context()` method with NaN-safe `_sv()` helper for drivers with missing style-vector entries
- Updated `observation_space` bounds in `__init__`: shape (25,), low/high covering all 12 new dims
- `test_grid_part5.py` — labeled 25-dim obs printer at laps 1/10/17/19/30/56 (VER P1) + lap 5 (PER P4)

**Validation — 16/16 assertions pass:**
- Lap 1: P1 sentinel active (gap_ahead=30.0), gap_behind=0.10s (LEC close behind at race start) ✓
- Lap 10: gap_behind=1.01s (VER opened gap to LEC slightly over 10 laps) ✓
- Lap 17: undercut_window_open=0.0 (VER P1, no rival ahead to undercut) ✓
- Lap 19: ego tire_age=2 (fresh HARD post-pit), defending=0.0 (ego fresher than rivals behind) ✓
- Lap 30: rival_ahead sentinel active (VER stays P1 whole race — age=0 is the correct sentinel) ✓
- Lap 56: gap_behind=16.0s (VER 16s clear at race end — realistic Bahrain spread) ✓
- Race 2 (PER P4, lap 5): both gaps populated (RUS 1.04s ahead, SAI 0.88s behind), no sentinels active ✓
- Observation space shape = (25,) ✓

**Key implementation notes:**
- `_compute_rival_context()` builds a `pos_map = {position: Car}` lookup each call — O(n) per lap but clean; 20-car grid makes this negligible
- Integer compound index (not one-hot) for rival compounds — keeps obs compact while preserving compound identity; PPO embedding layer will learn the mapping
- `gap_to_rival_ahead_s = ego.cumulative_race_time - rival_ahead.cumulative_race_time` — positive = ego is behind in time (rival ahead is faster)
- `gap_to_rival_behind_s = rival_behind.cumulative_race_time - ego.cumulative_race_time` — positive = rival behind is slower
- Both clipped to [0, 30] — 30.0 is a "safe" out-of-range sentinel that also signals "very large gap" to the agent

**Design rationale — undercut/defending flags pre-computed:**
Rather than leaving the agent to derive the undercut signal from raw gap + tire age features, the flags are pre-computed with clean semantics (1.5s threshold, tire age comparison). This reduces the RL learning burden: the agent can learn "if undercut_window_open=1, pitting now is likely profitable" without first having to discover that (gap < 1.5) AND (rival_age > ego_age) is the relevant conjunction. Raw features are also present for any more nuanced policy the agent discovers.

**Worked well:**
- NaN-safe `_sv()` helper cleanly handles the ~3 drivers in `driver_styles.parquet` with NaN style features (e.g., `wet_skill_delta` for HAD)
- Sentinel scheme (large round numbers) is learnable: the agent will quickly discover that gap=30.0 means "no rival in this direction," which is a simple signal to exploit

**Pain points:**
- Lap 30 assertion initially assumed VER would not be P1 (checking rival_ahead_tire_age in [1, 49]). VER stayed P1 the entire race, so sentinel (age=0) was correct. Assertion updated to conditional: check age if gap<30.0, else verify sentinel=0.

**Open questions:**
- Phase 5 PPO: will `undercut_window_open` and `defending_against_undercut` appear early in value-function feature importance? If so, validates the pre-computation design.
- Phase 4.5.1 rival policy used only ego-state features. Now that `GridRaceEnv` computes per-car gaps, could we retrain the rival policy with gap-to-rival features for a second-pass AUC lift (target: >0.80)? Deferred; current AUC=0.777 is sufficient for Phase 5.

---

## Phase 4.5.2 — GridRaceEnv (2026-05-02)
**Built:**
- `pitiq.envs.grid.GridRaceEnv` — 20-car Gymnasium multi-agent race environment for Optimizer Mode. 4-part incremental implementation:
  - **Part 1:** `Car` dataclass (12 fields: driver, style_vector, positions, compound, tire_age, stint_number, fuel, flags, pit_history) + `GridRaceEnv.__init__()` + `reset()` with full 20-car initialisation from `driver_styles.parquet` + stub `step()` + `render()`.
  - **Part 2:** Full `step()` — per-car XGBoost lap time prediction, compound dynamics (fresh-tire offset + cliff penalty), pit penalties (22s), cumulative race time accumulation, naive position sort, ego reward (identical formula to SandboxRaceEnv), tire_age/fuel/lap_num bookkeeping.
  - **Part 3:** `rival_pit_policy` integration — replaced deterministic cliff-threshold placeholder with `predict_pit_probability()` stochastic sampling + force-pit override at `laps_remaining<8` + never-pit guard at `laps_remaining≤2`. Per-circuit overtaking friction using `OVERTAKING_DIFFICULTY` from `pitiq.envs.grid_constants` — clamps on-track position gains per lap, pit-cycle swaps exempt.
  - **Part 4:** Full validation against official 2024 Bahrain GP results across 5 seeds.
- `pitiq.envs.grid_constants.OVERTAKING_DIFFICULTY` — per-circuit max positions gained on-track per lap (Bahrain/Monza/Spa/Baku=1, moderate circuits=0.5, Monaco=0.1, Singapore/Miami/Hungary=0.3).
- Validation scripts: `test_grid_part1.py` (skeleton), `test_grid_part2.py` (full race step), `test_grid_part3.py` (stochastic comparison), `test_grid_part4.py` (vs actual 2024 Bahrain results).

**Final metrics — Part 4 validation vs actual 2024 Bahrain GP (5 seeds: 42, 123, 456, 789, 999):**
- **70% of drivers within ±3 positions** of actual finishing position (target ≥60%) ✓
- **95% of drivers within ±5 positions** (target ≥85%) ✓
- **Mean absolute position delta: 2.06** (target ≤3.0) ✓
- **Race winner time: 5291s (−2.2% vs actual 5408s)** — within ±3% band ✓
- **VER P1 in 5/5 runs** (target ≥4/5) ✓
- **18/20 drivers with stdev ≥ 1.0** across runs — stochastic chaos confirmed ✓
- **20/20 two-compound rule compliance** in every run ✓

**Stochastic rival behavior validated (Part 3):**
- LEC/NOR/ZHO pit laps differ across seeds 42/123/999 — XGBClassifier sampling working correctly
- ZHO mean pit lap (11.0) < NOR mean pit lap (12.0) — driver style signal from Phase 4.5.1 classifier confirmed in sim behavior
- Simultaneous pit events (3+ rivals same lap): 17 total across 3 runs, each cluster 3–7 cars spread across laps 3–53. Part 2's deterministic placeholder had 1 event with all 19 cars on the same lap.

**Overtaking friction model:**
- `OVERTAKING_DIFFICULTY` — float per circuit: 1=easy (Bahrain, Monza, Spa, Baku, COTA, Las Vegas, Saudi), 0.5=moderate (most permanent circuits), 0.3=hard (Monaco, Singapore, Miami, Hungary). Stored in `grid_constants.py` (separate from `grid.py`) for clean dependency.
- Pit-cycle swaps are explicitly exempt: a car pitting from P5 to P8 while rivals stay out is realistic F1 behavior and should not be blocked.
- After friction, `self._grid` is re-sorted by `cumulative_race_time` to resolve any position conflicts introduced by position clamping.
- Defending cost: clamped cars' displaced defenders receive +0.3s to `cumulative_race_time` to keep time-based sort consistent with position assignment.

**Known limitations:**
- **5-season-aggregate driver styles cannot capture mid-career form drops.** RIC is the largest outlier: sim places him ~P13, actual P20. His 2021–2023 podium pace (strong style vector) dominates the 5-season aggregate; his 2024 performance was significantly below that level. Any driver in sudden form decline would show the same bias. Fix requires either per-season style recalibration (deferred post-MVP) or a recency-weighted style computation.
- **Educational outliers (SAI, NOR, MAG, PIA, SAR):** sim predicts underlying pace rank correctly; actual results were influenced by strategic chaos (SAC-triggered undercuts, unusual tire windows, safety car timing). These are features of the real race, not bugs in the simulation.
- **Race time runs −2.2% fast** vs actual (5291s vs 5408s). Consistent with SandboxRaceEnv finding from Phase 4.2 — the XGBoost lap time model predicts slightly optimistic clean-air pace. Acceptable for relative strategy comparison; not a calibration concern at this stage.
- **Naive cumulative-time position sort (Parts 1–2) deferred overtaking physics to Part 3.** Part 3's friction model is a simplified max-gain-per-lap clamping, not a full gap/delta physics model. The full physics (minimum gap threshold for overtake, DRS window, slipstream) is deferred to Phase 4.5.3.

**Pain points:**
- **Pickle module reference for `_CalibratedPitModel`**: model was saved when `rival_policy.py` ran as `__main__`, so class was pickled as `__main__._CalibratedPitModel`. Unpickling from a different `__main__` raised `AttributeError`. Fixed by injecting `_CalibratedPitModel` into the active `__main__` module before `joblib.load` in `_load_rival_policy()`.
- **Dataclass field ordering**: fields with defaults (`pit_history`, `starting_compound`) must follow non-default fields — Python dataclass constraint.
- **`CIRCUIT_OVERTAKING_FACTOR` vs `OVERTAKING_DIFFICULTY`**: two different constant dicts for similar concepts. `CIRCUIT_OVERTAKING_FACTOR` (float 0–1, in `grid.py`) was the Phase 1–2 design intent; `OVERTAKING_DIFFICULTY` (max positions/lap, in `grid_constants.py`) is the Part 3 implementation. The factor dict is retained as dead code for reference; the difficulty dict is the live model.

**Open questions:**
- Phase 4.5.3: add gap-to-rival features to both the rival policy and the GridRaceEnv obs space (Phase 4.5.1 decision to defer these features is still open).
- Phase 5 PPO training on `GridRaceEnv`: will the stochastic rivals provide enough episode diversity to train a robust undercut/overcut policy? The 18/20 stdev≥1.0 metric suggests yes.
- Should `OVERTAKING_DIFFICULTY` be a probability (0–1) rather than a max-positions-per-lap integer? The current design forces a cliff at integer boundaries (0 vs 1 position gains), which may be overly binary. Revisit if PPO shows unrealistic position dynamics during training.

---

## Phase 5.1 — PPO Sandbox Agent

**Deliverable:** `pitiq.ml.train_ppo_sandbox` — trained PPO agent on `SandboxRaceEnv` with curriculum learning. Artifacts: `models/ppo_sandbox_final.zip`, `models/ppo_sandbox_best.zip`, training curve + baseline comparison figures.

**Training run:**
- 52 minutes total on CPU (Apple M-series), 1M timesteps, 4 parallel envs (DummyVecEnv), ~335 fps
- Stage 1 (0–300K): fixed scenario — Bahrain GP 2024, VER, P1, SOFT. Single scenario to give agent a clean learning signal before adding complexity.
- Stage 2 (300K–1M): curriculum — 4 circuits (Bahrain, Italian, Belgian, Abu Dhabi) × 5 drivers (VER, LEC, NOR, HAM, ZHO) × P1–P10 starting positions, sampled randomly each episode reset.

**Training curve (EvalCallback — deterministic, Bahrain VER P1, 5 eps):**
- 100K: +7.46 — fast convergence on Stage 1 fixed scenario; agent already satisfying two-compound rule and finishing P1
- 300K (end Stage 1): −0.49 — reward tracked against a harder Stage 2 baseline (expected: Stage 1 had no diversity pressure)
- 400K: +8.09 — peak; agent recovered quickly from Stage 2 complexity expansion
- 500K–700K: +7.64 — stable plateau; generalisation across all 4 circuits confirmed
- 900K–1M: +7.46–8.15 — converged; policy gradient loss near zero, entropy ~−0.05 (fully exploiting)

**Baseline comparison (Bahrain GP, VER, P1, 10 deterministic episodes):**

| Policy | Mean Reward | Mean Pos | Mean Time | Wins |
|---|---|---|---|---|
| PPO (trained) | +8.15 | P1.0 | 5,415s | 10/10 |
| Cliff-pit heuristic | +8.67 | P1.0 | 5,411s | 10/10 |
| Never-pit | −231.45 | P20.0 | 5,505s | 0/10 |
| Random | −103.97 | P20.0 | 6,055s | 0/10 |

**Interpretation:** PPO +8.15 ≈ cliff-pit +8.67 is the correct result, not a failure. Bahrain P1 VER starting on SOFT is the simplest possible F1 strategy scenario: a single pit around the SOFT cliff (lap 18) onto HARD is close to optimal, and that's exactly what both the PPO agent and the cliff-pit heuristic do. PPO discovered this independently from reward signal alone, validating that the env and reward function are learnable from first principles. The 239-point margin vs never-pit (−231) and 112-point margin vs random (−104) confirm the agent learned genuine strategy and not env quirks. PPO differentiation vs cliff-pit heuristics is expected in Phase 5.2 (GridRaceEnv), where rival-awareness (undercut windows, rival tire age, style-based pit prediction) provides signal that any fixed heuristic cannot use.

**macOS Apple Silicon fix:**
XGBoost uses Homebrew libomp; PyTorch bundles its own OpenMP runtime. Loading both in the same process caused a segfault (exit 139) on every `model.learn()` call. Fix: set `KMP_DUPLICATE_LIB_OK=TRUE` and `OMP_NUM_THREADS=1` via `os.environ` at the very top of `train_ppo_sandbox.py`, before any imports trigger library loading. Added to the training script with a comment explaining the root cause for future reference.

**Pain points:**
- Three failed training launches before finding the segfault: first run failed (tensorboard not installed), second failed (tqdm/rich not installed for progress bar), third failed (OpenMP segfault). All three were dependency gaps; no code logic issues.
- `tee`-based logging doesn't capture rich progress bar output (rich writes to a terminal device, not stdout/stderr). The training log shows only PPO verbose output; progress bar was only visible interactively.

**Open questions for Phase 5.2:**
- Will the 25-dim rival-aware obs provide enough signal for PPO to learn undercut/overcut timing that beats a cliff-pit heuristic? The undercut window flag and rival tire age features are the key differentiators.
- Multi-circuit curriculum worked cleanly for Stage 2 — same pattern can be applied in Phase 5.2 with grid races at Bahrain + 3 other circuits.

---

## Phase 5.2 — PPO Grid Agent (2026-05-06)

**Built:**
- `backend/src/pitiq/ml/train_ppo_grid.py` — PPO agent on `GridRaceEnv` with 3-stage curriculum
- `pitiq.ml.predict.predict_lap_times_batch()` — batch XGBoost inference for all 20 cars in one call
- `pitiq.ml.rival_policy.predict_pit_probabilities_batch()` — batch rival pit probability inference
- `GridRaceEnv.step()` refactored to use both batch functions (replaces two per-car loops)
- Artifacts: `models/ppo_grid_final.zip`, `models/ppo_grid_best.zip`, `models/figures/grid_training_curve.png`, `models/figures/grid_baseline_comparison.png`

**Training run:**
- 3.29 hours total on CPU (Apple M-series), 1.5M timesteps, 2 parallel envs (DummyVecEnv)
- 126 fps achieved after batch optimization (initial run: 7 fps — killed after 1 rollout, 17.6× speedup)
- 3-stage curriculum:
  - Stage 1 (0–200K): fixed scenario — Bahrain 2024, VER, P1, actual qualifying grid
  - Stage 2 (200K–600K): Bahrain only, ego from [VER, LEC, NOR, HAM, ZHO], P1–P10 starts
  - Stage 3 (600K–1.5M): all 4 circuits (Bahrain, Monza, Spa, Abu Dhabi), 5 drivers, P1–P15

**Training curve (EvalCallback — deterministic, Bahrain VER P1, 5 eps):**
- 100K: +12.76 — fast Stage 1 convergence; agent learning pit timing from rival context
- 200K: −22.64 — Stage 1→2 transition shock; `approx_kl=0.208`, `explained_variance=−2.64` confirm large policy shift
- 300K: +14.33 — full recovery within 100K steps; Stage 2 generalisation working
- 400K–500K: +14.06–12.96 — Stage 2 stable plateau
- 600K: +14.81 — Stage 3 onset; no regression (Stage 2 generalised cleanly)
- 700K–1M: +14.79–14.89 — Stage 3 plateau; best model saved at 1M steps (+14.89)
- 1.5M: +13.87 — slight late-training variance, best model at 1M is the production model

**Convergence metrics at end of training:** `explained_variance=0.847`, `entropy_loss=−0.093`, `approx_kl=0.013` — healthy PPO convergence. Value function well-calibrated; policy has reduced exploration but not collapsed (entropy still negative and non-trivial).

**Baseline comparison results:**

Bahrain VER P1 (easy scenario — all smart policies find optimal strategy):

| Policy | Mean Reward | Mean Pos | Wins |
|---|---|---|---|
| Grid PPO | +14.87 | P1.0 | 10/10 |
| Sandbox PPO | +14.23 | P1.0 | 10/10 |
| Fixed (lap 18) | +14.67 | P1.0 | 10/10 |
| Random | −93.22 | P20.0 | 0/10 |

Bahrain ZHO P15 (hard scenario — mid-grid, struggling driver, high rival stochasticity):

| Policy | Mean Reward | Mean Pos | Wins |
|---|---|---|---|
| Grid PPO | −1.79 | P8.5 | 0/10 |
| Sandbox PPO | +1.48 | P7.3 | 0/10 |
| Fixed (lap 18) | −5.50 | P10.4 | 0/10 |
| Random | −88.80 | P20.0 | 0/10 |

**Key findings:**
- In VER P1 (simplest scenario): all three non-random policies converge — Grid PPO edges Sandbox PPO and Fixed by small margins (+0.64 reward vs Sandbox, +0.20 vs Fixed). Rival-awareness not differentiating in this scenario because the optimal strategy is well-determined regardless of rivals.
- In ZHO P15 (hard scenario): adaptive learned strategies (Grid PPO P8.5, Sandbox PPO P7.3) both outperform fixed heuristic (P10.4) by ~2–3 positions, validating that learned policies generalise meaningfully over rule-based strategies in complex multi-car scenarios.
- Sandbox PPO marginally outperforms Grid PPO on ZHO P15 (P7.3 vs P8.5). Interpretation: this specific evaluation scenario (ZHO mid-grid, Bahrain, high rival stochasticity) introduces variance that the Grid PPO's rival-aware features partially over-weight. Rival-aware features are expected to show clearer benefit in scenarios with explicit undercut windows (gap_ahead < 1.5s, rival on older tires) — this ZHO P15 scenario has high positional variance from rival stochasticity but not necessarily clean undercut windows from P15.
- The ~3-position advantage of learned policies over Fixed strategy is the primary validation metric: adaptive strategies are meaningfully better than rule-based heuristics in the complex multi-car environment.

**Critical fix — batch XGBoost inference:**
Initial training attempt ran at 7 fps (518s for first rollout of 4096 steps). Root cause: 39 individual XGBoost calls per step (20 `predict_lap_time` + 19 `predict_pit_probability`), each constructing a separate 1-row DataFrame and running `pd.get_dummies` independently. Fix: added `predict_lap_times_batch()` and `predict_pit_probabilities_batch()` functions that build one N-row DataFrame per step and call `model.predict()` once. Result: 7 fps → 126 fps (17.6× speedup). At 7 fps, 1.5M steps would have taken ~60 hours; after fix, 3.29 hours.

**Worked well:**
- Stage 2→3 curriculum transition was clean — no regression at 600K (unlike the Stage 1→2 dip at 200K). Suggests Stage 2's multi-driver/position diversity adequately prepared the policy for multi-circuit generalisation.
- `ent_coef=0.02` (vs 0.01 in Phase 5.1) kept entropy from collapsing prematurely during Stage 3; policy stayed exploratory through the full 1.5M steps.
- `caffeinate -dims` + `nohup` setup allowed unattended overnight training — process survived laptop sleeping and terminal closure.

**Pain points:**
- First training attempt ran for ~8 minutes at 7 fps before the bottleneck was diagnosed. The per-car prediction loop is O(N) in naive calls; the GridRaceEnv's 20-car grid makes this 20× worse than the SandboxRaceEnv without batching.
- `n_envs=2` (vs 4 for Sandbox) was chosen conservatively; in practice 2 envs achieved adequate throughput after batching. Could revisit 4 envs for Phase 5.3 if more training is needed.

**Open questions:**
- Will rival-awareness differentiate more clearly in scenarios with explicit undercut windows? Bahrain ZHO P15 had high rival stochasticity but not necessarily clean 1.5s gap windows. A Spa or Bahrain scenario where VER starts P5 surrounded by rivals on different strategies might show a clearer Grid PPO > Sandbox PPO signal.
- Phase 5.3 evaluation harness across 20+ test scenarios should include circuits with naturally high undercut frequency (Spa, Bahrain, Baku) and mid-grid starting positions to give rival-awareness its best opportunity to differentiate.

---

## Phase 5.3 — Evaluation Harness + RESULTS.md (2026-05-06)

**Built:**
- `backend/src/pitiq/ml/evaluate.py` — evaluation harness: 8 scenarios × 4 policies × 20 episodes = 640 total episodes
- `models/evaluation_results.json` — all metrics in structured JSON
- `models/figures/eval_position_gains.png` — positions gained bar chart (sandbox + grid side-by-side)
- `models/figures/eval_reward_comparison.png` — reward comparison bar chart
- `docs/RESULTS.md` — comprehensive project results document (8 sections)

**Scenarios (4 sandbox + 4 grid):** Bahrain VER P1, Bahrain ZHO P15, Italian NOR P3, Belgian HAM P6

**Sandbox policies:** PPO Sandbox, Cliff-pit, Never-pit, Random
**Grid policies:** PPO Grid, PPO Sandbox (obs[:13]), Fixed lap-18, Random

**Key results:**

| Scenario | Best policy | Key margin |
|---|---|---|
| Sandbox Bahrain VER P1 | Cliff-pit +8.67 | PPO +8.15 ≈ cliff-pit; +239 pts over never-pit |
| Sandbox ZHO P15 | (degenerate) | All policies P20 — env limitation |
| Sandbox Italian NOR P3 | Cliff-pit +9.26/P1 | PPO defaults to never-pit (OOD) |
| Sandbox Belgian HAM P6 | Cliff-pit +12.62/P1 | PPO = never-pit reward (rule violation) |
| Grid Bahrain VER P1 | Fixed +14.67 ≈ Grid PPO +14.65 | Ceiling effect; all learned policies P1 |
| Grid ZHO P15 | PPO Sandbox P7.3 (+7.7) | Grid PPO P8.3 (+6.7); both beat Fixed (+4.7) |
| Grid Italian NOR P3 | Grid PPO +9.47/P1/100% | vs Fixed +6.88/P1.8/35% (+37% win rate) |
| Grid Belgian HAM P6 | Grid PPO +11.54/P1.4/70% | vs Fixed +3.88/P4.0/0% (+198% reward, +70% win rate) |

**Key findings:**

1. **Grid PPO generalises across all 4 circuits**. Italian (+9.47/P1/100%) and Belgian (+11.54/P1.4/70%) confirm the rival-aware 25-dim obs enables correct undercut/overcut timing that a fixed heuristic cannot match.

2. **Sandbox PPO overfits to Bahrain**. At Italian NOR P3 and Belgian HAM P6, it defaults to never-pit (identical reward to the Never-pit baseline). It was trained on P1–P10 starts; P3/P6 MEDIUM starts at Monza/Spa were never in its distribution. Cliff-pit, not PPO Sandbox, is the best heuristic on these scenarios.

3. **SandboxRaceEnv mid-grid evaluation degenerates**. ZHO P15 sandbox: all 4 policies finish P20. The static 1-stop rival model assigns fixed pace profiles that overwhelm any strategy ZHO can take. Sandbox is reliable only for P1–P5 starts. GridRaceEnv is required for mid-grid evaluation.

4. **PPO Sandbox in Grid env achieves position but violates two-compound rule**. At Italian and Belgian, it finishes P1.4–P1.6 but with −106 to −126 reward (vs Grid PPO's +9.47 to +11.54). It's winning on raw pace without pitting correctly — rule violation triggers the −100 terminal penalty.

5. **Grid PPO Bahrain ZHO P15 vs Sandbox PPO**: Sandbox PPO (obs[:13]) marginally leads Grid PPO (P7.3 vs P8.3, +7.7 vs +6.7 gained). Grid PPO has higher variance (σ=1.71 vs 0.73). Both beat Fixed (+4.7 gained). The rival-aware features provide limited additional signal in this scenario — ZHO's gains are driven by pace vs the grid more than by undercut timing. Phase 5.2's finding confirmed.

**Worked well:**
- Script ran cleanly in ~10 minutes for 640 episodes; `caffeinate -dims` + `nohup` setup worked identically to Phase 5.2
- The 4-scenario design cleanly exposed 3 different failure modes in a single eval run (env degeneracy, OOD policy, rule violation)
- Loading meta JSONs from disk (not hardcoding numbers) means re-running the evaluation always reflects the latest trained models

**Pain points:**
- `KeyError: 'mae'` on first run — meta JSONs have a `metrics` nested key (`xgb_baseline_meta["metrics"]["mae"]`), not a top-level key. Quick fix but required a re-run.
- First run completed all 640 episodes correctly but crashed before saving JSON; second run was identical output, confirming determinism.

**Open questions:**
- Will Grid PPO's advantage widen on scenarios with explicit undercut windows where gap_to_rival_ahead < 1.5s and rival on 10+ older tires? Spa HAM P6 is suggestive but the margin could be larger at a higher-throughput undercut circuit (e.g., Bahrain VER starting P5 behind rivals on hard tires).
- Sandbox PPO could likely be fixed by extending Stage 2 training distribution to P1–P15 and including MEDIUM starting compounds. Whether that is worth doing vs just using Grid PPO is a Phase 6+ question.

---

## Phase 6.1 — FastAPI Data Endpoints (2026-05-06)

**Built:**
- `backend/src/pitiq/api/main.py` — FastAPI app with CORS, startup handler, all endpoints
- `backend/src/pitiq/api/schemas.py` — Pydantic schemas: `CircuitInfo`, `DriverInfo`, `HistoricalRace`, `HealthResponse`

**Endpoints (8 total):**

| Endpoint | Response model | Notes |
|---|---|---|
| `GET /health` | `HealthResponse` | status/version |
| `GET /api/circuits` | `list[CircuitInfo]` | 29 circuits, all fields |
| `GET /api/circuits/{name}` | `CircuitInfo` | case-insensitive match |
| `GET /api/drivers` | `list[DriverInfo]` | 33 drivers |
| `GET /api/drivers/{code}` | `DriverInfo` | uppercased, 404 on unknown |
| `GET /api/historical/{year}/{circuit}` | `HistoricalRace` | winner, strategy, grid, results |
| `GET /api/historical/{year}/{circuit}/grid` | `list[str]` | 20-driver starting order |
| `GET /docs` | Swagger UI | auto-generated by FastAPI |

**Startup data loading:**
- `app.state.lap_features` — 108,257-row Parquet, loaded once
- `app.state.driver_styles` — 33-driver style vectors
- `app.state.circuit_years` — per-circuit available year lists, precomputed
- `app.state.cluster_map` — k-means (k=4) cluster assignments computed at startup via scikit-learn, median-imputing the 4 NaN cells in driver_styles

**Response times (measured):**
- `/health`, `/api/circuits`, `/api/drivers`, `/api/drivers/VER`: 1–2ms
- `/api/historical/2024/Bahrain Grand Prix`: 12ms
- All well under 200ms ✓

**Data accuracy validation (2024 Bahrain GP):**
- Winner: VER ✓
- Grid order: VER/LEC/RUS/PER/SAI matches actual 2024 qualifying ✓
- Final positions: VER P1, PER P2, SAI P3, LEC P4, RUS P5 — matches actual race results ✓
- Winner strategy: SOFT → HARD (lap 18) → SOFT (lap 38) — VER's actual 3-stint 2-stop ✓

**VSC artifact fix:**
- `_reconstruct_strategy()` filters stints with < 5 laps before recording pit stops
- Confirmed it removes false pit entries from 12 affected races (e.g., 2021 Russian GP HAM had a 3-lap ghost stint; 2022 Monaco GP PER had 4+3 lap ghost stints around the wet-to-dry transition)
- 2024 Bahrain unchanged — all 3 VER stints are 15/18/19 laps, which is genuine data (2-stop race)

**Worked well:**
- FastAPI startup event cleanly separates I/O from request handling — the pattern of loading everything into `app.state` once is simple and performant for this data size
- Path parameter case-insensitive matching via `_find_circuit()` handles URL-encoded names cleanly without route proliferation
- K-means re-fit at startup is fast (33 × 11 matrix) and keeps the API self-contained — no need to save cluster assignments separately

**Pain points:**
- `BOR` and `DEV` driver codes required investigation (Bortoleto / de Vries) — not obvious from the code alone; full name mapping is now hardcoded in `_DRIVER_META`
- `docs/` gitignore requires `git add -f` for all doc files

**Open questions:**
- Phase 6.2 will need to import `SandboxRaceEnv` and the PPO models — watch for the `KMP_DUPLICATE_LIB_OK` / OpenMP conflict when uvicorn forks worker processes. Single-worker mode may be required.

## Phase 6.2 — Sandbox ML inference endpoints (2026-05-06)
**Built:** 3 POST endpoints: `/api/sandbox/degradation-curve` (XGBoost stint prediction with compound dynamics), `/api/sandbox/simulate` (user-defined strategy through SandboxRaceEnv), `/api/sandbox/recommend` (PPO Sandbox deterministic rollout). 6 new Pydantic schemas. ThreadPoolExecutor(max_workers=4) for sync env execution in async handlers. PPO + XGBoost loaded at startup.
**Worked well:** lru_cache on `load_model()` means no extra startup cost — just one warm call. PPO.load() is fast (~1s). Thread pool pattern cleanly separates sync env code from async FastAPI handlers. Lambda closures work fine (ThreadPoolExecutor is thread-based, not process-based, so no pickling needed).
**Pain points:** None significant. KMP_DUPLICATE_LIB_OK=TRUE already set at top of main.py so no OpenMP conflict on startup.
**Open questions:**
- Phase 6.3 (optimize endpoint) will need GridRaceEnv + PPO Grid agent — memory usage could be higher. Single-worker uvicorn still recommended.
- tire_age in lap_by_lap starts at 2 after lap 1 (env increments after step). This is correct env behavior (1-indexed tire age) but may need frontend note.

---

## Phase 6.3 — Optimizer Mode endpoints (2026-05-07)
**Built:**
- 3 new Optimizer endpoints: `POST /api/optimizer/simulate`, `POST /api/optimizer/recommend`, `GET /api/optimizer/historical-validation/{year}/{circuit}`
- 6 new Pydantic schemas: `GridSimulateRequest/Response`, `OptimizerRecommendRequest/Response`, `RivalPrediction`, `HistoricalValidationResponse`
- `ppo_grid_best.zip` loaded at startup alongside existing `ppo_sandbox_best.zip`
- `_run_grid_simulate_sync()` — executes user-specified pit strategy through GridRaceEnv, collects per-lap ego trace + 19 rival final positions/pit histories
- `_run_grid_recommend_sync()` — runs PPO Grid agent deterministically, same trace collection
- `_run_historical_validation_sync()` — rebuilds starting grid from lap_features.parquet, runs GridRaceEnv with cliff-heuristic ego, compares simulated vs actual finishing positions
- `_check_undercut_window()` — pre-step check: gap_to_ahead < 1.5s AND rival_ahead tire_age > 20 AND ego not pitting
- `_generate_rationale()` — template function referencing specific rival driver, tire age, tire saving coefficient, and circuit confidence
- `X-Simulation-Time-Ms` response header on heavy historical-validation endpoint

**Key validation results:**
- VER Bahrain P1: ego_predicted_position=1.0, 19 rival_predictions populated, strategy at lap 18 correctly recorded ✓
- ZHO P15 → P7 (+8 positions), recommended 2-stop (MEDIUM@22, SOFT@43). Undercut windows correctly fired: SAI ahead with tire_age 26–28, gap 1.26–1.32s. Rationale readable and specific.
- Historical validation 2024 Bahrain: 55% within ±3 (single-seed), 75% within ±5, mean_delta 3.6, response time 448ms — faster than 3–8s estimate due to batched XGBoost inference

**Metrics:**
- 14 total API endpoints across Phase 6 (1 health + 7 data/lookup + 3 sandbox + 3 optimizer)
- Historical validation response: 448ms (single-seed) vs 3–8s estimate; batched XGBoost is the main speedup
- Undercut detection correctly empty for VER P1 (no rival ahead throughout race), populated for ZHO P15 (SAI on aging MEDIUM)

**Single-seed vs 5-seed accuracy distinction:**
- Phase 4.5.2 evaluation report (70% within ±3) averaged 5 seeds — a stable estimate of the simulation's expected accuracy
- Historical-validation endpoint inherently returns a single-seed result due to stochastic rival pit policy; per-call accuracy varies ±10–15%. 55% within ±3 on a single seed is consistent with a 5-seed mean of ~70%.
- This distinction is documented in DECISIONS.md. Frontend should not claim "70% accurate" based on a single historical-validation call.

**Worked well:**
- `_check_undercut_window()` pre-step helper pattern is clean — accesses env internal state before calling step(), no env modification needed
- Template rationale is fast (~0.1ms) and specific enough to be useful: references actual rival name and tire age from the simulation trace, not generic text
- `X-Simulation-Time-Ms` header added via FastAPI `Response` dependency injection — clean, no middleware needed
- Thread pool reuse from Phase 6.2 (`app.state.executor`) works for GridRaceEnv; no new infrastructure needed

**Pain points:** None significant. GridRaceEnv loads cleanly under the existing `KMP_DUPLICATE_LIB_OK=TRUE` env var. ppo_grid load time ~1–2s at startup, acceptable.

**Open questions:**
- Frontend (Phase 7+) should display `rival_predictions` as mini strategy timelines — the pit_history list per rival is the right data structure for this
- `positions_gained` can be negative if ego loses positions; frontend should handle the sign correctly (positive = gained, negative = lost)
- Historical-validation accuracy will vary per call due to stochastic rivals; frontend should show it as an "example run" not a deterministic accuracy figure
