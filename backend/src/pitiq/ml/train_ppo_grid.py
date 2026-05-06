"""Phase 5.2 — Train PPO agent on GridRaceEnv with rival-aware 25-dim observation.

3-stage curriculum:
  Stage 1 (0–200K):    Fixed scenario — Bahrain, VER P1, fixed 2024 qualifying grid.
  Stage 2 (200K–600K): Bahrain only, ego from [VER,LEC,NOR,HAM,ZHO], P1-P10 start.
  Stage 3 (600K–1.5M): All 4 circuits, ego driver P1–P15, full generalisation.

CLI:  python -m pitiq.ml.train_ppo_grid [--timesteps N]
"""

from __future__ import annotations

import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import logging
import random
import time
from pathlib import Path
from typing import Any

import gymnasium as gym
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor

from pitiq.envs.grid import GridRaceEnv

logger = logging.getLogger(__name__)

_REPO_ROOT   = Path(__file__).parents[4]
_MODELS_DIR  = _REPO_ROOT / "models"
_FIGURES_DIR = _MODELS_DIR / "figures"
_LOGS_DIR    = _MODELS_DIR / "logs" / "grid"
_TB_DIR      = _MODELS_DIR / "tensorboard" / "grid"

# ── 2024 qualifying grids (P1 → P20) ──────────────────────────────────────────

_BAHRAIN_GRID = [
    "VER", "LEC", "RUS", "SAI", "PER",
    "ALO", "NOR", "PIA", "HAM", "TSU",
    "STR", "MAG", "OCO", "GAS", "ALB",
    "BOT", "HUL", "ZHO", "SAR", "RIC",
]

_MONZA_GRID = [
    "LEC", "PIA", "NOR", "RUS", "VER",
    "SAI", "HAM", "ALO", "TSU", "STR",
    "PER", "MAG", "OCO", "GAS", "ALB",
    "BOT", "HUL", "ZHO", "SAR", "RIC",
]

_SPA_GRID = [
    "RUS", "NOR", "LEC", "SAI", "HAM",
    "PIA", "ALO", "TSU", "STR", "PER",
    "MAG", "OCO", "GAS", "ALB", "BOT",
    "HUL", "ZHO", "SAR", "RIC", "VER",
]

_ABU_DHABI_GRID = [
    "NOR", "PIA", "SAI", "LEC", "RUS",
    "VER", "ALO", "HAM", "TSU", "STR",
    "MAG", "OCO", "GAS", "ALB", "BOT",
    "HUL", "ZHO", "SAR", "RIC", "PER",
]

# Training circuits: full config per-circuit including year-specific starting grid.
_TRAIN_CIRCUITS = [
    {
        "circuit":           "Bahrain Grand Prix",
        "total_laps":        57,
        "starting_compound": "SOFT",
        "year":              2024,
        "base_grid":         _BAHRAIN_GRID,
    },
    {
        "circuit":           "Italian Grand Prix",
        "total_laps":        53,
        "starting_compound": "MEDIUM",
        "year":              2024,
        "base_grid":         _MONZA_GRID,
    },
    {
        "circuit":           "Belgian Grand Prix",
        "total_laps":        44,
        "starting_compound": "MEDIUM",
        "year":              2024,
        "base_grid":         _SPA_GRID,
    },
    {
        "circuit":           "Abu Dhabi Grand Prix",
        "total_laps":        58,
        "starting_compound": "MEDIUM",
        "year":              2024,
        "base_grid":         _ABU_DHABI_GRID,
    },
]

_EGO_DRIVERS = ["VER", "LEC", "NOR", "HAM", "ZHO"]

# ── Eval scenario A: Bahrain, VER P1 ──────────────────────────────────────────
_EVAL_VER_P1: dict[str, Any] = {
    "circuit":               "Bahrain Grand Prix",
    "year":                  2024,
    "total_laps":            57,
    "ego_driver":            "VER",
    "ego_starting_position": 1,
    "starting_grid":         _BAHRAIN_GRID,
    "starting_compounds":    {d: "SOFT" for d in _BAHRAIN_GRID},
    "weather": {"air_temp": 24.0, "track_temp": 38.0, "humidity": 45.0, "is_wet": False},
    "two_compound_rule_enforced": True,
}

