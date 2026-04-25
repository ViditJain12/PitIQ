# Architecture Decisions

> Append a short entry whenever you make a non-obvious technical choice. Future you will thank you.

**Format:**
```
## YYYY-MM-DD — [Decision title]
**Context:** What was the situation/problem
**Decision:** What you chose
**Why:** Reasoning
**Alternatives considered:** What else you weighed
```

---

## Initial Decisions (Phase 0)

## 2026-04-22 — Python 3.13 instead of 3.11
**Context:** ROADMAP specifies Python 3.11+; only Python 3.13 was available via Homebrew on this machine.
**Decision:** Use Python 3.13 for the venv.
**Why:** `pyproject.toml` specifies `requires-python = ">=3.11"`, so 3.13 fully satisfies it. All deps resolved cleanly.
**Alternatives considered:** Installing 3.11 via `pyenv` (unnecessary overhead given 3.13 works).

## 2026-04-22 — libomp as a system dep for XGBoost on macOS ARM
**Context:** XGBoost 3.x on Apple Silicon requires OpenMP (`libomp.dylib`), which is not bundled in the wheel.
**Decision:** Document `brew install libomp` as a required system dep for local dev on macOS.
**Why:** No pure-Python fallback; without it XGBoost won't load.
**Alternatives considered:** Pinning an older XGBoost (rejected: newer versions have better Python 3.13 support).

## 2026-04-23 — Timedelta columns converted to float seconds before Parquet write
**Context:** FastF1 returns `LapTime`, `Sector1/2/3Time`, `PitInTime`, `PitOutTime` as `timedelta64[ns]`. PyArrow (the Parquet backend) does not have a native timedelta type and raises a conversion error on write.
**Decision:** Convert all timedelta columns to float seconds via `.dt.total_seconds()` at extraction time in `_extract_session()`.
**Why:** Float seconds is the natural unit for ML features anyway (XGBoost, feature engineering all expect numeric inputs). Keeping them as timedeltas would require conversion at every downstream consumer.
**Alternatives considered:** Storing as integer nanoseconds (rejected: harder to read and reason about); storing as strings (rejected: lossy and slow to re-parse).

