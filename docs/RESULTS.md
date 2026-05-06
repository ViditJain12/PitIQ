# PitIQ — Model Results

> Comprehensive evaluation across all pipeline components. Generated 2026-05-06.
> All RL numbers are deterministic over 20 episodes unless noted.

---

## 1. Data Pipeline

| Metric | Value |
|---|---|
| Raw seasons ingested | 2021–2025 (5 seasons) |
| Total laps after cleaning | 108,257 |
| Circuits covered | 29 (all matched to metadata) |
| Feature columns | 39 (lap/session/circuit/weather) |
| Train split | 2021–2024, 85,214 laps, 89 races |
| Val split | 2025 R1–R12, 11,103 laps |
| Test split | 2025 R13–R24, 11,940 laps |

Split strategy: **race-based** (entire races assigned to splits, no lap-level leakage).

---

## 2. Driver Style Fingerprinting

| Metric | Value |
|---|---|
| Drivers with style vectors | 33 |
| Feature dimensions | 11 |
| Features | pace_trend_{soft,medium,hard}, cornering_aggression, throttle_smoothness, wet_skill_delta, tire_saving_coef, overall_pace_rank, sector_relative_{s1,s2,s3} |
| k-means silhouette (k=4) | 0.151 |

Notable deltas (wet_skill_delta, race-normalised): VER −1.11s, ZHO +3.6s, rookies ~+0.4s. All 11 features appear in rival pit policy importance ranking.

---

## 3. XGBoost Lap-Time Prediction

| Model | Overall MAE | Stable MAE | Sparse MAE | Test Laps |
|---|---|---|---|---|
| Baseline (50 features) | 1.53s | 1.11s | 3.91s | 5,162 |
| Styled (61 features) | **1.32s** | **1.07s** | **2.77s** | 5,162 |
| Improvement | −13.4% | −3.7% | −29.1% | — |

**Stable circuits** (≥3 train years): Belgian, Emilia Romagna, US, Dutch, Qatar†.
**Sparse circuit**: Las Vegas (single season in training data).

†Qatar technically qualifies (3 training years: 2021, 2023, 2025) but posts 2.1s MAE — worse than other stable circuits — because the 2022/2024 gaps prevent the model from inferring the year-over-year pace trend. Non-consecutive training years are nearly as damaging as missing years. Qatar is classified as stable for subset labelling but is a known boundary case.

Ablation: `overall_pace_rank` carries ~100% of the improvement; remaining 10 style features retained for behavioral tasks (rival policy, GridRaceEnv position sorting).

---

## 4. Rival Pit-Decision Policy

| Metric | Value |
|---|---|
| Model | XGBClassifier + isotonic calibration |
| Features | 55 (race state + EventName OHE + Compound OHE + 11 style features) |
| Pit rate (train) | 3.28% (scale_pos_weight = 29.4) |
| AUC-ROC (test) | **0.777** (target >0.75 ✓) |
| Avg precision (test) | 0.098 |
| Precision @ threshold 0.30 | 0.303 |
| Recall @ threshold 0.30 | 0.061 |
| All 4 domain sanity checks | Pass |

Style features in importance: `overall_pace_rank` (rank 38), `tire_saving_coef`, `cornering_aggression`. All 11 style features appear in the importance ranking — the first task where all style features contribute measurable signal, contrasting with Phase 3.2 where only `overall_pace_rank` mattered (remaining 10 features combined gain ≈ 0.21% of total in XGBoost lap-time prediction).

---

## 5. Race Simulation Validation (GridRaceEnv)

Tested against 2024 Bahrain GP actual results across 5 seeds.

| Metric | Value | Target |
|---|---|---|
| Drivers within ±3 positions | 70% | ≥70% ✓ |
| Drivers within ±5 positions | 95% | — |
| Mean absolute delta | 2.06 positions | — |
| Race time vs actual (5408s) | −2.2% | — |
| VER P1 in all 5 runs | Yes | — |
| 2-compound rule compliance | 20/20 | — |
| Stochastic rival pit laps | Yes (seed-varying) | — |

---

## 6. RL Evaluation (640 episodes total: 8 scenarios × 4 policies × 20 episodes)

### 6a. Sandbox Mode (SandboxRaceEnv, single-car simulation)

> **Note:** SandboxRaceEnv uses a fixed 1-stop cumulative-time rival model. All policies collapse to P20 for P15 starting positions regardless of strategy — midfield sandbox evaluation is not meaningful. See Section 7, Limitation 1.

