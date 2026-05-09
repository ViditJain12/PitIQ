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

## 2026-04-24 — Replaced sector_profile_{s1,s2,s3} with overall_pace_rank + sector_relative_{s1,s2,s3}
**Context:** Initial style vector included three absolute avg-rank features (`sector_profile_s1/s2/s3`). Correlation heatmap in Phase 2.5.2 revealed all three correlated at r = +0.99 — they were three noisy copies of "how fast is this driver overall," not measures of where they gain or lose time.
**Decision:** Decompose into: `overall_pace_rank` = mean(s1_rank, s2_rank, s3_rank) + `sector_relative_{s1,s2,s3}` = s{N}_rank − overall_pace_rank.
**Why:** The decomposition separates two orthogonal signals: (1) overall quality captured cleanly in one feature instead of three redundant ones, and (2) sector specialisation — whether a driver over- or under-performs relative to their own mean in each sector type (low-speed, high-speed, mixed). Post-fix inter-correlations: r = −0.40 to −0.55, expected from the sum-to-zero constraint. Feature count went from 10 → 11 (net +2 useful features, −2 redundant ones).
**Alternatives considered:** Keep only `overall_pace_rank` and drop all sector_relative (rejected: discards potentially useful specialisation signal — Phase 3 feature importance will confirm whether to drop); keep the raw three features but add PCA (rejected: adds complexity and loses interpretability).

## 2026-XX-XX — Compute driver style features once, treat as static features
**Context:** Driver styles evolve over time, but recomputing dynamically is expensive.
**Decision:** Compute style vectors once across all 5 seasons, treat as static features per driver.
**Why:** Driver styles are relatively stable over a multi-season window. Dynamic recomputation adds complexity without proportional accuracy gain.
**Alternatives considered:** Per-season style vectors (revisit if accuracy is poor on early-career drivers).

## 2026-04-26 — EventName one-hot for circuit identity (vs physical features)
**Context:** Initial XGBoost feature set used physical circuit proxies: `length_km`, `pit_loss_s`, `circuit_type`. These don't uniquely identify circuits — Hungary, Mexico, São Paulo share ~4.3km / 22s pit loss but span a 7s lap-time range. Initial MAE was 3.43s; Azerbaijan alone contributed 9.2s MAE from pure circuit confusion.
**Decision:** Add `EventName` as a one-hot categorical feature alongside the physical proxies.
**Why:** EventName uniquely identifies each circuit and lets the model learn per-circuit lap time baselines directly. Physical features are retained as they carry real signal (pit_loss_s matters for strategy; length_km correlates with lap time). EventName one-hot is safe because our 29-circuit set is fixed across all 5 training seasons; a circuit coverage sanity check in `train_baseline()` fails fast if an unseen circuit appears in val/test.
**Alternatives considered:** Physical features only (rejected: cannot distinguish same-geometry circuits); per-circuit bias term via label encoding (rejected: one-hot is more interpretable and XGBoost handles high-cardinality dummies fine at 29 circuits); generalising to physical features for new-circuit robustness (deferred: no new circuits in scope for MVP).
**Trade-off:** One-hot fails silently for circuits not in training (unknown dummies zero-filled → very poor prediction). Acceptable for MVP; revisit if F1 adds circuits.

