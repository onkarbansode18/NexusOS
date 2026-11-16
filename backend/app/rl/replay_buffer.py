"""
Nexus Double DQN — Experience Replay Buffer
============================================
Thread-safe circular experience replay buffer for uniform batch sampling
during Double DQN training.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import numpy as np


class Transition(NamedTuple):
    state: np.ndarray        # shape (14,), dtype float32
    action: int              # discrete action index 0..6
    reward: float            # scalar reward
    next_state: np.ndarray   # shape (14,), dtype float32
    done: bool               # episode termination flag


class ExperienceReplayBuffer:
    """
    Circular replay memory with uniform random sampling.
    """

    def __init__(self, capacity: int = 50000) -> None:
        if capacity <= 0:
            raise ValueError(f"Capacity must be positive, got {capacity}")
        self.capacity = capacity
        self.buffer: deque[Transition] = deque(maxlen=capacity)

    def push(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> None:
        """Add a transition to the replay memory."""
        # Ensure correct array types
        s = np.asarray(state, dtype=np.float32)
        ns = np.asarray(next_state, dtype=np.float32)
        trans = Transition(state=s, action=int(action), reward=float(reward), next_state=ns, done=bool(done))
        self.buffer.append(trans)

    def sample(self, batch_size: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Sample a random batch of transitions.
        Returns:
          states: (batch_size, 14) float32
          actions: (batch_size, 1) int64
          rewards: (batch_size, 1) float32
          next_states: (batch_size, 14) float32
          dones: (batch_size, 1) float32
        """
        if len(self.buffer) < batch_size:
            raise ValueError(
                f"Cannot sample batch of size {batch_size} from buffer with {len(self.buffer)} samples."
            )

        batch = random.sample(self.buffer, batch_size)

        states = np.array([t.state for t in batch], dtype=np.float32)
        actions = np.array([t.action for t in batch], dtype=np.int64).reshape(-1, 1)
        rewards = np.array([t.reward for t in batch], dtype=np.float32).reshape(-1, 1)
        next_states = np.array([t.next_state for t in batch], dtype=np.float32)
        dones = np.array([t.done for t in batch], dtype=np.float32).reshape(-1, 1)

        return states, actions, rewards, next_states, dones

    def can_sample(self, batch_size: int) -> bool:
        """Check if buffer has enough samples for training."""
        return len(self.buffer) >= batch_size

    def __len__(self) -> int:
        return len(self.buffer)

    def clear(self) -> None:
        self.buffer.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """Compute buffer telemetry."""
        count = len(self.buffer)
        if count == 0:
            return {"size": 0, "capacity": self.capacity, "fill_percent": 0.0, "avg_reward": 0.0}

        avg_r = sum(t.reward for t in self.buffer) / count
        action_counts: Dict[int, int] = {}
        for t in self.buffer:
            action_counts[t.action] = action_counts.get(t.action, 0) + 1

        return {
            "size": count,
            "capacity": self.capacity,
            "fill_percent": round((count / self.capacity) * 100.0, 2),
            "avg_reward": round(avg_r, 3),
            "action_distribution": action_counts,
        }