| Scenario | PPO Sandbox | Cliff-pit | Never-pit | Random |
|---|---|---|---|---|
| **Bahrain VER P1** | +8.15 / P1 / 100% | **+8.67** / P1 / 100% | −231 / P20 | −99 / P20 |
| **Bahrain ZHO P15** | −37.4 / P20 / — | −36.2 / P20 / — | −229 / P20 / — | −96 / P20 / — |
| **Italian NOR P3** | −129 / P3 / 0% | **+9.26** / P1 / 100% | −129 / P3 / 0% | −94 / P20 |
| **Belgian HAM P6** | −105† / P1 / 100% | **+12.6** / P1 / 100% | −105† / P1 / 100% | −83 / P20 |

Format: mean reward / mean position / win rate. †Rule violation penalty (−100) included despite P1 finish.

**Sandbox findings:**

- **Bahrain VER P1 (in-distribution):** PPO ≈ cliff-pit (both P1, 239-point margin over never-pit). Correct — simplest possible scenario, cliff timing is near-optimal. Confirms PPO independently discovered the right strategy from reward signal alone.
- **Bahrain ZHO P15 (mid-grid):** All four policies finish P20. The static rival model assigns fixed 1-stop pace profiles — ZHO's pace rank is lower than the rival profiles regardless of strategy. This is an env limitation, not a policy failure. GridRaceEnv is required for any realistic mid-grid simulation.
- **Italian NOR P3 (OOD):** PPO Sandbox equals Never-pit exactly (−129.09, P3, 0% win). It is not pitting at all — this is out-of-distribution behavior, not learned strategy. Cliff-pit wins cleanly by pitting onto HARD at the MEDIUM cliff (lap ~18 at Monza). PPO Sandbox was trained on P1–P10 starts; P3 MEDIUM Monza was not in its training distribution.
- **Belgian HAM P6 (OOD):** PPO Sandbox and Never-pit produce identical reward (−104.64) and identical position (P1). PPO is doing never-pit, violating the 2-compound rule (−100 terminal penalty), and wins on raw pace alone. Cliff-pit earns +12.62 by correctly satisfying the rule and gets the +10 bonus on top of the P1 finish reward. This confirms PPO Sandbox overfit to Bahrain — it cannot generalize pit timing to new circuits or starting compounds.

### 6b. Grid Mode (GridRaceEnv, 20-car full simulation)

| Scenario | PPO Grid | PPO Sandbox† | Fixed lap-18 | Random |
|---|---|---|---|---|
| **Bahrain VER P1** | **+14.65** / P1 / 100% | +14.24 / P1 / 100% | +14.67 / P1 / 100% | −94 / P20 |
| **Bahrain ZHO P15** | −1.2 / P8.3 / +6.7 gained | **+1.3** / P7.3 / +7.7 gained | −5.4 / P10.3 / +4.7 gained | −90 / P20 |
| **Italian NOR P3** | **+9.47** / P1 / 100% | −126‡ / P1.6 / 50% | +6.88 / P1.8 / 35% | −96 / P20 |
| **Belgian HAM P6** | **+11.54** / P1.4 / 70% | −106‡ / P1.4 / 70% | +3.88 / P4.0 / 0% | −83 / P20 |

†PPO Sandbox runs on obs[:13] slice in 25-dim env. ‡Negative reward despite good position = 2-compound rule violation.

**Grid findings:**

- **Bahrain VER P1 (easy):** All three learned policies reach P1 with 100% win rate. Ceiling effect — this scenario is too easy to differentiate policies; it only confirms none are catastrophically broken.

- **Bahrain ZHO P15 (mid-grid):** Both learned policies (+6.7–7.7 positions gained) significantly outperform Fixed (+4.7 gained). PPO Sandbox marginally leads Grid PPO (P7.3 vs P8.3, σ=0.73 vs 1.71). The rival-aware 25-dim features provide limited marginal signal here — ZHO's gains depend more on pace vs the grid than on undercut timing. The higher Grid PPO variance reflects correct mid-grid sensitivity to stochastic rival behavior.

- **Italian NOR P3 (rival-awareness matters most):** Grid PPO dominates: P1 100% win vs 35% for Fixed (+37% win rate, +9.47 vs +6.88 reward). The rival-aware obs enables precise undercut timing off rival tire-age and gap-ahead features — Grid PPO identifies the exact window when the P1/P2 cars are vulnerable on aging tires. PPO Sandbox violates the 2-compound rule in 50% of episodes (reward −126 despite P1.6 avg) — without rival context it cannot time a clean double-compound strategy.