## 2026-04-23 — Hardcoded circuit lookup table (vs. external data source)
**Context:** Circuit metadata (length, type, pit loss) is needed as ML features but is not available from FastF1 in a structured, reliable format.
**Decision:** Hardcode a Python dict of 29 circuits with manually researched values.
**Why:** The alternative — scraping Ergast, Wikipedia, or a third-party F1 API — adds a network dependency to a build step that should be fully reproducible offline. Circuit metadata changes very rarely (maybe once a decade for a new layout). A hardcoded dict is easy to audit, correct, and version-control. All 29 values were verified against known sources.
**Alternatives considered:** Ergast API circuit data (rejected: adds network dependency, Ergast is being sunset); Wikipedia scraping (rejected: fragile, unversioned); FastF1 circuit info (rejected: doesn't include pit-loss estimates).

## 2026-04-23 — Session-level is_wet flag (vs. lap-level)
**Context:** Weather data from FastF1 is a time-series with `Rainfall` (bool) sampled every ~60s during the session. Mapping this to individual laps requires a timestamp merge.
**Decision:** Aggregate to session level: `is_wet = Rainfall.any()` across all weather samples for the session.
**Why:** Session-level is sufficient for the current XGBoost model — the primary signal is whether the race was wet at all (compound choice, pace deltas). The added complexity of lap-level merging is not worth it unless wet-race accuracy proves poor.
**Alternatives considered:** Lap-level Rainfall join by timestamp (possible, deferred); per-lap rolling weather window (complex, overkill for now).
**Revisit trigger:** If Phase 3 XGBoost shows poor MAE on wet-race sessions specifically, upgrade to lap-level merging.

## 2026-04-23 — Australian GP classified as permanent (not street)
**Context:** Albert Park uses public roads closed for the race weekend, which superficially resembles a street circuit. Initial classification was street.
**Decision:** Reclassify as permanent.
**Why:** The FIA officially classifies Albert Park as a semi-permanent circuit, which for strategy and tyre modelling purposes aligns with permanent-circuit behaviour (consistent asphalt, predictable degradation, no sharp barriers limiting overtake). Using street classification would incorrectly inflate pit-loss estimates and misclassify the circuit's degradation profile.
**Alternatives considered:** Separate "semi-permanent" category (rejected: only one circuit, adds complexity without proportional benefit).

## 2026-04-22 — Tailwind CSS v4 (not v3)
**Context:** `npm install tailwindcss` pulled v4.2.4. v4 has a completely different config model — no `tailwind.config.js`, no `postcss.config.js`; uses a Vite plugin instead.
**Decision:** Stay on v4 with `@tailwindcss/vite` plugin.
**Why:** v4 is the current release, the Vite plugin is simpler than the PostCSS pipeline, and the project has no legacy v3 constraints.
**Alternatives considered:** Pinning v3 (rejected: unnecessary regression; v4 plugin approach is cleaner for a greenfield project).

## 2026-04-22 — CSS custom properties for design tokens, not Tailwind config
**Context:** F1 team colors and surface tokens need to be reusable across components without Tailwind class sprawl.
**Decision:** Define all tokens as CSS `--var` properties in `index.css`; reference them via `style={{ color: 'var(--accent)' }}` in components.
**Why:** Tailwind v4 config-based theme extension is more complex and less portable; CSS vars are readable, work in inline styles, and will integrate cleanly with Recharts chart colors (which need JS-accessible values anyway).
**Alternatives considered:** Tailwind `theme.extend.colors` (rejected for v4: extra config complexity); hard-coded hex values (rejected: no single source of truth).

## 2026-04-23 — Fuel correction formula and constants
**Context:** Lap times in early race laps are artificially slow due to heavy fuel load. Without correction, a lap 1 time and a lap 50 time from the same driver on the same tyre look different even if the underlying pace is identical. The ML model would learn a spurious "lap number effect" instead of tyre degradation.
**Decision:** `LapTimeCorrected = LapTime − max(0, 110kg − (LapNumber−1) × 1.8kg) × 0.03 s/kg`. Constants: `FUEL_START_KG=110`, `FUEL_BURN_KG_PER_LAP=1.8`, `FUEL_EFFECT_S_PER_KG=0.03`.
**Why:** 110 kg is the standard FIA maximum fuel load for a race. 1.8 kg/lap is the widely-cited F1 burn rate. 0.03 s/kg is the industry-standard lap-time sensitivity figure used by teams and analysts. These are the same constants used in academic F1 strategy literature (e.g. Heilmeier et al. 2020).
**Alternatives considered:** Per-circuit, per-season constants derived empirically (better accuracy, but requires the model we haven't built yet — can revisit in Phase 3 if baseline MAE is poor); no fuel correction (rejected: confounds tyre degradation signal with fuel mass effect).

## 2026-04-23 — Drop IsAccurate=False laps as cleaning policy
**Context:** FastF1 marks laps as `IsAccurate=False` when timing data is incomplete, unreliable, or the lap crossed a session boundary (e.g. VSC, red flag, in/out laps). These laps do not represent true race pace and would add noise to lap time prediction.
**Decision:** Drop all `IsAccurate=False` laps as the first cleaning step. This removed ~13% of raw laps (16,798 of 125,055).
**Why:** The XGBoost model is trained to predict competitive race pace. Including non-representative laps would widen prediction error without adding signal. FastF1's `IsAccurate` flag is conservative — it errs toward marking borderline laps as inaccurate, so the false-positive rate is low.
**Alternatives considered:** Keeping inaccurate laps and adding `IsAccurate` as a feature (rejected: the model should not learn from corrupt data); manual per-lap filtering (rejected: `IsAccurate` captures exactly the right set for our use case).

## 2026-04-23 — Per-season Parquet files + combined laps_all.parquet
**Context:** Need a storage layout for 5 seasons of lap data that supports both full re-ingestion of a single season and combined multi-season training datasets.
**Decision:** Produce one `laps_{year}.parquet` per season during ingest, then combine into `laps_all.parquet` during the clean step. Both live in `data/processed/`.
**Why:** Per-season files allow re-running a single season's ingest without invalidating other seasons (important when FastF1 retroactively corrects data). The combined file is the single input for all downstream ML steps — no joins or glob patterns needed. Clean step is idempotent and fast (<1s to rebuild `laps_all.parquet` once per-season files exist).
**Alternatives considered:** Single combined Parquet updated incrementally (rejected: no clean re-ingest path for one season); one file per race (rejected: too many files, slower to load for training).

## 2026-XX-XX — Parquet over SQLite for data storage
**Context:** Need to store ~120K rows of lap data + telemetry across 5 seasons.
**Decision:** Parquet files in `data/processed/`.
**Why:** Faster columnar reads for ML pipelines, schema-on-read, no DB server to manage. SQLite would add overhead for a workload that's effectively read-only after ingest.
**Alternatives considered:** SQLite (rejected: unnecessary for analytical workload), DuckDB (good option, can revisit if querying becomes complex).

## 2026-04-24 — Split train/val/test BY RACE not random rows
**Context:** ML pipeline needs train/val/test splits. The dataset has 113 race weekends across 5 seasons (2021–2025).
**Decision:** Split by race weekend: train = 2021–2024 full seasons, val = 2025 rounds 1–12, test = 2025 rounds 13–24. All laps from a given race stay together.
**Why:** Random row splitting causes data leakage — the model sees laps from the same race in both train and test (same track conditions, weather, rival behaviour). This inflates val/test metrics by letting the model memorise race-specific effects rather than generalising. Splitting by race forces generalisation to unseen race weekends. Using 2025 as the holdout year also provides temporal separation (model must generalise forward in time), which matches real-world deployment.
**Alternatives considered:** Random 80/10/10 (rejected: leakage); split by season (train 2021–2023, val 2024, test 2025 — acceptable but reduces training data and val diversity); per-circuit stratified split (rejected: leaks temporal patterns).

## 2026-04-24 — Proceed to Phase 3 despite confounded EDA degradation plots
**Context:** Three iterations of tire degradation visualization (absolute, per-stint relative, controlled-conditions) all produced physically implausible curves at most circuits. Belgian GP was the only circuit to show a clean monotonic upward curve.
**Decision:** Accept the EDA limitation and proceed to Phase 3 (XGBoost training) without resolving the visualization confounds.
**Why:** The confounds are well understood (tire warm-up laps 1–5, traffic clearing mid-stint, Pirelli compound-allocation bias per circuit) and are all lap-level contextual effects that XGBoost will learn directly from features (`tire_age`, `Stint`, `position`, `laps_remaining`). EDA plots are aggregate views that can't condition on these variables simultaneously. The Belgian GP curve proves the degradation signal exists in the data. Poor MAE in Phase 3 on specific circuits would be a more actionable signal than better-looking EDA plots.
**Alternatives considered:** Further EDA iteration with per-driver-per-stint normalization (rejected: adds complexity, still wouldn't remove warm-up effect); adding a `is_warmup_lap` binary feature to the feature set (possible, deferred to Phase 3 feature importance analysis).

## 2026-04-24 — Renamed tire_deg_rate_* to pace_trend_* 
**Context:** Initial implementation named the OLS slope columns `tire_deg_rate_{soft,medium,hard}`. First run showed most slopes were negative — physically impossible if interpreted as tire degradation rates.
**Decision:** Rename to `pace_trend_{soft,medium,hard}` and update docstring to explain the measurement.
**Why:** The slopes measure net pace change (tire degradation minus track evolution) in the stint-1, green-flag, tire_age ≥ 5 window. Track evolution (rubber build-up) is a real, competing effect that often outpaces tire wear in early stints. Negative values are physically correct and expected. The old name implied pure tire wear, which is misleading. The relative driver-to-driver ordering in these slopes is still a valid style signal for XGBoost.
**Alternatives considered:** Filtering to later stints where track evolution is smaller (rejected: smaller sample sizes, different confounds); subtracting a circuit-level track evolution baseline (rejected: too complex, introduces new estimation error).

## 2026-04-24 — Minimum 20-lap threshold for wet_skill_delta
**Context:** First implementation computed wet_skill_delta for any driver with ≥1 wet-compound lap. HAD had 9 wet laps producing a large outlier.
**Decision:** Require ≥ 20 wet-compound laps; fewer → NaN.
**Why:** With <20 laps, a single chaotic session dominates the median. 20 laps represents at least one full wet-compound stint across 1–2 races — enough for a median to be meaningful.
**Alternatives considered:** 10-lap threshold (too few for a stable median on a noisy metric like wet pace), no threshold (produces outliers that corrupt downstream model inputs).

## 2026-04-24 — Race-normalised wet_skill_delta (vs global median)
**Context:** Initial wet_skill_delta was computed as driver median minus grid-wide INT/WET median. COL showed −9.4s and LAW −8.9s despite being rookies — implausible vs VER at −1.7s. Investigation showed COL's 31 wet laps were 24 from São Paulo 2024 (circuit INT median 82.7s) while the grid-wide INT median was 92.2s — a 9.5s circuit-speed difference unrelated to driver skill.
**Decision:** Compute wet_skill_delta as the median of per-lap deviations from the same-race, same-compound median. Each lap is compared only to other drivers at the same race on the same compound.
**Why:** Circuit speed differences (São Paulo 82.7s vs Belgium 120.2s on INT — a 37s gap) completely swamp driver skill differences (±1–2s) when using a global baseline. Race-normalisation removes this confound entirely. Post-fix COL moved to +0.36s and LAW to +0.45s (both slightly below race peers, plausible for rookies). VER moved from −1.72s to −1.11s (still correctly the fastest wet driver in the dataset).
**Alternatives considered:** Per-circuit normalisation (rejected: reduces sample sizes per driver, and same-race normalisation is strictly better since it also controls for conditions within a circuit on a given day); compound-separate global medians (rejected: doesn't address the circuit-mix problem, only the compound-type problem).

## 2026-XX-XX — Compute driver style features once, treat as static features
**Context:** Driver styles evolve over time, but recomputing dynamically is expensive.
**Decision:** Compute style vectors once across all 5 seasons, treat as static features per driver.
**Why:** Driver styles are relatively stable over a multi-season window. Dynamic recomputation adds complexity without proportional accuracy gain.
**Alternatives considered:** Per-season style vectors (revisit if accuracy is poor on early-career drivers).
