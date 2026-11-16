"""
Unit and Integration Tests for Nexus RL Environment & State Encoding (Phase 2)
==============================================================================
Tests verify:
  1. StateEncoder output shape, data type, bounds [0, 1], and NaN/Inf resilience
  2. RewardCalculator multi-objective rules, resource drops, stability bonus, safety penalty
  3. NexusRLEnvironment Gymnasium compatibility, scenario progression, and action dynamics
  4. Complete simulation isolation (no OS execution or psutil invocations)
"""

import sys
import unittest.mock
import numpy as np
import pytest

from app.rl.state_encoder import StateEncoder, STATE_DIM, FEATURE_NAMES
from app.rl.reward_calculator import RewardCalculator, RewardBreakdown
from app.rl.environment import (
    NexusRLEnvironment,
    SimulationScenario,
    SimState,
    ACTION_DIM,
    ACTION_NAMES,
)


# ── 1. StateEncoder Tests ───────────────────────────────────────────────────

def test_state_encoder_output_shape():
    """Verify state encoder produces exactly (14,) float32 vector."""
    encoder = StateEncoder()
    vec = encoder.encode()
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (STATE_DIM,)
    assert vec.dtype == np.float32
    assert len(FEATURE_NAMES) == STATE_DIM


def test_state_encoder_normalization_and_clamping():
    """Verify all 14 features are strictly within [0.0, 1.0], even with extreme inputs."""
    encoder = StateEncoder()
    # Test extreme high values
    vec_high = encoder.encode(
        system_cpu_percent=500.0,
        system_ram_percent=999.0,
        disk_percent=120.0,
        net_utilization=1000.0,
        process_cpu_percent=300.0,
        process_memory_mb=65536.0,
        memory_growth_rate=100.0,
        anomaly_score=5.0,
        forecast_mins=0.0,
        process_priority=100.0,
        thread_count=5000.0,
        historical_health=2.0,
        previous_action=10,
        action_success_rate=1.5,
    )
    assert np.all(vec_high >= 0.0)
    assert np.all(vec_high <= 1.0)

    # Test extreme negative values
    vec_low = encoder.encode(
        system_cpu_percent=-50.0,
        system_ram_percent=-10.0,
        disk_percent=-5.0,
        net_utilization=-100.0,
        process_cpu_percent=-20.0,
        process_memory_mb=-500.0,
        memory_growth_rate=-10.0,
        anomaly_score=-5.0,
        forecast_mins=-1.0,
        process_priority=-50.0,
        thread_count=-10.0,
        historical_health=-1.0,
        previous_action=-5,
        action_success_rate=-0.5,
    )
    assert np.all(vec_low >= 0.0)
    assert np.all(vec_low <= 1.0)


def test_state_encoder_no_nan_inf():
    """Verify NaN and Inf values are safely converted to clean float32 numbers in [0.0, 1.0]."""
    encoder = StateEncoder()
    vec = encoder.encode(
        system_cpu_percent=float("nan"),
        system_ram_percent=float("inf"),
        disk_percent=float("-inf"),
        net_utilization=float("nan"),
        process_cpu_percent=float("nan"),
        process_memory_mb=float("inf"),
        memory_growth_rate=float("nan"),
        anomaly_score=float("nan"),
        forecast_mins=float("inf"),
        process_priority=float("nan"),
        thread_count=float("nan"),
        historical_health=float("nan"),
        previous_action=0,
        action_success_rate=float("nan"),
    )
    assert not np.isnan(vec).any(), "State vector contains NaN!"
    assert not np.isinf(vec).any(), "State vector contains Inf!"
    assert np.all(vec >= 0.0)
    assert np.all(vec <= 1.0)


def test_state_encoder_handles_missing_values():
    """Verify passing None for all parameters uses safe defaults."""
    encoder = StateEncoder()
    vec = encoder.encode(
        system_cpu_percent=None,  # type: ignore
        system_ram_percent=None,  # type: ignore
        disk_percent=None,        # type: ignore
        net_utilization=None,     # type: ignore
        process_cpu_percent=None, # type: ignore
        process_memory_mb=None,   # type: ignore
        memory_growth_rate=None,  # type: ignore
        anomaly_score=None,       # type: ignore
        forecast_mins=None,
        process_priority=None,    # type: ignore
        thread_count=None,        # type: ignore
        historical_health=None,   # type: ignore
        previous_action=None,     # type: ignore
        action_success_rate=None, # type: ignore
    )
    assert vec.shape == (14,)
    assert not np.isnan(vec).any()
    assert np.all(vec >= 0.0)
    assert np.all(vec <= 1.0)