# Eval scenario B: Bahrain, ZHO P15 (swap ZHO and ALB in the base grid)
_BAHRAIN_ZHO_P15 = list(_BAHRAIN_GRID)
_BAHRAIN_ZHO_P15[14], _BAHRAIN_ZHO_P15[17] = (
    _BAHRAIN_ZHO_P15[17], _BAHRAIN_ZHO_P15[14]
)  # ZHO↔ALB: put ZHO at index 14 (P15), ALB at index 17 (P18)

_EVAL_ZHO_P15: dict[str, Any] = {
    "circuit":               "Bahrain Grand Prix",
    "year":                  2024,
    "total_laps":            57,
    "ego_driver":            "ZHO",
    "ego_starting_position": 15,
    "starting_grid":         _BAHRAIN_ZHO_P15,
    "starting_compounds":    {d: "SOFT" for d in _BAHRAIN_ZHO_P15},
    "weather": {"air_temp": 24.0, "track_temp": 38.0, "humidity": 45.0, "is_wet": False},
    "two_compound_rule_enforced": True,
}


# ── Grid helpers ───────────────────────────────────────────────────────────────

def _grid_with_ego(base_grid: list[str], ego_driver: str, ego_pos: int) -> list[str]:
    """Return a copy of base_grid with ego_driver placed at ego_pos (1-indexed).

    Swaps ego_driver with whoever currently occupies ego_pos.
    If ego_driver is not in base_grid, falls back to the base_grid unchanged
    (ego_pos must still be valid).
    """
    grid = list(base_grid)
    if ego_driver not in grid:
        return grid
    cur = grid.index(ego_driver)
    if cur + 1 != ego_pos:
        occupant = grid[ego_pos - 1]
        grid[ego_pos - 1]  = ego_driver
        grid[cur]          = occupant
    return grid


def _build_cfg(circuit_info: dict, ego_driver: str, ego_pos: int) -> dict[str, Any]:
    """Build a GridRaceEnv reset config from a circuit dict + ego spec."""
    grid = _grid_with_ego(circuit_info["base_grid"], ego_driver, ego_pos)
    cmp  = circuit_info["starting_compound"]
    return {
        "circuit":               circuit_info["circuit"],
        "year":                  circuit_info["year"],
        "total_laps":            circuit_info["total_laps"],
        "ego_driver":            ego_driver,
        "ego_starting_position": ego_pos,
        "starting_grid":         grid,
        "starting_compounds":    {d: cmp for d in grid},
        "two_compound_rule_enforced": True,
    }


# ── Curriculum wrappers ────────────────────────────────────────────────────────

class _Stage1Env(gym.Wrapper):
    """Fixed scenario — Bahrain 2024, VER P1."""

    def reset(self, **kwargs: Any):
        kwargs["options"] = _EVAL_VER_P1
        return self.env.reset(**kwargs)


class _Stage2Env(gym.Wrapper):
    """Bahrain only — 5 ego drivers × P1-P10."""

    def reset(self, **kwargs: Any):
        ego   = random.choice(_EGO_DRIVERS)
        pos   = random.randint(1, 10)
        kwargs["options"] = _build_cfg(_TRAIN_CIRCUITS[0], ego, pos)
        return self.env.reset(**kwargs)


class _Stage3Env(gym.Wrapper):
    """All 4 circuits — 5 ego drivers × P1-P15."""

    def reset(self, **kwargs: Any):
        info  = random.choice(_TRAIN_CIRCUITS)
        ego   = random.choice(_EGO_DRIVERS)
        pos   = random.randint(1, 15)
        kwargs["options"] = _build_cfg(info, ego, pos)
        return self.env.reset(**kwargs)


