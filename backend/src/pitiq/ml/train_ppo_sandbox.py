"""Phase 5.1 — Train PPO agent on SandboxRaceEnv with curriculum learning.

Stage 1 (0–300K):  Bahrain · VER · P1 · SOFT — clean single-scenario signal.
Stage 2 (300K–1M): 4 circuits × 5 drivers × P1–P10 — generalisation.

CLI:  python -m pitiq.ml.train_ppo_sandbox [--timesteps N]
"""

from __future__ import annotations

import os
# Must be set before any import that triggers libomp or PyTorch to load.
# XGBoost uses Homebrew libomp; PyTorch bundles its own OpenMP runtime.
# Two OpenMP runtimes in the same process segfault on macOS Apple Silicon
# unless this flag allows them to coexist.
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

from pitiq.envs.sandbox import SandboxRaceEnv
from pitiq.ml.compound_constants import COMPOUND_CLIFF_LAP

logger = logging.getLogger(__name__)

_REPO_ROOT   = Path(__file__).parents[4]
_MODELS_DIR  = _REPO_ROOT / "models"
_FIGURES_DIR = _MODELS_DIR / "figures"
_LOGS_DIR    = _MODELS_DIR / "logs"
_TB_DIR      = _MODELS_DIR / "tensorboard" / "sandbox"

_TRAIN_CIRCUITS = [
    {"circuit": "Bahrain Grand Prix",   "total_laps": 57, "starting_compound": "SOFT"},
    {"circuit": "Italian Grand Prix",   "total_laps": 53, "starting_compound": "MEDIUM"},
    {"circuit": "Belgian Grand Prix",   "total_laps": 44, "starting_compound": "MEDIUM"},
    {"circuit": "Abu Dhabi Grand Prix", "total_laps": 58, "starting_compound": "MEDIUM"},
]
_TRAIN_DRIVERS   = ["VER", "LEC", "NOR", "HAM", "ZHO"]
_COMPOUNDS_ORDER = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]

_EVAL_OPTIONS: dict[str, Any] = {
    "circuit":                    "Bahrain Grand Prix",
    "driver":                     "VER",
    "year":                       2024,
    "total_laps":                 57,
    "starting_position":          1,
    "starting_compound":          "SOFT",
    "two_compound_rule_enforced": True,
}


# ── Curriculum wrappers ────────────────────────────────────────────────────────

class _Stage1Env(gym.Wrapper):
    """Fixed Stage-1 scenario: Bahrain 2024, VER, P1, SOFT."""

    def reset(self, **kwargs: Any):
        kwargs["options"] = {
            "circuit":                    "Bahrain Grand Prix",
            "driver":                     "VER",
            "year":                       2024,
            "total_laps":                 57,
            "starting_position":          1,
            "starting_compound":          "SOFT",
            "two_compound_rule_enforced": True,
        }
        return self.env.reset(**kwargs)


class _Stage2Env(gym.Wrapper):
    """Randomised Stage-2: 4 circuits × 5 drivers × P1–P10."""

    def reset(self, **kwargs: Any):
        cfg = random.choice(_TRAIN_CIRCUITS)
        kwargs["options"] = {
            **cfg,
            "driver":                     random.choice(_TRAIN_DRIVERS),
            "year":                       2024,
            "starting_position":          random.randint(1, 10),
            "two_compound_rule_enforced": True,
        }
        return self.env.reset(**kwargs)


class _EvalEnv(gym.Wrapper):
    """Fixed eval scenario: Bahrain 2024, VER, P1, SOFT."""

    def reset(self, **kwargs: Any):
        kwargs["options"] = _EVAL_OPTIONS
        return self.env.reset(**kwargs)


def _make_stage1_env() -> gym.Env:
    return Monitor(_Stage1Env(SandboxRaceEnv()))


def _make_stage2_env() -> gym.Env:
    return Monitor(_Stage2Env(SandboxRaceEnv()))


# ── Baseline policies ──────────────────────────────────────────────────────────

def _never_pit(obs: np.ndarray, _env: SandboxRaceEnv) -> int:
    return 0