def test_state_encoder_from_sim():
    """Verify encoding from a SimState object returns a valid state vector."""
    encoder = StateEncoder()
    st = SimState(
        scenario=SimulationScenario.CPU_INTENSIVE,
        system_cpu_percent=78.5,
        system_ram_percent=60.0,
        disk_percent=45.0,
        net_utilization=0.2,
        process_cpu_percent=72.0,
        process_memory_mb=512.0,
        memory_growth_rate=1.5,
        anomaly_score=0.8,
        forecast_mins=4.0,
        process_priority=10,
        thread_count=16,
        historical_health=0.5,
        previous_action=1,
        action_success_rate=0.9,
    )
    vec = encoder.encode_from_sim(st)
    assert vec.shape == (14,)
    assert pytest.approx(vec[0], 0.01) == 0.785
    assert pytest.approx(vec[4], 0.01) == 0.720
    assert pytest.approx(vec[5], 0.01) == 512.0 / 8192.0
    assert pytest.approx(vec[12], 0.01) == 1.0 / 6.0


def test_state_encoder_from_real():
    """Verify encoding from mocked SystemMetrics and ProcessSnapshot."""
    encoder = StateEncoder()
    mock_metrics = unittest.mock.Mock()
    mock_metrics.cpu_percent = 65.0
    mock_metrics.ram_percent = 70.0
    mock_metrics.disk = unittest.mock.Mock(percent=55.0)
    mock_metrics.network = unittest.mock.Mock(delta_bytes_sent=1024 * 1024, delta_bytes_recv=2 * 1024 * 1024)

    mock_proc = unittest.mock.Mock()
    mock_proc.cpu_percent = 50.0
    mock_proc.memory_mb = 1024.0
    mock_proc.num_threads = 8

    vec = encoder.encode_from_real(
        system_metrics=mock_metrics,
        process_snapshot=mock_proc,
        anomaly_score=0.4,
        forecast_mins=8.0,
        memory_slope=2.0,
        prev_action_idx=2,
        action_success_rate=0.85,
        process_health_history=0.75,
        nice_value=0,
    )
    assert vec.shape == (14,)
    assert not np.isnan(vec).any()
    assert np.all(vec >= 0.0)
    assert np.all(vec <= 1.0)


# ── 2. RewardCalculator Tests ───────────────────────────────────────────────

def test_reward_calculator_healthy_observe():
    """Verify stability bonus (+2.0) for OBSERVE_ONLY when system is healthy."""
    calc = RewardCalculator()
    prev_st = SimState(process_cpu_percent=10.0, process_memory_mb=100.0, historical_health=1.0)
    next_st = SimState(process_cpu_percent=11.0, process_memory_mb=102.0, historical_health=1.0)
    reward = calc.calculate(prev_st, action=0, next_state=next_st)
    assert reward == 2.0


def test_reward_calculator_blocked_action():
    """Verify safety violation penalty (-50.0) for blocked action."""
    calc = RewardCalculator()
    prev_st = SimState(process_cpu_percent=90.0, process_memory_mb=2000.0)
    next_st = SimState(process_cpu_percent=90.0, process_memory_mb=2000.0)
    reward = calc.calculate(prev_st, action=6, next_state=next_st, outcome={"blocked": True})
    assert reward == -50.0


def test_reward_calculator_resource_drops():
    """Verify resource drop bonuses: >20% CPU (+10.0), >200MB RAM (+10.0)."""
    calc = RewardCalculator()
    # CPU dropped 30% after RENICE (action 1, cost -1.0)
    # prev_status is critical (CPU 90), next_status is warning (CPU 60) -> health +8.0
    # Expected: CPU drop (+10.0) + health (+8.0) - action cost (1.0) = +17.0
    prev_st = SimState(process_cpu_percent=90.0, process_memory_mb=100.0, historical_health=0.2)
    next_st = SimState(process_cpu_percent=60.0, process_memory_mb=100.0, historical_health=0.6)
    reward = calc.calculate(prev_st, action=1, next_state=next_st)
    assert reward == 17.0

    # RAM drop >200MB (+10.0) after RESTART (action 5, cost -8.0)
    # CPU remains constant at 20.0 (no cpu drop bonus)
    # prev is critical (RAM 7000MB), next is healthy (RAM 100MB) -> health +15.0
    # Expected: RAM drop (+10.0) + health (+15.0) - action cost (8.0) = +17.0
    prev_ram = SimState(process_cpu_percent=20.0, process_memory_mb=7000.0, historical_health=0.2)
    next_ram = SimState(process_cpu_percent=20.0, process_memory_mb=100.0, historical_health=0.95)
    reward_ram = calc.calculate(prev_ram, action=5, next_state=next_ram)
    assert reward_ram == 17.0


def test_reward_calculator_inaction_penalty():
    """Verify inaction penalty (-0.5) when observing during critical state."""
    calc = RewardCalculator()
    prev_st = SimState(process_cpu_percent=92.0, process_memory_mb=200.0, historical_health=0.2)
    next_st = SimState(process_cpu_percent=94.0, process_memory_mb=200.0, historical_health=0.2)
    reward = calc.calculate(prev_st, action=0, next_state=next_st)
    assert reward == -0.5