class _EvalVEREnv(gym.Wrapper):
    """Fixed eval — Bahrain VER P1."""

    def reset(self, **kwargs: Any):
        kwargs["options"] = _EVAL_VER_P1
        return self.env.reset(**kwargs)


def _make_stage1() -> gym.Env:
    return Monitor(_Stage1Env(GridRaceEnv()))


def _make_stage2() -> gym.Env:
    return Monitor(_Stage2Env(GridRaceEnv()))


def _make_stage3() -> gym.Env:
    return Monitor(_Stage3Env(GridRaceEnv()))


# ── Baseline policies ──────────────────────────────────────────────────────────

def _fixed_lap18(obs: np.ndarray, lap_num: int) -> int:
    """Pit to HARD on lap 18, stay otherwise."""
    return 3 if lap_num == 18 else 0


def _sandbox_ppo_policy(model: PPO):
    """Wrap a 13-dim Sandbox PPO model for use in the 25-dim Grid env."""
    def _fn(obs: np.ndarray, _lap: int) -> int:
        action, _ = model.predict(obs[:13], deterministic=True)
        return int(action)
    return _fn


def _random_policy(obs: np.ndarray, lap_num: int) -> int:
    return random.randint(0, 3)


# ── Episode runner ─────────────────────────────────────────────────────────────

def _run_episode(policy_fn, eval_cfg: dict, seed: int) -> dict:
    """Run one GridRaceEnv episode; policy_fn(obs, lap_num) → action."""
    env  = GridRaceEnv()
    obs, _ = env.reset(seed=seed, options=eval_cfg)
    total_reward   = 0.0
    terminated = truncated = False
    lap_num    = 1
    info: dict = {}
    while not (terminated or truncated):
        action = policy_fn(obs, lap_num)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        lap_num      += 1
    return {
        "reward":         total_reward,
        "final_position": info.get("ego_position", 20),
    }


def _evaluate(policy_fn, eval_cfg: dict, n_episodes: int = 10) -> dict:
    rows      = [_run_episode(policy_fn, eval_cfg, seed=i) for i in range(n_episodes)]
    rewards   = [r["reward"]         for r in rows]
    positions = [r["final_position"] for r in rows]
    return {
        "mean_reward":   float(np.mean(rewards)),
        "mean_position": float(np.mean(positions)),
        "wins":          sum(1 for p in positions if p == 1),
    }


# ── Plots ──────────────────────────────────────────────────────────────────────