## 2026-04-26 — Mixed-year train/val/test split (replacing all-2025-held-out)
**Context:** Original split (train=2021–2024, val=2025 R1–12, test=2025 R13–24) gave the model zero 2025 training laps. XGBoost trees cannot extrapolate past the training Year maximum (2024), so 2025 test laps were predicted using 2021–2024 average pace, producing 2–4s systematic over-prediction at circuits where F1 cars improved significantly year-over-year.
**Decision:** Restructure to train=2021–2023 + 2024 R1–20 + 2025 R1–18, val=2024 R21–24 + 2025 R19–21, test=2025 R22–24 (Las Vegas, Qatar, Abu Dhabi).
**Why:** The Sandbox/Optimizer always has access to completed historical races at inference time — including earlier rounds of the current season. Including 2025 R1–18 in training matches deployment reality. Val spans a season boundary (2024 tail + 2025 mid) to give the early stopping signal diversity.
**Alternatives considered:** Adding Year as a feature with the original split (tried — Year importance ≈ 0.0007 because trees cannot extrapolate and Year=2025 was absent from training); tweaking the 2024 boundary to include more Las Vegas/Qatar history (rejected: split-tweaking to chase a metric, doesn't address the underlying data scarcity for those circuits).

## 2026-04-26 — 6-race stratified test set (replacing 3-circuit narrow test)
**Context:** After the mixed-year split, the test set was 3 circuits (Las Vegas, Qatar, Abu Dhabi). 2 of 3 were data-scarce, making the stable-vs-sparse comparison a near-tautology. Single-circuit "stable" MAE (Abu Dhabi, 0.87s) was not a reliable headline.
**Decision:** Switch to explicit (Year, RoundNumber) stratified race selection: test = 2024 Belgian + 2024 US + 2024 Qatar + 2025 Emilia Romagna + 2025 Dutch + 2025 Las Vegas. Val = 2024 Mexico City + 2024 Abu Dhabi + 2025 British + 2025 Singapore.
**Why:** 6 circuits provide a statistically meaningful test set (~5,200 laps). Stratifying across 2024 and 2025 avoids a single-year test. Including a mix of high-data circuits (Belgian, US, Dutch: 3–4 train years each) alongside sparse circuits (Las Vegas: 2 train years) gives a genuine stable-vs-sparse split where each subset has enough laps to be meaningful. Implemented as explicit frozensets in `split.py` to be transparent and prevent boundary-creep.
**Alternatives considered:** All-2025 test (rejected: over-represents new circuits, temporal drift dominates); boundary-based split tweaking to get nicer numbers (rejected: masks data scarcity, not methodologically honest).

## 2026-04-26 — Stable vs sparse circuit reporting for test MAE
**Context:** Final 6-circuit test set: 5 stable circuits (≥3 train years) and 1 sparse circuit (Las Vegas, 2 train years). Qatar qualifies as stable (2021 + 2023 + 2025 in train) yet posts 2.1s MAE due to non-consecutive training years.
**Decision:** Report test MAE as stable (≥3 train years): 1.11s and sparse (<3 train years): 3.91s subsets, with overall 1.53s. Use stable-subset MAE as the headline number for Phase 3.1/3.2 comparison.
**Why:** Las Vegas joined the F1 calendar in 2023; Qatar runs sporadically. Their data scarcity is structural to the F1 calendar, not a model defect. Masking it by further split tweaking would be methodologically dishonest and make Phase 3.2's comparison unfair. Both phases train under identical splits, so the relative improvement metric is valid.
**Alternatives considered:** Further boundary adjustments to improve Qatar/Las Vegas MAE (rejected: split-tweaking to chase metrics; root cause is data scarcity, not split design).

## 2026-04-27 — Retain all 11 driver style features despite ablation showing only overall_pace_rank improves Phase 3
**Context:** Phase 3.2 ablation confirmed `overall_pace_rank` (rank 39/61) carries ~100% of the 13.4% MAE improvement. The other 10 style features (pace_trend_*, cornering_aggression, throttle_smoothness, wet_skill_delta, tire_saving_coef, sector_relative_*) rank 44–58/61 with combined gain ≈ 0.21% of total. Removing `overall_pace_rank` returns sparse MAE to 3.92s (≈ baseline); stable MAE barely changes (1.06s vs 1.07s).
**Decision:** Retain all 11 style features in the styled model and pass all 11 to downstream phases.
**Why:** Lap-time regression is dominated by circuit identity + compound + tire age + fuel. Per-driver style differences are ±0.1-0.5s effects that XGBoost cannot isolate from residual noise at this granularity. However, the other 10 features were designed for behavioural prediction tasks — Phase 4.5 rival pit-decision classification and Phase 5 PPO state representation — where cornering aggression, tire saving, and wet skill are expected to differentiate strategic decisions, not absolute lap times. Dropping them now would require re-running Phase 2.5 later.
**Alternatives considered:** Drop the 10 non-contributing features from the styled model (rejected: premature — their value is in Phase 4.5/5, not Phase 3; dropping would force re-joining at a later phase); impute NaN style values for rookies (rejected: XGBoost handles NaN natively; imputation would mask the genuine uncertainty for data-sparse drivers).

## 2026-04-27 — Use xgb_styled.pkl as production model for Sandbox/Optimizer
**Context:** Both baseline (xgb_baseline.pkl) and styled (xgb_styled.pkl) models are available. The 13.4% overall MAE improvement (1.53s → 1.32s) is concentrated in `overall_pace_rank` but is consistent across all three dry compounds and both sparse and stable circuits.
**Decision:** `xgb_styled.pkl` is the production model for all downstream phases (RaceEnv lap-time prediction, RL training, API inference).
**Why:** The improvement is real and verified via ablation. The styled model includes all 11 driver style features, making it the correct input interface for Phase 4.5 (rivals modelled with style vectors) and Phase 5 (RL state includes driver style). Using the baseline would require a model swap later; using styled is strictly better and forward-compatible.
**Alternatives considered:** Use baseline for simplicity (rejected: 13% worse MAE for no benefit; styled is already trained and saved).

## 2026-04-27 — Compound dynamics handled via explicit constants layer, not model retraining
**Context:** Phase 3.3 validation revealed MEDIUM and HARD produce identical XGBoost predictions (Compound_HARD feature gain ≈ 0.000036, below the model's split threshold). The real-world MEDIUM/HARD pace difference (~0.1s on fresh tyres) is below the model's inherent MAE (1.07s stable). Additionally, XGBoost lap-time predictions produce a near-linear degradation curve (≈ +0.027s/lap regardless of compound) — the accelerating cliff degradation seen in real F1 stints is not represented.
**Decision:** Create `compound_constants.py` with three dicts (COMPOUND_CLIFF_LAP, COMPOUND_CLIFF_PENALTY_S, COMPOUND_FRESH_TIRE_OFFSET_S) applied as a post-processing layer in `predict_degradation_curve()`. Controlled via `apply_compound_dynamics: bool = False` flag; disabled by default, enabled in Phase 4 RaceEnv.
**Why:** Attempting to learn MEDIUM/HARD differentiation by retraining with interaction features would fit noise — the signal is too small relative to residual error. Cliff degradation is a structural tyre physics effect (thermal cliff when compound leaves operating window) that is well-characterised by industry constants (Pirelli guidance, Heilmeier et al. 2020). A separate constants layer mirrors real F1 strategy software architecture where pace and tyre durability are separate models combined at the simulator layer. It also keeps the XGBoost model's predictions interpretable — the constants layer is auditable and adjustable independently.
**Alternatives considered:** Retrain with Compound × tire_age interaction features (rejected: no additional data, would just fit noise at 1.07s MAE resolution); per-stint degradation fitting from historical data (rejected: requires stint-level ground truth not in current dataset — deferred post-MVP); continuous compound degradation function replacing constants (rejected: more complex, same data scarcity problem).

## 2026-04-28 — Rival baseline uses historical median pit lap per (circuit, year)

**Decision:** `load_circuit_rival_profile` returns the raw historical median pit lap from top-10 training data. At circuits where the median is biased by VSC/SC pit cycling (e.g., Bahrain 2024: lap 12–13 of 57), this produces unrealistically aggressive rival pit timing.

**Rationale:** Acceptable for Phase 5 PPO training because the agent learns relative to whatever rival behavior the env produces — it will discover that matching or slightly undercutting the rival pit lap is optimal regardless of whether that lap reflects a VSC event. Flag for revisit if PPO learns to game early pit cycles (e.g., always pitting on lap 1).

## 2026-04-30 — Per-circuit overtaking difficulty deferred to Phase 4.5 GridRaceEnv

**Context:** `SandboxRaceEnv` uses cumulative race time to rank the ego against static 1-stop rivals. A driver who pits early (large lap time on pit lap) drops positions; one who pits late gains positions longer but faces a bigger time gap later. This is physically realistic at high-overtaking circuits (Monza, Bahrain, Silverstone) where lap-time advantage converts to actual overtakes. At low-overtaking circuits (Monaco, Singapore, Hungary) real-world behaviour is a procession — starting position ≈ finishing position regardless of pit timing.

**Decision:** Accept the cumulative-time position model in `SandboxRaceEnv` as-is. Defer per-circuit overtaking difficulty to Phase 4.5's `GridRaceEnv`.

**Why:** Adding overtaking resistance to `SandboxRaceEnv` would require a circuit-specific difficulty constant (essentially a parameter saying "position changes are X% harder at Monaco"), which is another hardcoded lookup with no ground-truth source. The effect on Phase 5 PPO training is acceptable: the agent will learn that aggressive Monaco strategies (early pit, late pit) are sub-optimal in the env even if not for the right physical reason. The ordering of valid strategies is still correct at circuits where overtaking is possible, which is the majority of the F1 calendar.

**Phase 4.5 fix:** `GridRaceEnv` will implement an overtaking probability model (minimum time-gap threshold × circuit overtaking factor) so position changes at Monaco are rightly rare.

## 2026-04-28 — Year-specific weather defaults instead of all-time averages

**Decision:** `SandboxRaceEnv.reset()` computes weather means from the exact (circuit, year) subset of training data and passes them to `predict_lap_time`, falling back to the circuit-wide mean only when fewer than 5 laps match.

**Rationale:** Keeps XGBoost predictions in-distribution for the trained year window. All-time circuit means conflate different car-generation eras (e.g., Singapore 2022 slow-car season with 87% humidity vs 74% in 2024), causing the model to interpolate toward a wrong regime and producing large prediction errors (up to 10s at Singapore).

## 2026-04-30 — pace_reward component (pace_delta × 0.05) added to combat reward sparsity

**Context:** Without a per-step pace signal, `step_reward` is 0 on every non-pit, non-position-change lap. At low-overtaking circuits (Monaco, Singapore) this produces 60–70 consecutive laps of 0 reward, making the credit-assignment problem intractable for PPO. SNR metric (terminal reward magnitude / per-step std) was undefined (0/0) at circuits with no position changes.

**Decision:** Add `pace_reward = (rival_lap_time − ego_lap_time) × 0.05` to every step.

**Why:** Provides a dense circuit-agnostic signal that rewards the agent for going faster than the rival baseline, regardless of whether a position change occurs. Scale of 0.05 was calibrated so cumulative pace signal across a 53-lap stint (±13s max) does not exceed terminal magnitude (±10), preventing pace from dominating positional incentives. SNR with pace_reward: 7.2× across test circuits (above the 3× threshold empirically needed for PPO convergence). Per-step std improved +24% (0.896 → 1.114), correctly differentiating wasteful strategies (4+ pit stops) from efficient ones even at non-overtaking circuits.

**Alternatives considered:** Bonus reward when ego is faster than rival this lap (rejected: binary signal, no gradient for how much faster); pit-count penalty (rejected: already captured by pit_cost=-0.05 per pit; doubling penalises pitting without improving density); no per-step signal (rejected: SNR fails at Monaco/Singapore, PPO cannot learn).

## 2026-04-30 — Reward weight calibration for SandboxRaceEnv

**Context:** Reward function has 6 components: position_delta, pit_cost, cliff_penalty, pace_reward, terminal_position, rule_bonus/penalty. Weights need to be calibrated so: (1) terminal position drives the objective, (2) intermediate signals shape behavior without dominating, (3) rule violation is strongly penalised.

**Decision:** `position_delta × 0.5 | pit_cost = −0.05 per pit | cliff_penalty = −0.10 per lap past cliff | pace_reward = pace_delta × 0.05 | terminal_position = −curr_position × 2.0 | rule_bonus = +10.0 (valid) / −100.0 (violation)`.

**Why:** Terminal position (max −20 to −2, assuming P2–P10 realistic) anchors the scale. Step position rewards (+0.5 per position gained) can sum to ±10 over a race if a driver gains/loses 10 places — comparable to but not exceeding the terminal. Pit cost (−0.05) discourages wasteful pitting over a 53-lap race by a cumulative −0.20 (4 pits), small enough not to over-penalise necessary stops. Cliff penalty (−0.10/lap past cliff) makes running a dead tyre cost ~−1.0 over 10 laps past cliff — enough to signal degradation without swamping position reward. Rule violation (−100) is 5× the worst-case terminal (−20) to make constraint satisfaction the hard objective.

**Alternatives considered:** Normalising all rewards to [−1, 1] per step (rejected: loses interpretability and relative weighting becomes architecture-dependent); larger terminal weight (rejected: at PPO horizon γ=0.99, terminal dominates anyway; don't need to double-count); symmetric rule bonus/penalty (rejected: recovering from a violation should not be rewarded equally with clean racing).

## 2026-05-01 — XGBClassifier + scale_pos_weight for behavior cloning (vs resampling)
**Context:** Rival pit-decision dataset has 3.28% positive rate (3,465 pit laps out of 105,715). Standard approaches include SMOTE oversampling, undersampling stay laps, or class-weight adjustment.
**Decision:** Use `scale_pos_weight = n_stay / n_pit = 29.4` natively in XGBClassifier. No resampling.
**Why:** XGBoost's internal class weighting adjusts split gain calculations to treat each pit observation as 29.4× more important than a stay observation during tree building. This preserves the true training distribution — the model sees the actual data, not a synthetic rebalanced sample — which produces better-calibrated raw probabilities and avoids the nearest-neighbour interpolation artifacts of SMOTE on tabular F1 data. Isotonic regression then calibrates the output probabilities on the val set.
**Alternatives considered:** SMOTE (rejected: interpolates between drivers' style vectors in ways that don't correspond to real drivers; pit decisions are race-context-specific, not smoothly interpolable); undersampling stay laps (rejected: discards 90K real laps with valid training signal for lap count, circuit, and compound features).

## 2026-05-01 — Isotonic regression for probability calibration (vs Platt scaling)
**Context:** After training XGBClassifier with scale_pos_weight=29.4, raw probabilities need calibration. sklearn 1.8 dropped `cv='prefit'` from `CalibratedClassifierCV`, requiring a custom implementation.
**Decision:** Manual isotonic regression: fit `IsotonicRegression(out_of_bounds='clip')` on val-set raw probabilities → val-set labels. Implemented as `_CalibratedPitModel` wrapper that combines the fitted XGBClassifier and the fitted `IsotonicRegression`.
**Why:** Isotonic regression is non-parametric — it doesn't assume a sigmoid shape, which is important for rare-event classifiers where the uncalibrated probability curve is often non-monotonic at the extremes. Platt scaling (logistic sigmoid fit) assumes the calibration curve is sigmoid-shaped, which fails for the 3% base rate we have here (raw probs cluster near 0, sigmoid fitting produces poor high-probability calibration). Fitting on the val set is acceptable: the val set is used for early stopping signal (not gradient updates), and calibration is a post-hoc isotonic mapping that doesn't introduce distributional assumptions.
**Alternatives considered:** Platt scaling (rejected: sigmoid assumption fails for 3% base rate); no calibration (rejected: XGBoost raw probs with scale_pos_weight are known to be overconfident at the high end); `CalibratedClassifierCV(cv=5)` (rejected: requires 5× refitting of XGBClassifier which is expensive and would lose early stopping context).

## 2026-05-01 — Calibrated pit probability clipped to [0.001, 0.95]
**Context:** After isotonic calibration, extreme-scenario probabilities (VER at tire_age=25 Bahrain, tire_age=35 on any compound past cliff) saturated to 1.0. The isotonic regressor maps to 1.0 at the high end of its training range.
**Decision:** Clip all outputs of `_CalibratedPitModel.predict_proba()` to [0.001, 0.95] before returning.
**Why:** In `GridRaceEnv`, rivals SAMPLE from the pit probability — they don't argmax. A probability of 1.0 means a rival will deterministically pit at that state every episode, which removes episode diversity for the PPO agent (Phase 5). If ZHO always pits on lap 25 at Bahrain, the PPO agent can hard-code "ZHO pits on lap 25" into its policy — this is exactly the predictable-robot behavior the stochastic sampling was designed to prevent. Capping at 0.95 means there is always a 5% chance the rival doesn't pit even in high-urgency states. AUC-ROC is unaffected (rank-order metric); all 4 sanity checks preserve correct directionality at clipped values.
**Alternatives considered:** Platt scaling for smoother probability surface (rejected: see isotonic regression decision above); no clipping, accept 1.0 as correct for past-cliff scenarios (rejected: directionally correct but eliminates PPO exploration signal); clip only for inference (rejected: inconsistency between training metrics and deployment).

## 2026-05-01 — Gap-to-rival features excluded from Phase 4.5.1 rival policy
**Context:** Real F1 pit strategy is heavily undercut-window-dependent — teams often pit in response to rivals' recent pit stops or threatening gap closures. Gap-to-rival features (gap_ahead, rival_ahead_tire_age, rival_ahead_tire) are natural inputs to a pit-decision classifier.
**Decision:** Exclude gap-to-rival features from Phase 4.5.1. These features are added in Phase 4.5.3 when `GridRaceEnv` exists and multi-car state can be computed.
**Why:** Phase 4.5.1 trains on historical lap data from `lap_features.parquet`, which does not contain inter-car gap information at inference time. Reconstructing per-lap gaps from historical timing data would require significant additional data engineering (ordering all cars per lap, computing deltas) with no clean source in the current pipeline. The Phase 4.5.1 model is adequate for stochastic simulation with AUC-ROC=0.777; the remaining lift from gap features is deferred to Phase 4.5.3 where the features will be computed in real-time within `GridRaceEnv`. AUC ceiling without gap features is estimated ~0.80.
**Alternatives considered:** Reconstruct historical gaps from lap order data (rejected: complex, laps have position but not gap-seconds; would require FastF1 raw timing data re-ingestion); estimate gap from position delta as proxy (rejected: noisy, doesn't distinguish a 0.3s gap from a 3s gap which is the key undercut signal).

## 2026-04-30 — Bahrain as primary validation circuit for Phase 4.5+
**Context:** Multi-agent grid env validation needs a test circuit that 
isolates strategy logic from circuit-specific noise.
**Decision:** Use Bahrain for Phase 4.5.2 GridRaceEnv validation.
**Why:** High tire degradation makes pit timing meaningful (vs Monaco 
where pit timing barely affects outcome). Realistic overtaking matches 
the multi-agent env's design intent. Clean weather avoids confounds. 
Plenty of training data.
**Alternatives considered:** Monza (low deg makes strategy decisions 
trivial), Monaco (no overtaking, env limitation), Spa (weather + long 
laps add noise).

## 2026-05-02 — Per-circuit OVERTAKING_DIFFICULTY constants for friction model
**Context:** `GridRaceEnv` Part 3 needs a mechanism to prevent the naive cumulative-time position sort from producing unrealistic on-track passes. In real F1, Monaco produces nearly zero on-track overtakes per lap; Monza and Bahrain produce several.
**Decision:** Create `pitiq.envs.grid_constants.OVERTAKING_DIFFICULTY` — a dict from circuit name to maximum positions a non-pitting car can gain per lap on-track. Easy circuits (Bahrain, Monza, Spa, Baku, COTA, Las Vegas, Saudi): 1 position/lap. Moderate (most permanent circuits): 0.5 (rounds to 0 via `int()`, so effectively no on-track gain). Hard (Monaco=0.1, Singapore/Miami/Hungary=0.3).
**Why:** Per-circuit overtaking frequency is well-characterised by F1 analyst consensus and historical passing statistics. A max-gain-per-lap clamp is the simplest model that captures the qualitative difference between a DRS highway (Monza) and a procession (Monaco) without requiring a full gap-physics simulation. Calibrated so that strategy (pit timing) is the primary driver of position changes at most circuits.
**Alternatives considered:** Continuous overtaking probability per lap (more realistic but requires a gap model not yet built); circuit overtaking factor as a probability multiplier applied to each position-gain attempt (deferred to Phase 4.5.3 when full gap features are added); using `CIRCUIT_OVERTAKING_FACTOR` (0–1 float already in `grid.py`) instead of a new dict (rejected: different semantics — factor scales a probability, difficulty caps an integer count; cleaner to have separate constants).

## 2026-05-02 — Pit-cycle position swaps EXEMPT from overtaking friction
**Context:** The overtaking friction model clamps on-track position gains. But a pitting car legitimately drops many positions as it cycles through the pit lane while rivals stay out — this is not an "on-track overtake," it is a strategic position swap driven by cumulative time differences.
**Decision:** In `_apply_overtaking_friction()`, skip the gain-clamping logic entirely for any car that pitted on the current lap (`car.driver in cars_that_pitted`). Pitting cars can gain or lose any number of positions freely.
**Why:** A car pitting from P1 to P5 because four rivals stay out is a foundational F1 race dynamic. Clamping this would prevent the undercut/overcut mechanic from working at all — a car that pits first can never recover positions once rivals pit. The distinction between "pit-cycle swap" and "on-track overtake" is clean in the data: `pitted_drivers` is computed before the friction loop, so exempt cars are known exactly.
**Alternatives considered:** Apply friction uniformly to all cars (rejected: breaks undercut/overcut mechanics); apply friction only when gaining positions into clean air (requires gap data not yet available); allow pitting cars to gain but not lose positions (rejected: a pitting car at the back of the queue should drop positions while stopped).

## 2026-05-02 — Force-pit override for rivals when laps_remaining < 8 and rule unsatisfied
**Context:** The `_rival_pit_decision()` method samples from the Phase 4.5.1 XGBClassifier probability. For some driver-compound-circuit combinations near the end of a race, the classifier returns a low probability even when the 2-compound rule has not been met. Without a fallback, some rivals would finish a race having used only one dry compound, causing a rule violation.
**Decision:** In `_rival_pit_decision()`, override the sampled decision to `True` (pit) when `not rival.has_used_2nd_compound and laps_remaining < 8`. Additionally, always return `False` when `laps_remaining <= 2` (pitting on the final 2 laps cannot recover time).
**Why:** The 2-compound rule is a hard FIA sporting regulation — all cars must comply or receive a post-race time penalty. The behavior-cloned policy was trained on historical data where teams always satisfy the rule, but probability clipping to 0.95 means there is a non-zero chance of non-compliance in the sim. The override acts as a regulatory hard constraint layered on top of the learned soft policy. The 8-lap threshold gives enough time for a pit stop and for the new tire to contribute before the checkered flag.
**Alternatives considered:** Remove probability clipping only for end-of-race laps (rejected: complicates the calibration logic for marginal gain); rely on the classifier alone (rejected: 5% non-pit probability at laps_remaining=5 means ~8% of 19 rivals could fail the rule per race — too high for a hard constraint); penalty in the reward function for rule violation instead of hard override (rejected: penalties work for the ego agent but not for rivals who have no reward signal).

## 2026-05-03 — 25-dim ego observation includes rival-aware features
**Context:** `GridRaceEnv` originally used a 13-dim ego-state observation identical to `SandboxRaceEnv`. F1 strategy is fundamentally relational — the value of a pit stop depends on the gap to rivals and their tire states, not just absolute ego state.
**Decision:** Expand to 25 dims by adding 12 rival-context features: gap/compound/tire_age/pace_rank/tire_saving for the car immediately ahead and behind, plus `undercut_window_open` and `defending_against_undercut` boolean flags.
**Why:** An RL agent with only ego-state obs cannot learn undercut/overcut timing — it has no information about whether rivals have older tires or are within striking distance. The 12 new features give the agent exactly the relational context that F1 strategy engineers use to evaluate pit windows. Using only the immediately adjacent rivals (P±1) keeps the obs compact while covering the strategically relevant cases: an undercut targets the car ahead, a defending pit covers the car behind.
**Alternatives considered:** Include all 19 rival states (full grid context) — rejected: 19×5 = 95 additional dims, most irrelevant for immediate strategy decisions; dramatically slows PPO training; the two adjacent cars cover >90% of strategic decisions. Gap features only (no style features for rivals) — rejected: tire_saving_coef and overall_pace_rank for rivals provide PPO with a prior on whether rivals will pit aggressively or conservatively, reducing sample complexity.

## 2026-05-03 — Pre-computed undercut_window_open and defending_against_undercut flags
**Context:** Raw observation includes gap_ahead, rival_ahead_tire_age, and ego tire_age. The undercut signal is a conjunction of these (gap < 1.5s AND rival older tires). PPO could learn this conjunction from raw features, but conjunctions are hard for neural networks to discover efficiently.
**Decision:** Pre-compute both flags in `_compute_rival_context()` using explicit thresholds: `undercut_window_open = 1.0 if (rival_ahead exists AND gap_ahead < 1.5s AND rival_ahead.tire_age > ego.tire_age) else 0.0`. Same logic for defending.
**Why:** Reduces PPO sample complexity by making common strategic situations explicit rather than requiring the agent to derive them from raw features. The 1.5s threshold matches the industry-standard DRS detection point used by F1 teams for undercut window assessment. Raw features (gap, tire ages) are still present in the obs — the agent can learn more nuanced policies using them while the flag provides a clean bootstrap signal. This is the same design principle used in AlphaGo's hand-crafted liberty count features alongside raw board state.
**Alternatives considered:** Raw features only, let PPO discover the conjunction (rejected: significantly more sample complexity for a well-known strategic threshold — adds no value vs encoding domain knowledge directly); probability-based flag (smooth function of gap and tire delta rather than binary) — rejected: binary is cleaner and the 1.5s threshold is a hard physical threshold (DRS range), not a soft one.

## 2026-05-03 — Sentinel scheme for P1/P20 edge positions (out-of-range values, not NaN)
**Context:** When ego is P1, there is no car ahead. When ego is P20, there is no car behind. The observation needs a representation for "no rival exists in this direction" that is safe to feed to a neural network.
**Decision:** Use fixed out-of-range-but-interpretable sentinel values: gap=30.0 (capped max is 30s), compound_index=0, tire_age=0, pace_rank=33.0 (beyond any real driver's rank in a 20-car grid), tire_saving_coef=0.5 (midpoint of the [0,1] range). Binary flags (`undercut_window_open`, `defending_against_undercut`) are 0.0 when no rival exists.
**Why:** NaN would cause `observation_space.contains()` checks to fail and could propagate through PyTorch/TF tensors in unexpected ways. Padding with zero would conflate "no rival" with "rival on lap 0 with SOFT compound at rank 0" — the zero pad is ambiguous. The chosen sentinels are unambiguous: gap=30.0 is beyond the physical maximum gap that matters for strategy (a 30s+ gap means the race is decided); rank=33 is beyond any real driver rank; these values are learnable signals that "nothing is here" rather than noise. The observation space bounds are set to accommodate the sentinel values, so no out-of-bounds violation occurs.
**Alternatives considered:** Separate binary flag `has_rival_ahead` / `has_rival_behind` (then zero-pad the rival features) — rejected: doubles the number of edge-case signals the agent must track; sentinel scheme achieves the same result with fewer dims. Masking in the neural network architecture (attention-style ignore) — rejected: adds architectural complexity; not needed given the limited grid size (20 cars).

## 2026-05-02 — Stochastic rival pit decisions (sample from probability, not argmax)
**Context:** Rival pit decisions in `GridRaceEnv._rival_pit_decision()` are made by drawing `self._rng.random() < pit_prob`. This means rivals sometimes don't pit even at high-probability states, and sometimes pit at low-probability states.
**Decision:** Sample stochastically from `pit_prob` rather than applying a deterministic threshold (e.g., `pit_prob >= 0.5`).
**Why:** Deterministic argmax would make all 19 rivals predictable robots — the PPO agent could memorise "rival X always pits on lap Y" and exploit this brittle pattern. Stochastic sampling means each episode is a different instance of the underlying distribution: rivals sometimes pit early, sometimes late, sometimes skip a window. This forces the PPO agent to learn a strategy that is robust to rival variation rather than over-fit to a fixed rival behavior. The Phase 4.5.1 model was specifically calibrated (isotonic regression + [0.001, 0.95] clipping) to produce well-calibrated probabilities suitable for stochastic sampling — not classification thresholding.
**Alternatives considered:** Argmax at 0.30 threshold (the DECISION_THRESHOLD in rival_policy.py): tried in Part 2's deterministic placeholder — produced all 19 rivals pitting on the same lap (lap 15) every episode; catastrophically non-diverse. Argmax at 0.50: lower simultaneous pit count but still deterministic per driver-state combination. Temperature scaling on probabilities (soften/sharpen the distribution): unnecessary given calibrated probs already span the full [0.001, 0.95] range.
## 2026-05-04 — Curriculum training: Stage 1 single-circuit before Stage 2 multi-circuit
**Context:** Phase 5.1 PPO training on `SandboxRaceEnv`. Training directly on 4 circuits × 5 drivers × 10 positions from step 0 risks slow convergence — the reward signal is noisy across diverse scenarios before the agent has learned basic strategy.
**Decision:** Stage 1 (0–300K): single fixed scenario (Bahrain 2024, VER, P1, SOFT). Stage 2 (300K–1M): randomised across 4 circuits × 5 drivers × P1–P10 per episode reset.
**Why:** A clean single-scenario signal lets the agent converge on core strategy (satisfy two-compound rule, time pit around tire cliff) before the curriculum adds diversity. Stage 1 converged to +7.46 eval reward by 100K steps; Stage 2 rollouts were hitting +6.31 across varied scenarios by 700K, confirming generalisation. The temporary reward drop at Stage 2 onset (−29 rollout reward) recovered within 80K steps.
**Alternatives considered:** Single stage training on all circuits from step 0 (risk: slow/unstable convergence on a noisy joint distribution); per-circuit separate models (rejected: defeats the purpose of generalisation; more complex at inference time).

## 2026-05-04 — 4 parallel envs (DummyVecEnv) for PPO rollout collection
**Context:** SB3 PPO supports vectorised environments for parallel rollout collection. More envs = faster data collection and more diverse experience per update.
**Decision:** `n_envs=4` with `DummyVecEnv` (single process, sequential stepping).
**Why:** Standard SB3 pattern for CPU-bound envs. With `n_steps=2048` per env, each PPO update uses 4 × 2048 = 8,192 transitions — a well-sized batch for the 13-dim obs space. DummyVecEnv (not SubprocVecEnv) was chosen because SandboxRaceEnv uses XGBoost inference which has a per-process OpenMP thread pool; SubprocVecEnv would fork 4 processes each initialising their own XGBoost thread pools, adding overhead and risking the libomp conflict that caused segfaults in this session.
**Alternatives considered:** `n_envs=1` (slower data collection, less diverse rollouts); `SubprocVecEnv` with `n_envs=4` (true parallelism but subprocess overhead + OpenMP fork risks on macOS Apple Silicon).

## 2026-05-06 — 3-stage curriculum for GridRaceEnv PPO training
**Context:** Phase 5.2 PPO training on `GridRaceEnv`. The 20-car grid with rival-aware 25-dim obs is significantly more complex than `SandboxRaceEnv`. Training on full diversity from step 0 risks slow or unstable convergence.
**Decision:** Stage 1 (0–200K): fixed Bahrain 2024 VER P1 with actual qualifying grid. Stage 2 (200K–600K): Bahrain only, ego from [VER, LEC, NOR, HAM, ZHO] at P1–P10. Stage 3 (600K–1.5M): all 4 circuits, 5 ego drivers, P1–P15 starts.
**Why:** Stage 1 fixed scenario gives the agent a clean signal to learn basic pit timing with real 20-car rivals. Stage 2 adds positional and driver diversity within a known circuit before adding circuit diversity in Stage 3. The Stage 1→2 transition caused the expected reward dip (−22.64 at 200K eval) but recovered within 100K steps. Stage 2→3 showed no regression, confirming Stage 2's generalization prepared the agent cleanly for multi-circuit training.
**Alternatives considered:** 2-stage curriculum matching Phase 5.1 (rejected: GridRaceEnv has an extra complexity dimension — 20 rivals vs 0 — that warrants an additional stage); full diversity from step 0 (rejected: Sandbox PPO took 300K steps to recover from immediate multi-circuit exposure; GridRaceEnv is harder).

## 2026-05-06 — ent_coef=0.02 for GridRaceEnv PPO (vs 0.01 for Sandbox)
**Context:** `SandboxRaceEnv` used `ent_coef=0.01`. `GridRaceEnv` has stochastic rivals — each episode produces a different rival pit sequence, adding observation variance that can cause premature policy collapse if entropy is too low.
**Decision:** `ent_coef=0.02` for `train_ppo_grid.py`.
**Why:** Higher entropy coefficient encourages the policy to maintain exploration longer, preventing it from converging prematurely to a strategy that over-fits to a specific rival pit sequence. With stochastic rivals, the optimal policy must be robust to rival variance — a higher entropy prior keeps the policy from hard-coding expected rival behavior. Entropy at convergence (`−0.093`) is higher than Phase 5.1 (`−0.05`), confirming the coefficient had the intended effect.
**Alternatives considered:** `ent_coef=0.01` (same as Sandbox — risk of premature collapse given rival stochasticity); `ent_coef=0.05` (too high — may prevent convergence entirely on the fixed Stage 1 scenario).

## 2026-05-06 — Grid PPO evaluated vs Sandbox PPO as rival-awareness baseline
**Context:** Phase 5.2 evaluation needs to quantify what rival-awareness (dims 13–24 in the 25-dim obs) contributes over a policy that has no rival information.
**Decision:** Load `ppo_sandbox_best.zip` and feed only `obs[:13]` (the 13 ego-state dims) to the Sandbox model when evaluating in `GridRaceEnv`. Compare rewards and mean finishing positions across two scenarios (VER P1 easy, ZHO P15 hard).
**Why:** The Sandbox PPO is the natural baseline — it was trained on the same circuits and drivers but with a 13-dim obs and no rivals. Any difference in GridRaceEnv performance isolates the value of rival-awareness. Using `obs[:13]` is valid because `GridRaceEnv` preserves the same 13-dim ego-state layout as `SandboxRaceEnv` in the first 13 observation dimensions.
**Results:** VER P1 (easy): Grid PPO +14.87 vs Sandbox PPO +14.23 — small advantage. ZHO P15 (hard): Sandbox PPO P7.3 vs Grid PPO P8.5 — Sandbox marginally better on this specific scenario. Key finding: learned policies (both Grid and Sandbox PPO) outperform the fixed heuristic by ~3 positions in the hard scenario (P7-8 vs P10.4), confirming adaptive strategies add real value regardless of rival-awareness. Rival-awareness benefit expected to differentiate more clearly in scenarios with explicit undercut windows (gap_ahead < 1.5s + rival on older tires) — ZHO P15 Bahrain had high rival stochasticity but not necessarily clean undercut windows from P15.

## 2026-05-06 — Batch XGBoost inference for GridRaceEnv step()
**Context:** First training attempt ran at 7 fps (1.5M steps would take ~60 hours). Root cause: `GridRaceEnv.step()` called `predict_lap_time()` 20 times and `predict_pit_probability()` 19 times per step, each constructing a 1-row DataFrame, running `pd.get_dummies`, and calling `model.predict()` individually.
**Decision:** Add `predict_lap_times_batch()` to `pitiq.ml.predict` and `predict_pit_probabilities_batch()` to `pitiq.ml.rival_policy`. Both build one N-row DataFrame per call and invoke `model.predict()` once. Update `GridRaceEnv.step()` to use both batch functions.
**Why:** The per-call overhead (DataFrame construction + `pd.get_dummies` for categorical features + XGBoost prediction setup) is roughly constant regardless of batch size. Running 20 individual calls repeated this overhead 20×. A single 20-row batch amortises all overhead across all cars. Result: 7 fps → 126 fps (17.6× speedup), reducing training time from ~60 hours to ~3.3 hours.
**Alternatives considered:** Pre-computing DMatrix once and updating per step (more complex, marginal additional gain); caching per-driver, per-circuit static features at `reset()` time (valid optimization but batch call already captures most of the gain); reducing total timesteps instead of optimising (rejected: 50K steps at 7 fps would still take 2 hours and produce undertrained policy).

## 2026-05-06 — Evaluation harness scenario selection (4 circuits covering 3 policy-quality axes)
**Context:** Phase 5.3 needs test scenarios that can differentiate policy quality. Bahrain VER P1 (the training eval scenario) is a ceiling-effect case — all learned policies reach P1. A useful eval set must include scenarios where rival-aware strategies outperform heuristics and where out-of-distribution generalization matters.
**Decision:** 4 scenarios chosen to span 3 axes: (1) Bahrain VER P1 — baseline ceiling check; (2) Bahrain ZHO P15 — mid-grid complexity and rival stochasticity; (3) Italian NOR P3 MEDIUM — undercut opportunity on a low-degradation circuit where timing precision matters; (4) Belgian HAM P6 MEDIUM — multi-car traffic and undercut/overcut windows.
**Why:** Italian P3 MEDIUM is the best differentiator for rival-awareness: the car ahead is on aging tires in laps 15–22, and the PPO agent should detect `gap_to_rival_ahead` + `rival_ahead_tire_age` to time a clean undercut. Belgian P6 puts HAM in mid-grid traffic at a circuit with multiple undercut windows (Spa's back straight is the primary opportunity). These two scenarios produced the clearest Grid PPO > Fixed margin in the final evaluation (+37% and +198% reward, respectively).
**Alternatives considered:** All-Bahrain evaluation (rejected: ceiling effect on P1, ZHO P15 is sandbox-degenerate — only 1 of 2 Bahrain scenarios is informative); including Monaco or Singapore (rejected: GridRaceEnv's overtaking friction makes these circuits near-deterministic, masking strategy quality); Monza P1 (NOR at P3 was chosen over P1 to include an overtaking challenge).

## 2026-05-06 — Fixed lap-18 heuristic as Grid baseline (not cliff-pit)
**Context:** Phase 5.1 Sandbox baseline used cliff-pit (pit at tire cliff) as the strongest non-PPO heuristic. Phase 5.3 Grid baseline needed a circuit-agnostic heuristic.
**Decision:** Fixed lap-18 pit for Grid Mode baselines.
**Why:** Cliff-pit depends on the current compound's cliff lap, which requires obs inspection. Fixed lap-18 is the simplest possible non-trivial heuristic — it satisfies the two-compound rule (always pits before lap 40 even at Belgian 44 laps), avoids cliff violations, and represents the strategy teams use when they have no telemetry. It also matches the lap-18 timing used in the Phase 5.2 baseline comparison, so results are comparable. Belgian HAM P6 result (+3.88 / P4.0 / 0% win) confirms fixed lap-18 is a weak Grid heuristic and Grid PPO's +70% win-rate margin is a meaningful gap.
**Alternatives considered:** Cliff-pit (requires obs decoding — more complex, harder to understand as a baseline); median-pit-lap from training data per circuit (too specific, removes the "naive heuristic" character of the baseline).

## 2026-05-06 — In-memory Parquet loading at startup via app.state
**Context:** FastAPI endpoints need access to `lap_features.parquet` (108K rows) and `driver_styles.parquet` (33 rows). The naive approach reads from disk on every request.
**Decision:** Load both Parquet files into `app.state` during the `@app.on_event("startup")` handler. All endpoints read from `app.state.lap_features` / `app.state.driver_styles` in memory.
**Why:** The combined data footprint is small (~50MB in memory). Per-request Parquet reads at 108K rows would add 30–100ms of I/O per call and require holding a file handle across concurrent requests. Loading once at startup reduces all data-dependent endpoints to pure in-memory pandas operations — measured at 1–12ms. The startup event is a standard FastAPI pattern for exactly this use case.
**Alternatives considered:** SQLite cache (rejected: adds a dependency and a schema migration for data that doesn't change between restarts); per-request Parquet read with an LRU cache (rejected: more complex, first-request latency spike, harder to reason about memory usage); Redis (rejected: overkill for a single-process dev server at this scale).

## 2026-05-06 — CORS origin locked to localhost:5173 (Vite dev server)
**Context:** Frontend runs on `http://localhost:5173` in development. FastAPI's CORS middleware must explicitly allow this origin or browser preflight requests will be rejected.
**Decision:** `allow_origins=["http://localhost:5173"]` in `CORSMiddleware`. Credentials and all methods/headers allowed for dev ergonomics.
**Why:** Locking to a single explicit origin (rather than `["*"]`) prevents accidental credential leakage if the API is accidentally exposed on a non-loopback interface during development. The Vite dev server always uses port 5173 by default.
**Alternatives considered:** `allow_origins=["*"]` (rejected: overly permissive, masks the production configuration requirement); environment-variable-driven origin list (deferred to Phase 10 deployment — premature for a dev-only backend).
**Follow-up:** Update to production frontend URL in Phase 10 (deployment). Add `ALLOWED_ORIGINS` env var support at that point.

## 2026-05-06 — Short-stint filter (< 5 laps) for winner_strategy reconstruction
**Context:** FastF1 occasionally records spurious Stint number changes of 1–4 laps around VSC periods, red flags, or pit lane drive-throughs. Without filtering, these appear as pit stops in the reconstructed strategy.
**Decision:** In `_reconstruct_strategy()`, compute stint lengths and skip any stint with fewer than 5 laps when building the strategy list.
**Why:** A genuine pit stop requires at least a lap in the pits + return to race position. Real racing stints are almost never shorter than 5 laps by design (a pit stop with < 5 laps of the new tire wastes more time than it gains). The 5-lap threshold was validated against 12 known artifact cases (e.g., 2021 Russian GP HAM, 2022 Monaco GP PER) where the filter correctly removed ghost stints; and against 2024 Bahrain VER where no stints are filtered (all 3 stints are 15/18/19 laps — genuinely a 2-stop race).
**Alternatives considered:** Filtering by compound change (rejected: VSC stints can keep the same compound, making this insufficient); using only the `PitInTime`/`PitOutTime` columns (rejected: these have frequent NaN in the cleaned dataset — lap_features cleans timing but doesn't guarantee pit columns are populated).

## 2026-05-04 — gamma=0.99 (high discount) for terminal-reward-dominated env
**Context:** `SandboxRaceEnv` terminal reward (`−position × 2.0 ± rule_bonus`) dominates the total episode return. A 57-lap Bahrain race means the terminal reward is 57 steps away from the agent's first pit decision around lap 18.
**Decision:** `gamma=0.99`.
**Why:** At gamma=0.99, a terminal reward at step 57 is discounted by 0.99^57 ≈ 0.566 — still more than half its face value. At gamma=0.95 (common default), 0.95^57 ≈ 0.054 — only 5% of the terminal reaches back to step 1, making credit assignment for early pit decisions extremely difficult. With the per-step `pace_reward` providing a dense intermediate signal (SNR=7.2×, validated in Phase 4.2), the combination of dense pace signal + high-gamma terminal propagation gives the agent enough gradient to learn that an early pit on lap 18 causes P1 at lap 57.
**Alternatives considered:** gamma=0.95 (standard default — rejected: too much discounting for a 57-step episode with dominant terminal reward); gamma=1.0 (no discounting — rejected: destabilises PPO value function training on long episodes).

## 2026-05-06 — ThreadPoolExecutor for sync env execution in async FastAPI
**Context:** SandboxRaceEnv and PPO inference are synchronous (Gymnasium + NumPy + XGBoost). FastAPI endpoints are async. Blocking the event loop with a 57-step env rollout (~200ms) would stall all other requests.
**Decision:** `ThreadPoolExecutor(max_workers=4)` stored in `app.state.executor`, called via `await loop.run_in_executor(app.state.executor, lambda: ...)`.
**Why:** Standard pattern for CPU-bound work in async FastAPI. Thread-based (not process-based) so closures/lambdas work without pickling. max_workers=4 matches a typical M-series Mac core count without over-subscribing given XGBoost also uses threads internally.
**Alternatives considered:** Separate worker process via `ProcessPoolExecutor` — rejected: requires pickling, complicates model sharing, more complex lifecycle management.

## 2026-05-06 — PPO inference at /recommend uses deterministic=True
**Context:** PPO Sandbox produces stochastic actions by default (samples from learned policy distribution). For a recommendation endpoint, the user expects a single consistent recommendation, not a random sample.
**Decision:** `ppo_model.predict(obs, deterministic=True)` — takes the argmax of the action distribution rather than sampling.
**Why:** API users want a reproducible recommendation. Stochastic sampling makes sense during training (exploration) but not for a served endpoint. The deterministic policy is also the stronger one at evaluation time (as confirmed by Phase 5.3 evaluation).

## 2026-05-07 — Historical-validation endpoint returns single-seed result; claimed 70% accuracy is a 5-seed average
**Context:** Phase 4.5.2 validation reported "70% of drivers within ±3 positions" for the GridRaceEnv against 2024 Bahrain actual results. That figure was derived by averaging across 5 seeds (42, 123, 456, 789, 999). The `/api/optimizer/historical-validation` endpoint runs one simulation per request with a single stochastic rival policy seed.
**Decision:** Accept single-seed results from the endpoint. Document that the claimed 70% accuracy figure (from RESULTS.md and Phase 4.5.2 notes) is a 5-seed mean, not a per-call guarantee. A single call produces ~55–70% within ±3 depending on which seed the RNG happens to draw.
**Why:** Running 5 seeds per API call would multiply response time by 5× (from ~450ms to ~2.2s for Bahrain), which is unacceptable for a real-time endpoint. The per-call variance is an honest reflection of the model's inherent stochasticity, not a bug. Frontend should present historical-validation results as "one simulated race" not "the simulator's average accuracy."
**Alternatives considered:** Multiple-seed averaging per call (rejected: 5× latency penalty); seeding the RNG deterministically per (year, circuit) pair (rejected: removes stochasticity that is a feature, not a bug — same seed would always produce the same outlier result).

## 2026-05-07 — strategy_rationale generated via template function, not LLM
**Context:** `/api/optimizer/recommend` needs a human-readable explanation of the recommended strategy that references specific rival context (rival driver name, tire age, gap) and driver characteristics (tire saving coefficient).
**Decision:** `_generate_rationale()` is a deterministic template function that formats a fixed set of sentences from simulation trace data. No LLM involved.
**Why:** The rationale must be fast (called synchronously in the endpoint handler after the simulation finishes), reproducible (same input → same output), and specific (references actual rival name and tire age from the trace, not generic F1 text). A template function satisfies all three. LLM calls would add latency (~500ms–2s), non-determinism, and an external API dependency — all unacceptable for a real-time endpoint that already runs a 57-lap simulation. The specificity of the rationale ("Rival ahead (SAI) on aging tires, age 26") is more useful to users than generic LLM-generated strategy prose.
**Alternatives considered:** LLM-generated rationale via Anthropic API (deferred post-MVP — could be added as a premium feature without changing the endpoint contract); fixed boilerplate per circuit (rejected: doesn't reference actual rival context from the simulation trace).

## 2026-05-07 — Undercut window detection: gap < 1.5s AND rival_ahead tire_age > 20 AND ego not pitting
**Context:** `/api/optimizer/simulate` and `/api/optimizer/recommend` both return `undercut_windows_identified` — laps where the ego driver was in a position to execute an undercut but didn't (or could have).
**Decision:** `_check_undercut_window()` fires when: (1) `gap_to_rival_ahead < 1.5s` (DRS detection zone threshold), (2) `rival_ahead.tire_age > 20` (rival tires old enough to be meaningfully slower on next stint), (3) `action == 0` (ego is not already pitting on this lap). Check is run pre-step, on the state at the start of each lap.
**Why:** The 1.5s threshold is the FIA DRS detection point — the industry-standard marker for "within striking distance." Tire_age > 20 ensures the undercut is credible: a car on lap-21+ tires is meaningfully slower per lap on most compounds, making the position swap feasible after fresh-tire pace advantage. Requiring `action == 0` means the window is identified as a "missed opportunity" when ego didn't pit — if ego is already pitting (action != 0), the undercut is being executed, not missed. Validated: correctly empty for VER P1 Bahrain (no rival ahead throughout), fires 8 times for ZHO P15 Bahrain against SAI (age 26–34, gap 0.22–1.34s) as expected.
**Alternatives considered:** Stricter tire_age threshold (> 30) — rejects too many genuine windows; broader gap threshold (< 2.5s) — fires on laps where undercut is not credible; post-step detection (after rival has pitted) — too late to capture the decision point.

## 2026-05-07 — Industrial/F1-broadcast aesthetic: Barlow Condensed 900 + JetBrains Mono + E8002D + zero border-radius
**Context:** Phase 7.1 established the visual design language for the entire frontend.
**Decision:** All display text (headlines, labels, mode names) uses Barlow Condensed weight 900. All data/numbers (lap times, positions, tire ages, stat values) use JetBrains Mono. Primary accent is #E8002D (McLaren/Ferrari red — also the SOFT tire color). `--radius: 0px` — no rounded corners anywhere in the UI.
**Why:** McLaren timing tower aesthetic — sharp rectangles, monospace data readouts, high-contrast red on black. Rounded corners signal "consumer app." Sharp corners signal "precision instrument." The audience for PitIQ (engineers, strategy teams, F1 fans who care about data) expect the latter. Barlow Condensed at 900 matches the weight and condensed width of F1 broadcast supers and sector time displays. JetBrains Mono is purpose-built for data readability at small sizes.
**How to apply:** Every new component and page should reference `var(--font-display)`, `var(--font-mono)`, `var(--font-body)` rather than hardcoding font-family. Border-radius must remain 0 — no Tailwind `rounded-*` classes, no `border-radius` inline styles.

## 2026-05-07 — Canonical F1 tire compound colors
**Context:** `TireBadge` component and `LapTimeline` ReferenceLine markers need compound-to-color mapping.
**Decision:** SOFT=#E8002D, MEDIUM=#FFF200, HARD=#FFFFFF, INTERMEDIATE=#39B54A, WET=#0067FF. Defined in `tokens.css` as `--tire-soft/medium/hard/intermediate/wet` and referenced in component maps.
**Why:** These are the FIA/F1 broadcast-standard colors — instantly recognizable to any F1 viewer. Deviating would create confusion. White (HARD) requires special treatment in tooltip/badge text (use black label text).
**How to apply:** Always use `var(--tire-{compound})` for compound colors. Never use other colors for tire compounds. In SVG/canvas contexts where CSS vars may not resolve, use the hex equivalents from this decision.

## 2026-05-08 — Rival position interpolation strategy for Grid Position Tracker
**Context:** GridRaceEnv returns per-lap position data only for the ego driver. Rival predictions contain only `starting_position`, `final_position`, and `pit_history` (lap + compound, no positions).
**Decision:** Interpolate rival positions piece-wise linearly: start at `starting_position` at lap 1, add a +4 position dip at each pit stop lap (linear blend from base trajectory), end at `final_position` at lap N.
**Why:** GridRaceEnv's `RivalPrediction` was designed for strategy analysis (pit timing, tire choice), not per-lap telemetry. Adding per-lap position tracking to all 19 rivals would quadruple the response payload and require GridRaceEnv architectural changes. The interpolated trajectory is visually convincing and conveys the strategic narrative (pit drop → recovery → final finish) without being exact.
**How to apply:** If per-lap rival accuracy becomes important (e.g. for traffic analysis), add `rival_lap_by_lap` to `GridSimulateResponse` and update `RivalPrediction` schema. Until then, use the linear interpolation approach in `interpolateRivalPosition()`.

## 2026-05-09 — DriverStylePanel: normDrivers (33) vs allDrivers (season ~20) split
**Context:** `DriverStylePanel` needs two different driver lists: one for the comparison dropdown (season-filtered, ~20 drivers) and one for min/max normalization (full roster, 33 drivers). Initial implementation used a single `allDrivers` prop for both, sourced from `seasonDrivers[year]`.
**Decision:** Add a `normDrivers: DriverInfo[]` prop sourced from `store.drivers` (33 drivers, loaded globally at app mount). Use `normDrivers` for all `norm()` / `allSV()` calls; keep `allDrivers` for the comparison dropdown only. Fall back to `allDrivers` if `normDrivers` is empty (e.g., before the global fetch completes).
**Why:** Normalizing against ~20 season drivers collapses midfield drivers to ~0.5 on every axis because they're all clustered in the middle of that narrow range. Normalizing against the full 33-driver VER→MAZ spread gives correct proportional placement: VER→1.0 on Pace, MAZ/backmarkers→0.0, midfield→0.4–0.6.
**How to apply:** Always source `normDrivers` from `store.drivers` (the globally-loaded full driver list). Never use `seasonDrivers[year]` for normalization.

## 2026-05-09 — Driver style normalisation: min/max per active season roster (not global)
**Context:** `DriverStylePanel` radar and metric bars need to normalise raw style values (e.g. `overall_pace_rank` ranges 1–33 globally, but a given season may only have 20 drivers with ranks 1–28) to a [0, 1] scale for display.
**Decision:** Compute min/max from the currently loaded `allDrivers` array (the season-filtered driver list passed as a prop), not from any global constant or all-time dataset.
**Why:** Global min/max would compress most values into a narrow band whenever the selected season has fewer or different drivers than the full 33-driver set. Season-scoped normalisation fills the full 0–1 range on every radar, making comparisons maximally legible. Since `allDrivers` is already the season-filtered set used everywhere else in the page, this is also the consistent reference frame.
**Alternatives considered:** Global hard-coded min/max per metric (rejected: brittle to new seasons adding drivers beyond current range); z-score normalisation (rejected: [0,1] range is required for Recharts `RadarChart` domain).

## 2026-05-09 — Panel close-outside: document mousedown listener (not transparent backdrop)
**Context:** `DriverStylePanel` needs to close when the user clicks outside it. The Sandbox and Optimizer pages have form controls (dropdowns, buttons) in the area behind the panel.
**Decision:** Attach a `document.addEventListener('mousedown', handler)` that compares the event target against `panelRef.current`. mousedown closes the panel; the original click event fires normally on whatever element was behind the panel.
**Why:** A transparent full-screen backdrop div intercepts the pointer event, meaning a click intended for the driver dropdown behind the panel would close the panel but not open the dropdown — the user must click twice. The mousedown-listener pattern lets the click event propagate normally to the underlying element: mousedown closes the panel on pointer-down, then the browser's natural click (mousedown → mouseup → click) fires on the original target. Users can immediately interact with the form after dismissing the panel in one click.
**Alternatives considered:** Transparent backdrop `div` (rejected: double-click UX issue described above); click listener on document (same timing issue — click fires after mouseup, panel is gone but backdrop may still intercept).

## 2026-05-08 — Undercut window gap threshold and UI labeling
**Context:** Backend detects undercut windows where gap to rival ahead is < 1.5s and rival tire age is high. Some flagged windows have gaps < 0.5s which are better described as direct battles than undercut opportunities.
**Decision:** Display gap < 0.5s as "TIGHT BATTLE" (orange #FF8C00) and gap 0.5–1.5s as "UNDERCUT" (yellow #FFF200). Threshold 0.5s chosen because below this the car is effectively in DRS range — pitting to undercut a car you're already about to pass on track is rarely optimal.
**How to apply:** Classification is purely frontend (`UndercutPanel`). If backend changes the 1.5s threshold, update the UI label breakpoint to match. The 0.5s TIGHT BATTLE boundary is a display heuristic, not a strategy model parameter.