# ── 3. NexusRLEnvironment Tests ─────────────────────────────────────────────

def test_environment_reset_all_scenarios():
    """Verify reset() succeeds and returns valid shapes for all 6 scenarios."""
    env = NexusRLEnvironment()
    for sc in SimulationScenario:
        obs, info = env.reset(scenario=sc, seed=42)
        assert isinstance(obs, np.ndarray)
        assert obs.shape == (STATE_DIM,)
        assert np.all(obs >= 0.0) and np.all(obs <= 1.0)
        assert info["scenario"] == sc.value
        assert info["step"] == 0
        assert env.state.scenario == sc


def test_environment_step_observe():
    """Verify step with OBSERVE_ONLY advances step count and returns standard 5-tuple."""
    env = NexusRLEnvironment()
    env.reset(scenario=SimulationScenario.NORMAL_WORKLOAD, seed=123)
    obs, reward, term, trunc, info = env.step(action=0)
    assert obs.shape == (STATE_DIM,)
    assert isinstance(reward, float)
    assert isinstance(term, bool)
    assert isinstance(trunc, bool)
    assert info["step"] == 1
    assert info["action"] == 0
    assert info["action_name"] == "OBSERVE_ONLY"


def test_environment_step_all_actions():
    """Verify all 7 discrete actions execute safely."""
    env = NexusRLEnvironment()
    for act in range(ACTION_DIM):
        env.reset(scenario=SimulationScenario.CPU_INTENSIVE, seed=10 + act)
        obs, reward, term, trunc, info = env.step(action=act)
        assert obs.shape == (STATE_DIM,)
        assert info["action"] == act
        assert info["action_name"] == ACTION_NAMES[act]


def test_environment_invalid_action():
    """Verify out-of-range action raises ValueError."""
    env = NexusRLEnvironment()
    env.reset()
    with pytest.raises(ValueError):
        env.step(99)
    with pytest.raises(ValueError):
        env.step(-1)


def test_environment_done_condition_max_steps():
    """Verify truncation occurs when max_steps is reached."""
    env = NexusRLEnvironment(max_steps_per_episode=5)
    env.reset(scenario=SimulationScenario.NORMAL_WORKLOAD, seed=42)
    for _ in range(4):
        _, _, term, trunc, _ = env.step(0)
        assert not term
        assert not trunc
    _, _, term, trunc, _ = env.step(0)
    assert trunc is True


def test_scenario_cpu_intensive_dynamics():
    """Verify CPU grows on OBSERVE and drops significantly after THROTTLE."""
    env = NexusRLEnvironment()
    env.reset(scenario=SimulationScenario.CPU_INTENSIVE, seed=42)

    # 3 steps of observe -> CPU should rise
    initial_cpu = env.state.process_cpu_percent
    for _ in range(3):
        env.step(0)
    observed_cpu = env.state.process_cpu_percent
    assert observed_cpu > initial_cpu

    # 1 step of THROTTLE (action 2) -> CPU should drop significantly
    env.step(2)
    throttled_cpu = env.state.process_cpu_percent
    assert throttled_cpu < observed_cpu


def test_scenario_memory_leak_dynamics():
    """Verify memory leak persists under RENICE, but RESTART clears memory."""
    env = NexusRLEnvironment()
    env.reset(scenario=SimulationScenario.MEMORY_LEAK, seed=42)

    initial_mem = env.state.process_memory_mb
    # Step with RENICE (action 1) -> does NOT fix memory leak
    env.step(1)
    leaking_mem = env.state.process_memory_mb
    assert leaking_mem > initial_mem

    # Step with RESTART (action 5) -> resets memory to clean startup
    env.step(5)
    restarted_mem = env.state.process_memory_mb
    assert restarted_mem < leaking_mem
    assert restarted_mem < 150.0


def test_simulation_isolation():
    """
    STRICT SAFETY TEST:
    Assert no real OS process APIs (psutil, os.kill, subprocess) are invoked during simulation.
    """
    env = NexusRLEnvironment()
    env.reset(scenario=SimulationScenario.MULTI_CONTENTION)

    # Ensure psutil and subprocess are not called
    with unittest.mock.patch("psutil.cpu_percent") as mock_cpu, \
         unittest.mock.patch("psutil.Process") as mock_proc, \
         unittest.mock.patch("os.kill") as mock_kill, \
         unittest.mock.patch("subprocess.run") as mock_sub:

        for act in range(ACTION_DIM):
            env.step(act)

        assert mock_cpu.call_count == 0, "psutil.cpu_percent was called during pure simulation!"
        assert mock_proc.call_count == 0, "psutil.Process was called during pure simulation!"
        assert mock_kill.call_count == 0, "os.kill was called during pure simulation!"
        assert mock_sub.call_count == 0, "subprocess was called during pure simulation!"
