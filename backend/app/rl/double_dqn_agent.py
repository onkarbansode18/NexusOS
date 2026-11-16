"""
Nexus Double DQN — Agent & Neural Network
==========================================
Double Deep Q-Network (Double DQN) implementation with:
  - Online Q-Network and Target Q-Network
  - Double Q-learning TD error: a* = argmax Q_online(s'), y = r + gamma * Q_target(s', a*)
  - Decoupled action selection and evaluation to prevent Q-value overestimation
  - Epsilon-greedy exploration schedule with dynamic decay
  - Explainability metadata generation for every inference decision
"""

from __future__ import annotations

import os
import random
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

import torch
import torch.nn as nn
import torch.optim as optim

from app.rl.environment import ACTION_DIM, ACTION_NAMES
from app.rl.state_encoder import STATE_DIM, FEATURE_NAMES
from app.rl.replay_buffer import ExperienceReplayBuffer

logger = logging.getLogger("nexus.rl.double_dqn")


class QNetwork(nn.Module):
    """
    Multilayer Perceptron Q-Network mapping 14-dim state -> 7 discrete action Q-values.
    """

    def __init__(
        self,
        state_dim: int = STATE_DIM,
        action_dim: int = ACTION_DIM,
        hidden_dims: Tuple[int, int] = (128, 128),
    ) -> None:
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim

        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dims[0]),
            nn.ReLU(),
            nn.Linear(hidden_dims[0], hidden_dims[1]),
            nn.ReLU(),
            nn.Linear(hidden_dims[1], action_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class DoubleDQNAgent:
    """
    Double Deep Q-Network Reinforcement Learning Agent.
    """

    def __init__(
        self,
        state_dim: int = STATE_DIM,
        action_dim: int = ACTION_DIM,
        learning_rate: float = 1e-3,
        gamma: float = 0.99,
        epsilon: float = 1.0,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.995,
        target_update_freq: int = 10,
        batch_size: int = 64,
        grad_clip: float = 1.0,
        hidden_dims: Tuple[int, int] = (128, 128),
        device: Optional[str] = None,
    ) -> None:
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.target_update_freq = target_update_freq
        self.batch_size = batch_size
        self.grad_clip = grad_clip

        self.device = torch.device(
            device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        )

        # 1. Online and Target Q-Networks
        self.online_net = QNetwork(state_dim, action_dim, hidden_dims).to(self.device)
        self.target_net = QNetwork(state_dim, action_dim, hidden_dims).to(self.device)
        self.update_target_network()
        self.target_net.eval()  # Target net is never trained directly

        # 2. Optimization setup
        self.optimizer = optim.Adam(self.online_net.parameters(), lr=learning_rate)
        self.loss_fn = nn.MSELoss()

        self.train_step_count = 0
        self.total_episodes = 0

    def update_target_network(self) -> None:
        """Hard copy weights from online network to target network."""
        self.target_net.load_state_dict(self.online_net.state_dict())

    def select_action(
        self,
        state: np.ndarray,
        evaluate: bool = False,
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Select action via epsilon-greedy policy with complete explainability telemetry.
        Returns: (action_idx, explanation_dict)
        """
        # Ensure state is tensor (1, state_dim)
        s_tensor = torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)

        with torch.no_grad():
            q_values_tensor = self.online_net(s_tensor)
            q_values = q_values_tensor.squeeze(0).cpu().numpy().tolist()

        best_action = int(np.argmax(q_values))

        # Epsilon-greedy decision
        is_random = False
        if not evaluate and random.random() < self.epsilon:
            action = random.randint(0, self.action_dim - 1)
            is_random = True
        else:
            action = best_action

        # Confidence calculation (Softmax temperature-scaled or margin)
        q_arr = np.array(q_values)
        exp_q = np.exp(q_arr - np.max(q_arr))
        probs = (exp_q / np.sum(exp_q)).tolist()
        confidence = float(probs[best_action])

        # Explanation object
        q_breakdown = {ACTION_NAMES[i]: round(float(q_values[i]), 4) for i in range(self.action_dim)}
        prob_breakdown = {ACTION_NAMES[i]: round(float(probs[i]), 4) for i in range(self.action_dim)}

        explanation = {
            "selected_action": action,
            "selected_action_name": ACTION_NAMES[action],
            "best_action": best_action,
            "best_action_name": ACTION_NAMES[best_action],
            "is_exploration": is_random,
            "epsilon": round(float(self.epsilon), 4),
            "confidence": round(confidence, 4),
            "q_values": q_breakdown,
            "probabilities": prob_breakdown,
            "state_dim": self.state_dim,
        }

        return action, explanation

    def train_step(self, replay_buffer: ExperienceReplayBuffer) -> Optional[float]:
        """
        Execute one Double DQN optimization step over a minibatch from replay buffer.
        Double DQN TD Target:
          a* = argmax_a Q_online(s', a)
          y  = r + gamma * Q_target(s', a*) * (1 - done)
        """
        if not replay_buffer.can_sample(self.batch_size):
            return None

        # Sample minibatch
        states, actions, rewards, next_states, dones = replay_buffer.sample(self.batch_size)

        b_states = torch.as_tensor(states, dtype=torch.float32, device=self.device)
        b_actions = torch.as_tensor(actions, dtype=torch.int64, device=self.device)
        b_rewards = torch.as_tensor(rewards, dtype=torch.float32, device=self.device)
        b_next_states = torch.as_tensor(next_states, dtype=torch.float32, device=self.device)
        b_dones = torch.as_tensor(dones, dtype=torch.float32, device=self.device)

        # 1. Predict Q(s, a) with online network
        current_q = self.online_net(b_states).gather(1, b_actions)

        # 2. Double DQN target computation:
        with torch.no_grad():
            # Select best action in s' using ONLINE network: a* = argmax Q_online(s', a)
            next_state_actions = self.online_net(b_next_states).argmax(dim=1, keepdim=True)
            # Evaluate Q-value of a* using TARGET network: Q_target(s', a*)
            next_q_values = self.target_net(b_next_states).gather(1, next_state_actions)
            # TD target: y = r + gamma * Q_target(s', a*) * (1 - done)
            target_q = b_rewards + (1.0 - b_dones) * self.gamma * next_q_values

        # 3. Loss & Backprop
        loss = self.loss_fn(current_q, target_q)

        self.optimizer.zero_grad()
        loss.backward()
        if self.grad_clip > 0:
            nn.utils.clip_grad_norm_(self.online_net.parameters(), max_norm=self.grad_clip)
        self.optimizer.step()

        # 4. Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        self.train_step_count += 1

        # 5. Periodic target network sync
        if self.train_step_count % self.target_update_freq == 0:
            self.update_target_network()

        return float(loss.item())

    def save_checkpoint(self, filepath: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Save network weights, optimizer state, and hyperparameter metadata."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        checkpoint = {
            "online_net_state": self.online_net.state_dict(),
            "target_net_state": self.target_net.state_dict(),
            "optimizer_state": self.optimizer.state_dict(),
            "epsilon": self.epsilon,
            "train_step_count": self.train_step_count,
            "total_episodes": self.total_episodes,
            "metadata": metadata or {},
        }
        torch.save(checkpoint, filepath)
        logger.info("Saved Double DQN checkpoint to %s", filepath)

    def load_checkpoint(self, filepath: str) -> Dict[str, Any]:
        """Load network weights, optimizer state, and metadata."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Checkpoint file not found: {filepath}")

        checkpoint = torch.load(filepath, map_location=self.device)
        self.online_net.load_state_dict(checkpoint["online_net_state"])
        self.target_net.load_state_dict(checkpoint["target_net_state"])
        if "optimizer_state" in checkpoint:
            self.optimizer.load_state_dict(checkpoint["optimizer_state"])
        self.epsilon = checkpoint.get("epsilon", self.epsilon_min)
        self.train_step_count = checkpoint.get("train_step_count", 0)
        self.total_episodes = checkpoint.get("total_episodes", 0)
        logger.info("Loaded Double DQN checkpoint from %s", filepath)
        return checkpoint.get("metadata", {})
