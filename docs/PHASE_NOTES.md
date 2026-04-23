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
