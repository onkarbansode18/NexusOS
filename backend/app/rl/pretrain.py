"""
Nexus Double DQN — Pretraining Script
=======================================
Trains a baseline Double DQN model across all 6 scenarios and registers it
as the default active model in the checkpoint catalog.
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nexus.rl.pretrain")

# Add current dir to python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/../.."))

from app.rl.environment import NexusRLEnvironment
from app.rl.double_dqn_agent import DoubleDQNAgent
from app.rl.trainer import RLTrainer, TrainerConfig
from app.rl.model_manager import ModelManager


def main():
    logger.info("Starting baseline pretraining (30 episodes)...")
    ckpt_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "checkpoints"))
    os.makedirs(ckpt_dir, exist_ok=True)

    config = TrainerConfig(
        episodes=30,
        max_steps_per_episode=60,
        batch_size=32,
        checkpoint_dir=ckpt_dir,
    )

    agent = DoubleDQNAgent(
        learning_rate=1e-3,
        epsilon=1.0,
        epsilon_min=0.05,
        epsilon_decay=0.95,
        batch_size=32,
    )

    env = NexusRLEnvironment(max_steps_per_episode=60)
    trainer = RLTrainer(config=config, agent=agent, env=env)

    metrics = trainer.train_sync(episodes=30)
    avg_reward = sum(m.total_reward for m in metrics) / len(metrics)
    success_rate = (sum(1 for m in metrics if m.success) / len(metrics)) * 100.0

    logger.info("Pretraining completed. Avg Reward: %.2f, Success Rate: %.1f%%", avg_reward, success_rate)

    # Save default checkpoint
    default_ckpt_path = os.path.join(ckpt_dir, "nexus_ddqn_default.pt")
    agent.save_checkpoint(
        default_ckpt_path,
        metadata={
            "episodes": 30,
            "avg_reward": avg_reward,
            "success_rate": success_rate,
            "type": "pretrained_baseline",
        },
    )

    # Register in ModelManager
    manager = ModelManager(checkpoints_dir=ckpt_dir)
    manager.register_model(
        filepath=default_ckpt_path,
        name="Nexus Double DQN Production Baseline",
        version="1.0.0",
        episodes_trained=30,
        best_reward=trainer.best_reward,
        success_rate=success_rate,
        notes="Pretrained across all 6 scenarios with multi-objective self-healing reward",
        set_active=True,
    )
    logger.info("Registered and set nexus_ddqn_default.pt as active model.")


if __name__ == "__main__":
    main()
