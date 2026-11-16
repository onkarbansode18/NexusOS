"""
Nexus Double DQN — Training Pipeline & Simulation Runner
=========================================================
Manages automated simulated training loops, experience collection,
Double DQN policy optimization, and evaluation metric tracking.
"""

from __future__ import annotations

import os
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from app.rl.environment import NexusRLEnvironment, SimulationScenario, ACTION_DIM
from app.rl.double_dqn_agent import DoubleDQNAgent
from app.rl.replay_buffer import ExperienceReplayBuffer

logger = logging.getLogger("nexus.rl.trainer")


@dataclass
class EpisodeMetric:
    episode_num: int
    scenario: str
    total_reward: float
    steps: int
    avg_loss: float
    epsilon: float
    success: bool
    duration_sec: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class TrainerConfig:
    episodes: int = 50
    max_steps_per_episode: int = 100
    learning_rate: float = 1e-3
    gamma: float = 0.99
    epsilon: float = 1.0
    epsilon_min: float = 0.05
    epsilon_decay: float = 0.992
    target_update_freq: int = 10
    batch_size: int = 64
    buffer_capacity: int = 50000
    checkpoint_dir: str = "app/rl/checkpoints"
    save_freq: int = 10


class RLTrainer:
    """
    Orchestrates episode generation, replay buffering, and neural network updates.
    Supports asynchronous thread execution with pause/cancel controls.
    """

    def __init__(
        self,
        config: Optional[TrainerConfig] = None,
        agent: Optional[DoubleDQNAgent] = None,
        env: Optional[NexusRLEnvironment] = None,
    ) -> None:
        self.config = config or TrainerConfig()
        self.env = env or NexusRLEnvironment(max_steps_per_episode=self.config.max_steps_per_episode)
        self.agent = agent or DoubleDQNAgent(
            learning_rate=self.config.learning_rate,
            gamma=self.config.gamma,
            epsilon=self.config.epsilon,
            epsilon_min=self.config.epsilon_min,
            epsilon_decay=self.config.epsilon_decay,
            target_update_freq=self.config.target_update_freq,
            batch_size=self.config.batch_size,
        )
        self.buffer = ExperienceReplayBuffer(capacity=self.config.buffer_capacity)

        self.is_training: bool = False
        self._stop_requested: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self.current_episode: int = 0
        self.total_episodes: int = 0
        self.metrics_history: List[EpisodeMetric] = []
        self.best_reward: float = -float("inf")
        self.status_message: str = "Idle"

    def start_training_async(
        self,
        episodes: Optional[int] = None,
        on_episode_complete: Optional[Callable[[EpisodeMetric], None]] = None,
    ) -> bool:
        """Launch background training thread."""
        with self._lock:
            if self.is_training:
                logger.warning("Training already in progress.")
                return False
            self.is_training = True
            self._stop_requested = False
            self.status_message = "Training started"

        target_episodes = episodes or self.config.episodes
        self._thread = threading.Thread(
            target=self._run_training_loop,
            args=(target_episodes, on_episode_complete),
            daemon=True,
        )
        self._thread.start()
        return True

    def stop_training(self) -> None:
        """Signal background training thread to stop."""
        with self._lock:
            self._stop_requested = True
            self.status_message = "Stopping training..."

    def _run_training_loop(
        self,
        episodes: int,
        callback: Optional[Callable[[EpisodeMetric], None]] = None,
    ) -> None:
        """Core training loop running over specified simulated episodes."""
        scenarios = list(SimulationScenario)
        start_time = time.time()

        try:
            for ep in range(1, episodes + 1):
                with self._lock:
                    if self._stop_requested:
                        self.status_message = f"Training stopped by user at episode {ep-1}"
                        break
                    self.current_episode = ep
                    self.total_episodes = ep

                scenario = scenarios[(ep - 1) % len(scenarios)]
                ep_start = time.time()
                obs, _ = self.env.reset(scenario=scenario)

                ep_reward = 0.0
                ep_losses: List[float] = []
                step_count = 0
                terminated = False
                truncated = False

                while not (terminated or truncated):
                    with self._lock:
                        if self._stop_requested:
                            break

                    step_count += 1
                    action, _ = self.agent.select_action(obs, evaluate=False)
                    next_obs, reward, term, trunc, info = self.env.step(action)

                    # Store in replay buffer
                    self.buffer.push(obs, action, reward, next_obs, term or trunc)

                    # Train step
                    loss = self.agent.train_step(self.buffer)
                    if loss is not None:
                        ep_losses.append(loss)

                    ep_reward += reward
                    obs = next_obs
                    terminated = term
                    truncated = trunc

                ep_duration = time.time() - ep_start
                avg_loss = float(np.mean(ep_losses)) if ep_losses else 0.0
                # Success criteria: finished with healthy state or high reward
                is_success = ep_reward > 10.0 or getattr(self.env.state, "historical_health", 0.0) >= 0.75

                metric = EpisodeMetric(
                    episode_num=ep,
                    scenario=scenario.value,
                    total_reward=round(ep_reward, 2),
                    steps=step_count,
                    avg_loss=round(avg_loss, 4),
                    epsilon=round(float(self.agent.epsilon), 4),
                    success=is_success,
                    duration_sec=round(ep_duration, 2),
                )

                with self._lock:
                    self.metrics_history.append(metric)
                    if ep_reward > self.best_reward:
                        self.best_reward = ep_reward
                        # Save best checkpoint
                        ckpt_path = os.path.join(self.config.checkpoint_dir, "nexus_dqn_best.pt")
                        self.agent.save_checkpoint(ckpt_path, metadata={"episode": ep, "reward": ep_reward})

                    if ep % self.config.save_freq == 0:
                        ckpt_latest = os.path.join(self.config.checkpoint_dir, "nexus_dqn_latest.pt")
                        self.agent.save_checkpoint(ckpt_latest, metadata={"episode": ep, "reward": ep_reward})

                if callback:
                    try:
                        callback(metric)
                    except Exception as cb_err:
                        logger.error("Error in episode callback: %s", cb_err)

            total_dur = time.time() - start_time
            with self._lock:
                self.status_message = f"Training completed ({episodes} episodes in {total_dur:.1f}s)"

        except Exception as e:
            logger.exception("Unexpected error in training loop: %s", e)
            with self._lock:
                self.status_message = f"Training error: {str(e)}"
        finally:
            with self._lock:
                self.is_training = False

    def train_sync(self, episodes: int = 10) -> List[EpisodeMetric]:
        """Synchronously train for N episodes (useful for tests and headless verification)."""
        collected: List[EpisodeMetric] = []
        self._run_training_loop(episodes=episodes, callback=collected.append)
        return collected

    def get_progress(self) -> Dict[str, Any]:
        """Return real-time snapshot of training state for API and UI."""
        with self._lock:
            recent_metrics = [
                {
                    "episode": m.episode_num,
                    "scenario": m.scenario,
                    "reward": m.total_reward,
                    "steps": m.steps,
                    "loss": m.avg_loss,
                    "epsilon": m.epsilon,
                    "success": m.success,
                    "duration": m.duration_sec,
                }
                for m in self.metrics_history[-50:]  # last 50 episodes
            ]
            return {
                "is_training": self.is_training,
                "status": self.status_message,
                "current_episode": self.current_episode,
                "total_episodes": self.total_episodes,
                "epsilon": round(float(self.agent.epsilon), 4),
                "best_reward": round(float(self.best_reward), 2) if self.best_reward != -float("inf") else 0.0,
                "buffer_size": len(self.buffer),
                "recent_episodes": recent_metrics,
            }