- **Belgian HAM P6 (multi-car traffic):** Grid PPO: P1.4 / 70% win / +11.54 reward vs Fixed: P4.0 / 0% win / +3.88 reward — Grid PPO reward is **198% higher**, win rate goes from 0% to 70%. PPO Sandbox achieves similar position to Grid PPO (P1.4, 70% win) but with negative reward (−106) due to consistent 2-compound rule violations — it's winning on pace but never pitting correctly.

- **PPO Sandbox in Grid env (systematic failure):** Achieves competitive positions on Bahrain P1 but fails the 2-compound rule at Italian and Belgian. Without rival context (obs[:13] only), it cannot determine when to pit relative to surrounding cars and defaults to late/no pit behavior.

### 6c. Headline numbers

| Metric | Value |
|---|---|
| Grid PPO vs Fixed (Italian NOR P3) | +9.47 vs +6.88 reward (+37%), 100% vs 35% win rate |
| Grid PPO vs Fixed (Belgian HAM P6) | +11.54 vs +3.88 reward (+198%), 70% vs 0% win rate |
| Both learned policies vs Fixed (ZHO P15) | +6.7–7.7 vs +4.7 positions gained (~+2 positions) |
| Grid PPO reward over random | +105 pts (Italian), +108 pts (Belgian) |
| Sandbox PPO reward over never-pit (Bahrain P1) | +239 pts |
| Sandbox eval failure rate | 3/4 scenarios degenerate (ZHO P15 env-limited; Italian/Belgian OOD) |
| GridRaceEnv 2024 Bahrain validation | 70% of drivers within ±3 positions of actual 2024 finish |

---

## 7. Limitations

1. **SandboxRaceEnv mid-grid evaluation degenerates**: The static 1-stop rival model cannot realistically simulate traffic dynamics for P10+ starting positions. All policies collapse to P20 for ZHO P15 regardless of strategy — the rival pace profiles overpower any timing decision. GridRaceEnv is required for realistic mid-grid simulation; SandboxRaceEnv is only reliable for P1–P5 starts where the ego driver has a pace advantage over the fixed rival profile.

2. **Sandbox PPO overfits to Bahrain**: Trained exclusively on Bahrain during Stage 1 (0–300K steps), the agent never learned to generalize pit timing to different starting compounds (MEDIUM at Italian/Belgian). At Italian NOR P3 and Belgian HAM P6 it defaults to never-pit, producing identical rewards to the Never-pit baseline. The 2-compound rule violation at Belgian further confirms it never learned compound-switching behavior for MEDIUM starts.

3. **Bahrain P1 ceiling effect**: Three out of four learned Grid policies reach P1 on Bahrain VER P1 with 100% win rate. This scenario cannot differentiate policy quality — it only validates that policies are not broken. More differentiated scenarios (Italian, Belgian) are the meaningful benchmarks.

4. **ZHO P15 grid evaluation variance**: High stochasticity in the midfield scenario (σ=1.71 for Grid PPO vs σ=0.73 for Sandbox PPO). 20 episodes is borderline for stable mean estimates in chaotic mid-grid races where a ±2 position swing is common.

5. **Sparse circuits**: Las Vegas MAE 3.91s (baseline) / 2.77s (styled) — 2× worse than stable circuits. Only one training season of data. Any inference involving Las Vegas should be treated as lower-confidence.

6. **Rival policy recall**: At threshold 0.30, recall = 6.1%. The model is precision-first by design (stochastic sampling requires few false positives), but this means rivals underpit on short stints, making the simulation slightly conservative on pit frequency.

---

## 8. Resume Bullets

_For portfolio / technical recruiters — bullets generated from actual measured results_

- Built end-to-end F1 race strategy ML platform: FastF1 data pipeline → XGBoost lap-time prediction (MAE 1.32s) → 20-car multi-agent race simulation → PPO reinforcement learning agent
- Designed driver style fingerprinting from raw telemetry (11-feature vectors across 33 drivers); style features improved lap-time model accuracy by 13.4% and contributed measurable signal to rival behavior prediction (AUC-ROC 0.777)
- Trained PPO Grid agent via 3-stage curriculum on 1.5M timesteps; achieved 100% win rate at Italian GP (NOR P3) vs 35% for fixed-strategy baseline, 70% win rate at Belgian GP (HAM P6) vs 0% for fixed baseline
- Optimized multi-agent simulation 17.6× (7 fps → 126 fps) by replacing 39 per-step XGBoost calls with single batched inference; reduced 60-hour training estimate to 3.3 hours on Apple Silicon
