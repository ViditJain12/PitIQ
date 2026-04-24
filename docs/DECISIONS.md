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

## 2026-XX-XX — Parquet over SQLite for data storage
**Context:** Need to store ~120K rows of lap data + telemetry across 5 seasons.
**Decision:** Parquet files in `data/processed/`.
**Why:** Faster columnar reads for ML pipelines, schema-on-read, no DB server to manage. SQLite would add overhead for a workload that's effectively read-only after ingest.
**Alternatives considered:** SQLite (rejected: unnecessary for analytical workload), DuckDB (good option, can revisit if querying becomes complex).

## 2026-XX-XX — Split train/test BY RACE not random
**Context:** ML pipeline needs train/val/test splits.
**Decision:** Split by race weekend, not random row sampling.
**Why:** Random splitting causes data leakage — model sees laps from the same race in both train and test, inflating metrics. Splitting by race forces the model to generalize to unseen race conditions.
**Alternatives considered:** Random 80/10/10 (rejected: leakage), split by season (acceptable but reduces test diversity).

## 2026-XX-XX — Compute driver style features once, treat as static features
**Context:** Driver styles evolve over time, but recomputing dynamically is expensive.
**Decision:** Compute style vectors once across all 5 seasons, treat as static features per driver.
**Why:** Driver styles are relatively stable over a multi-season window. Dynamic recomputation adds complexity without proportional accuracy gain.
**Alternatives considered:** Per-season style vectors (revisit if accuracy is poor on early-career drivers).
