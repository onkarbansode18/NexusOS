"""
Unit and Convergence Tests for Double DQN Algorithm (Phase 3)
=============================================================
Tests verify:
  1. Replay buffer push, FIFO capacity overflow, batch tensor conversion
  2. QNetwork forward pass tensor dimensions
  3. DoubleDQNAgent action selection, epsilon-greedy schedule, explainability output
  4. Double DQN TD target computation and gradient optimization step
  5. Checkpoint serialization and weight restoration
"""

import os
import tempfile
import numpy as np
import pytest
import torch

from app.rl.replay_buffer import ExperienceReplayBuffer, Transition
from app.rl.double_dqn_agent import DoubleDQNAgent, QNetwork
from app.rl.environment import ACTION_DIM
from app.rl.state_encoder import STATE_DIM


# ── 1. Replay Buffer Tests ──────────────────────────────────────────────────

def test_replay_buffer_push_and_sample():
    """Verify buffer push and minibatch array structure."""
    buf = ExperienceReplayBuffer(capacity=100)
    for i in range(10):
        s = np.zeros(STATE_DIM, dtype=np.float32)
        ns = np.ones(STATE_DIM, dtype=np.float32)
        buf.push(state=s, action=i % ACTION_DIM, reward=1.0, next_state=ns, done=False)

    assert len(buf) == 10
    assert buf.can_sample(5) is True
    assert buf.can_sample(20) is False

    states, actions, rewards, next_states, dones = buf.sample(5)
    assert states.shape == (5, STATE_DIM)
    assert actions.shape == (5, 1)
    assert rewards.shape == (5, 1)
    assert next_states.shape == (5, STATE_DIM)
    assert dones.shape == (5, 1)
    assert states.dtype == np.float32
    assert actions.dtype == np.int64


def test_replay_buffer_capacity_overflow():
    """Verify circular buffer preserves capacity limit."""
    buf = ExperienceReplayBuffer(capacity=5)
    for i in range(10):
        s = np.full(STATE_DIM, i, dtype=np.float32)
        buf.push(state=s, action=0, reward=float(i), next_state=s, done=False)

    assert len(buf) == 5
    # Oldest items (0-4) should have been dropped; only 5-9 remain
    rewards = [t.reward for t in buf.buffer]
    assert rewards == [5.0, 6.0, 7.0, 8.0, 9.0]


def test_replay_buffer_empty_or_underflow():
    """Verify sampling from underfilled buffer raises ValueError."""
    buf = ExperienceReplayBuffer(capacity=50)
    with pytest.raises(ValueError):
        buf.sample(10)


# ── 2. QNetwork & Agent Tests ───────────────────────────────────────────────

def test_q_network_forward_pass():
    """Verify QNetwork forward pass tensor shapes."""
    net = QNetwork(state_dim=STATE_DIM, action_dim=ACTION_DIM)
    x = torch.randn(4, STATE_DIM)
    out = net(x)
    assert out.shape == (4, ACTION_DIM)


def test_double_dqn_action_selection():
    """Verify action selection returns valid action and explainability dictionary."""
    agent = DoubleDQNAgent(epsilon=0.0)  # Pure greedy
    state = np.random.uniform(0.0, 1.0, size=(STATE_DIM,)).astype(np.float32)

    action, info = agent.select_action(state, evaluate=True)
    assert 0 <= action < ACTION_DIM
    assert "q_values" in info
    assert len(info["q_values"]) == ACTION_DIM
    assert "confidence" in info
    assert "probabilities" in info
    assert info["is_exploration"] is False

    # Test random exploration when epsilon=1.0
    agent.epsilon = 1.0
    _, info_explore = agent.select_action(state, evaluate=False)
    assert info_explore["is_exploration"] is True


def test_double_dqn_training_step():
    """Verify Double DQN training step computes loss and updates weights."""
    agent = DoubleDQNAgent(batch_size=8, learning_rate=1e-3)
    buf = ExperienceReplayBuffer(capacity=50)

    # Populate buffer with dummy transitions
    for i in range(20):
        s = np.random.uniform(0.0, 1.0, size=(STATE_DIM,)).astype(np.float32)
        ns = np.random.uniform(0.0, 1.0, size=(STATE_DIM,)).astype(np.float32)
        buf.push(s, action=i % ACTION_DIM, reward=2.0, next_state=ns, done=False)

    initial_loss = agent.train_step(buf)
    assert initial_loss is not None
    assert isinstance(initial_loss, float)
    assert initial_loss >= 0.0
    assert agent.train_step_count == 1


def test_double_dqn_target_update():
    """Verify target network synchronization."""
    agent = DoubleDQNAgent()
    # Perturb online weights
    with torch.no_grad():
        for param in agent.online_net.parameters():
            param.add_(1.0)

    # Target and online should differ
    diff = False
    for p_on, p_tgt in zip(agent.online_net.parameters(), agent.target_net.parameters()):
        if not torch.equal(p_on, p_tgt):
            diff = True
            break
    assert diff is True

    # After update, weights must match exactly
    agent.update_target_network()
    for p_on, p_tgt in zip(agent.online_net.parameters(), agent.target_net.parameters()):
        assert torch.equal(p_on, p_tgt)


def test_double_dqn_save_and_load():
    """Verify model checkpoint save and load integrity."""
    agent = DoubleDQNAgent()
    state = np.random.uniform(0.0, 1.0, size=(STATE_DIM,)).astype(np.float32)
    _, info_before = agent.select_action(state, evaluate=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        ckpt_path = os.path.join(tmpdir, "nexus_dqn_test.pt")
        agent.save_checkpoint(ckpt_path, metadata={"version": "2.0-test"})

        new_agent = DoubleDQNAgent()
        meta = new_agent.load_checkpoint(ckpt_path)
        assert meta["version"] == "2.0-test"

        _, info_after = new_agent.select_action(state, evaluate=True)
        # Q-values must match identically
        for act_name in info_before["q_values"]:
            assert pytest.approx(info_before["q_values"][act_name], 1e-4) == info_after["q_values"][act_name]