def _plot_training_curve(log_path: Path, out: Path) -> None:
    eval_file = log_path / "evaluations.npz"
    if not eval_file.exists():
        logger.warning("evaluations.npz not found — skipping training curve")
        return
    data      = np.load(eval_file)
    timesteps = data["timesteps"]
    mean_rew  = data["results"].mean(axis=1)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(timesteps, mean_rew, lw=2, color="#e8002d", label="Mean reward (5 eps)")
    ax.axhline(0, color="white", lw=0.5, alpha=0.3)
    ax.set_xlabel("Timesteps")
    ax.set_ylabel("Mean Episode Reward")
    ax.set_title("PPO Grid Agent — Training Curve")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_facecolor("#0d1117")
    fig.patch.set_facecolor("#0d1117")
    ax.tick_params(colors="white")
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color("white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.title.set_color("white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Training curve → {out}")


def _plot_baseline_comparison(
    summaries_ver: dict[str, dict],
    summaries_zho: dict[str, dict],
    out: Path,
) -> None:
    labels = list(summaries_ver.keys())
    ver_rew = [summaries_ver[k]["mean_reward"] for k in labels]
    zho_rew = [summaries_zho[k]["mean_reward"] for k in labels]
    colors  = ["#e8002d", "#1e90ff", "#ff8800", "#888888"]

    x  = np.arange(len(labels))
    w  = 0.35

    fig, ax = plt.subplots(figsize=(11, 6))
    b1 = ax.bar(x - w / 2, ver_rew, w, label="VER P1", color=colors, alpha=0.9, edgecolor="#ffffff44")
    b2 = ax.bar(x + w / 2, zho_rew, w, label="ZHO P15", color=colors, alpha=0.55, edgecolor="#ffffff44", hatch="//")
    ax.bar_label(b1, labels=[f"{v:+.1f}" for v in ver_rew], padding=3, fontsize=9)
    ax.bar_label(b2, labels=[f"{v:+.1f}" for v in zho_rew], padding=3, fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Mean Episode Reward (10 eps)")
    ax.set_title("Bahrain GP — Policy Comparison (solid=VER P1, hatched=ZHO P15)")
    ax.legend()
    ax.set_facecolor("#0d1117")
    fig.patch.set_facecolor("#0d1117")
    ax.tick_params(colors="white")
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color("white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.title.set_color("white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")
    ax.grid(True, alpha=0.2, axis="y", color="white")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Baseline comparison → {out}")


# ── Training ───────────────────────────────────────────────────────────────────

def train(total_timesteps: int = 1_500_000) -> None:
    for d in [_MODELS_DIR, _FIGURES_DIR, _LOGS_DIR, _TB_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    stage1_steps = min(200_000, int(total_timesteps * 0.133))
    stage2_steps = min(400_000, int(total_timesteps * 0.267))
    stage3_steps = total_timesteps - stage1_steps - stage2_steps

    print(f"\n{'='*64}")
    print(f"  Phase 5.2 — PPO Grid Agent Training")
    print(f"  Stage 1 : {stage1_steps:>9,}  (Bahrain · VER · P1 · fixed grid)")
    print(f"  Stage 2 : {stage2_steps:>9,}  (Bahrain · 5 drivers · P1–P10)")
    print(f"  Stage 3 : {stage3_steps:>9,}  (4 circuits · 5 drivers · P1–P15)")
    print(f"  Total   : {total_timesteps:>9,}  timesteps")
    print(f"{'='*64}\n")

    eval_env = Monitor(_EvalVEREnv(GridRaceEnv()))

    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=str(_LOGS_DIR),
        log_path=str(_LOGS_DIR),
        eval_freq=50_000,       # every 50K steps (wall-clock slower than sandbox)
        n_eval_episodes=5,
        deterministic=True,
        render=False,
        verbose=1,
    )

    # ── Stage 1 ───────────────────────────────────────────────────────────────
    print("Stage 1 — fixed scenario (Bahrain · VER · P1)")
    print("-" * 50)
    vec_s1 = make_vec_env(_make_stage1, n_envs=2)

    model = PPO(
        policy="MlpPolicy",
        env=vec_s1,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.02,
        verbose=1,
        tensorboard_log=str(_TB_DIR),
        seed=42,
    )

    t0 = time.time()
    model.learn(
        total_timesteps=stage1_steps,
        callback=eval_callback,
        progress_bar=True,
        reset_num_timesteps=True,
    )
    print(f"\nStage 1 complete in {(time.time() - t0) / 60:.1f} min")

    # ── Stage 2 ───────────────────────────────────────────────────────────────
    print("\nStage 2 — Bahrain · 5 drivers · P1–P10")
    print("-" * 50)
    vec_s2 = make_vec_env(_make_stage2, n_envs=2)
    model.set_env(vec_s2)

    t1 = time.time()
    model.learn(
        total_timesteps=stage2_steps,
        callback=eval_callback,
        progress_bar=True,
        reset_num_timesteps=False,
    )
    print(f"\nStage 2 complete in {(time.time() - t1) / 60:.1f} min")

    # ── Stage 3 ───────────────────────────────────────────────────────────────
    print("\nStage 3 — 4 circuits · 5 drivers · P1–P15")
    print("-" * 50)
    vec_s3 = make_vec_env(_make_stage3, n_envs=2)
    model.set_env(vec_s3)

    t2 = time.time()
    model.learn(
        total_timesteps=stage3_steps,
        callback=eval_callback,
        progress_bar=True,
        reset_num_timesteps=False,
    )
    total_elapsed = time.time() - t0
    print(f"\nStage 3 complete in {(time.time() - t2) / 60:.1f} min")
    print(f"Total training time: {total_elapsed / 60:.1f} min ({total_elapsed / 3600:.2f} h)")

    # ── Save artifacts ────────────────────────────────────────────────────────
    final_path = str(_MODELS_DIR / "ppo_grid_final")
    model.save(final_path)
    print(f"\nFinal model → {final_path}.zip")

    best_src = _LOGS_DIR / "best_model.zip"
    best_dst = _MODELS_DIR / "ppo_grid_best.zip"
    if best_src.exists():
        best_src.rename(best_dst)
        print(f"Best model  → {best_dst}")
    else:
        model.save(str(_MODELS_DIR / "ppo_grid_best"))
        print(f"Best model  → {_MODELS_DIR / 'ppo_grid_best.zip'}  (no EvalCallback best found)")

    # ── Training curve ────────────────────────────────────────────────────────
    print("\nGenerating plots...")
    _plot_training_curve(_LOGS_DIR, _FIGURES_DIR / "grid_training_curve.png")

    # ── Baseline comparison ───────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print("  Post-training Evaluation")
    print(f"{'='*64}")

    load_path = str(
        best_dst if best_dst.exists() else _MODELS_DIR / "ppo_grid_final"
    )
    grid_ppo = PPO.load(load_path)
    print(f"  Loaded: {load_path}\n")

    def grid_ppo_policy(obs: np.ndarray, lap_num: int) -> int:
        action, _ = grid_ppo.predict(obs, deterministic=True)
        return int(action)

    sandbox_best = _MODELS_DIR / "ppo_sandbox_best.zip"
    sandbox_model = PPO.load(str(sandbox_best)) if sandbox_best.exists() else None
    if sandbox_model is None:
        print("  WARNING: ppo_sandbox_best.zip not found — skipping Sandbox PPO baseline")

    def sandbox_ppo_policy(obs: np.ndarray, lap_num: int) -> int:
        if sandbox_model is None:
            return 0
        action, _ = sandbox_model.predict(obs[:13], deterministic=True)
        return int(action)

    policies: dict[str, Any] = {
        "Grid PPO":       grid_ppo_policy,
        "Sandbox PPO":    sandbox_ppo_policy,
        "Fixed (lap 18)": _fixed_lap18,
        "Random":         _random_policy,
    }

    def _print_scenario(title: str, eval_cfg: dict) -> dict[str, dict]:
        print(f"\n=== {title} ===")
        hdr = f"{'Policy':<18} | {'Mean Reward':>11} | {'Mean Pos':>8} | Wins"
        print(hdr)
        print("-" * len(hdr))
        summaries: dict[str, dict] = {}
        for name, fn in policies.items():
            s = _evaluate(fn, eval_cfg, n_episodes=10)
            summaries[name] = s
            print(
                f"{name:<18} | {s['mean_reward']:>+11.2f} | "
                f"P{s['mean_position']:>6.1f}  | "
                f"{s['wins']}/10"
            )
        return summaries

    ver_summaries = _print_scenario("Bahrain VER P1",  _EVAL_VER_P1)
    zho_summaries = _print_scenario("Bahrain ZHO P15", _EVAL_ZHO_P15)

    _plot_baseline_comparison(
        ver_summaries, zho_summaries,
        _FIGURES_DIR / "grid_baseline_comparison.png",
    )

    print(f"\n{'='*64}")
    print("Phase 5.2 complete.")
    print(f"  models/ppo_grid_final.zip")
    print(f"  models/ppo_grid_best.zip")
    print(f"  models/figures/grid_training_curve.png")
    print(f"  models/figures/grid_baseline_comparison.png")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Phase 5.2 — Train PPO Grid agent")
    ap.add_argument("--timesteps", type=int, default=1_500_000,
                    help="Total training timesteps (default: 1,500,000)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    train(total_timesteps=args.timesteps)