def _cliff_pit(obs: np.ndarray, _env: SandboxRaceEnv) -> int:
    tire_age     = float(obs[6])
    compound_idx = int(obs[1:6].argmax())
    compound     = _COMPOUNDS_ORDER[compound_idx]
    cliff        = COMPOUND_CLIFF_LAP.get(compound, 999)
    return 3 if tire_age >= cliff else 0   # pit to HARD at cliff


def _random_policy(obs: np.ndarray, env: SandboxRaceEnv) -> int:
    return int(env.action_space.sample())


# ── Evaluation harness ─────────────────────────────────────────────────────────

def _run_episode(policy_fn, seed: int) -> dict:
    env = SandboxRaceEnv()
    obs, _ = env.reset(seed=seed, options=_EVAL_OPTIONS)
    total_reward = 0.0
    terminated = truncated = False
    info: dict = {}
    while not (terminated or truncated):
        obs, reward, terminated, truncated, info = env.step(policy_fn(obs, env))
        total_reward += reward
    return {
        "reward":         total_reward,
        "final_position": info.get("position", 20),
        "race_time":      info.get("cumulative_race_time", 0.0),
    }


def _evaluate(policy_fn, n_episodes: int = 10, seed_offset: int = 0) -> dict:
    rows      = [_run_episode(policy_fn, seed=seed_offset + i) for i in range(n_episodes)]
    rewards   = [r["reward"]         for r in rows]
    positions = [r["final_position"] for r in rows]
    times     = [r["race_time"]      for r in rows]
    return {
        "mean_reward":    float(np.mean(rewards)),
        "mean_position":  float(np.mean(positions)),
        "mean_race_time": float(np.mean(times)),
        "win_rate":       sum(1 for p in positions if p == 1),
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
    fig, ax   = plt.subplots(figsize=(10, 5))
    ax.plot(timesteps, mean_rew, lw=2, color="#e8002d", label="Mean reward (5 eps)")
    ax.axhline(0, color="white", lw=0.5, alpha=0.3)
    ax.set_xlabel("Timesteps")
    ax.set_ylabel("Mean Episode Reward")
    ax.set_title("PPO Sandbox Agent — Training Curve")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Training curve → {out}")


def _plot_baseline_comparison(summaries: dict[str, dict], out: Path) -> None:
    labels = list(summaries.keys())
    means  = [summaries[k]["mean_reward"] for k in labels]
    colors = ["#e8002d", "#1e90ff", "#ff8800", "#888888"]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(labels, means, color=colors[: len(labels)], edgecolor="#ffffff44", linewidth=0.8)
    label_texts = [f"{v:+.2f}" for v in means]
    ax.bar_label(bars, labels=label_texts, padding=4, fontsize=10)
    ax.set_ylabel("Mean Episode Reward (10 eps)")
    ax.set_title("Bahrain GP · VER · P1 — Policy Comparison")
    ax.set_facecolor("#0d1117")
    fig.patch.set_facecolor("#0d1117")
    ax.tick_params(colors="white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.title.set_color("white")
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color("white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")
    ax.grid(True, alpha=0.2, axis="y", color="white")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  Baseline comparison → {out}")


# ── Training ───────────────────────────────────────────────────────────────────

def train(total_timesteps: int = 1_000_000) -> None:
    for d in [_MODELS_DIR, _FIGURES_DIR, _LOGS_DIR, _TB_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    stage1_steps = min(300_000, int(total_timesteps * 0.3))
    stage2_steps = total_timesteps - stage1_steps

    print(f"\n{'='*64}")
    print(f"  Phase 5.1 — PPO Sandbox Agent Training")
    print(f"  Stage 1 : {stage1_steps:>9,}  (Bahrain · VER · P1 · SOFT)")
    print(f"  Stage 2 : {stage2_steps:>9,}  (4 circuits · 5 drivers · P1–P10)")
    print(f"  Total   : {total_timesteps:>9,}  timesteps")
    print(f"{'='*64}\n")

    eval_env = Monitor(_EvalEnv(SandboxRaceEnv()))

    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=str(_MODELS_DIR),
        log_path=str(_LOGS_DIR),
        eval_freq=25_000,      # ~100K total env steps between evals with 4 envs
        n_eval_episodes=5,
        deterministic=True,
        render=False,
        verbose=1,
    )

    # ── Stage 1 ───────────────────────────────────────────────────────────────
    print("Stage 1 — fixed scenario (Bahrain · VER · P1)")
    print("-" * 50)
    vec_s1 = make_vec_env(_make_stage1_env, n_envs=4)

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
        ent_coef=0.01,
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
    print("\nStage 2 — curriculum (4 circuits · 5 drivers · P1–P10)")
    print("-" * 50)
    vec_s2 = make_vec_env(_make_stage2_env, n_envs=4)
    model.set_env(vec_s2)

    t1 = time.time()
    model.learn(
        total_timesteps=stage2_steps,
        callback=eval_callback,
        progress_bar=True,
        reset_num_timesteps=False,
    )
    total_elapsed = time.time() - t0
    print(f"\nStage 2 complete in {(time.time() - t1) / 60:.1f} min")
    print(f"Total training time: {total_elapsed / 60:.1f} min ({total_elapsed / 3600:.2f} h)")

    # ── Save artifacts ────────────────────────────────────────────────────────
    final_path = str(_MODELS_DIR / "ppo_sandbox_final")
    model.save(final_path)
    print(f"\nFinal model  → {final_path}.zip")

    best_src = _MODELS_DIR / "best_model.zip"
    best_dst = _MODELS_DIR / "ppo_sandbox_best.zip"
    if best_src.exists():
        best_src.rename(best_dst)
    else:
        model.save(str(_MODELS_DIR / "ppo_sandbox_best"))
    print(f"Best model   → {best_dst}")

    # ── Training curve ────────────────────────────────────────────────────────
    print("\nGenerating plots...")
    _plot_training_curve(_LOGS_DIR, _FIGURES_DIR / "sandbox_training_curve.png")

    # ── Baseline comparison ───────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print("  Post-training Evaluation — Bahrain GP · VER · P1 · 10 eps")
    print(f"{'='*64}")

    load_path = str(best_dst if best_dst.exists() else _MODELS_DIR / "ppo_sandbox_final")
    ppo_model = PPO.load(load_path)
    print(f"  Loaded: {load_path}\n")

    def ppo_policy(obs: np.ndarray, _env: SandboxRaceEnv) -> int:
        action, _ = ppo_model.predict(obs, deterministic=True)
        return int(action)

    policies: dict[str, Any] = {
        "PPO (trained)": ppo_policy,
        "Cliff-pit":     _cliff_pit,
        "Never-pit":     _never_pit,
        "Random":        _random_policy,
    }

    summaries: dict[str, dict] = {}
    for name, fn in policies.items():
        summaries[name] = _evaluate(fn, n_episodes=10)

    hdr = f"{'Policy':<18} | {'Mean Reward':>11} | {'Mean Pos':>8} | {'Mean Time':>10} | Wins"
    print(hdr)
    print("-" * len(hdr))
    for name, s in summaries.items():
        print(
            f"{name:<18} | {s['mean_reward']:>+11.2f} | "
            f"P{s['mean_position']:>6.1f}  | "
            f"{s['mean_race_time']:>9,.0f}s | "
            f"{s['win_rate']}/10"
        )

    _plot_baseline_comparison(summaries, _FIGURES_DIR / "sandbox_baseline_comparison.png")

    print("\nPhase 5.1 complete.")
    print(f"  models/ppo_sandbox_final.zip")
    print(f"  models/ppo_sandbox_best.zip")
    print(f"  models/figures/sandbox_training_curve.png")
    print(f"  models/figures/sandbox_baseline_comparison.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Phase 5.1 — Train PPO Sandbox agent")
    ap.add_argument("--timesteps", type=int, default=1_000_000,
                    help="Total training timesteps (default: 1,000,000)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    train(total_timesteps=args.timesteps)
