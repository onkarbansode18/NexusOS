"""
Nexus Double DQN — Gymnasium-Compatible RL Environment
========================================================
A pure in-memory simulation environment representing an operating system's
process and system resource lifecycle.

CRITICAL SAFETY & ISOLATION DIRECTIVE:
  - This module is 100% PURE SIMULATION.
  - NEVER calls psutil, os.kill, subprocess, or any OS execution APIs.
  - All metrics and process entities are simulated mathematical state models.
  - All logs and telemetry are stamped [SIMULATED].
"""

from __future__ import annotations

import enum
import random
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from app.rl.state_encoder import StateEncoder, STATE_DIM
from app.rl.reward_calculator import RewardCalculator, RewardBreakdown

logger = logging.getLogger("nexus.rl.environment")

ACTION_DIM: int = 7

ACTION_NAMES: List[str] = [
    "OBSERVE_ONLY",  # 0: Do nothing, monitor
    "RENICE",        # 1: Lower process priority (nice +10)
    "THROTTLE",      # 2: Maximum priority reduction (idle priority)
    "SUSPEND",       # 3: Freeze/pause process execution
    "RESUME",        # 4: Unpause suspended process
    "RESTART",       # 5: Graceful reboot of process
    "KILL",          # 6: Force kill process (blocked in auto mode)
]


class SimulationScenario(str, enum.Enum):
    CPU_INTENSIVE = "cpu_intensive"        # Process CPU ramps to 95%+
    MEMORY_LEAK = "memory_leak"            # Memory steadily climbs to OOM
    HIGH_DISK_IO = "high_disk_io"          # Disk utilization climbs to 95%+
    NORMAL_WORKLOAD = "normal_workload"    # Stable, healthy baseline
    MULTI_CONTENTION = "multi_contention"  # High contention across cores
    RECOVERY = "recovery"                  # Post-incident stabilization


@dataclass
class SimState:
    """
    Internal simulated telemetry state [SIMULATED].
    Pure numeric representation of OS & process state.
    """
    step_count: int = 0
    scenario: SimulationScenario = SimulationScenario.NORMAL_WORKLOAD

    # System metrics
    system_cpu_percent: float = 25.0
    system_ram_percent: float = 40.0
    disk_percent: float = 45.0
    net_utilization: float = 0.05

    # Process metrics
    process_cpu_percent: float = 12.0
    process_memory_mb: float = 150.0
    memory_growth_rate: float = 0.0
    anomaly_score: float = 0.0
    forecast_mins: Optional[float] = None
    process_priority: int = 0  # nice: 0 normal
    thread_count: int = 4
    historical_health: float = 1.0

    # RL state history
    previous_action: int = 0
    action_success_rate: float = 1.0

    # Process lifecycle flags
    is_suspended: bool = False
    is_terminated: bool = False
    consecutive_critical_steps: int = 0


class SpaceBox:
    """Gymnasium-compatible continuous Box space."""
    def __init__(self, low: float, high: float, shape: Tuple[int, ...], dtype: Any = np.float32) -> None:
        self.low = low
        self.high = high
        self.shape = shape
        self.dtype = dtype

    def sample(self) -> np.ndarray:
        return np.random.uniform(self.low, self.high, size=self.shape).astype(self.dtype)

    def contains(self, x: np.ndarray) -> bool:
        return x.shape == self.shape and np.all(x >= self.low) and np.all(x <= self.high)


class SpaceDiscrete:
    """Gymnasium-compatible discrete action space."""
    def __init__(self, n: int) -> None:
        self.n = n

    def sample(self) -> int:
        return random.randint(0, self.n - 1)

    def contains(self, x: int) -> bool:
        return 0 <= x < self.n


class NexusRLEnvironment:
    """
    [SIMULATED] Gymnasium-compatible environment for Double DQN agent training.
    Simulates multi-scenario OS workloads and process behavior without touching real hardware.
    """

    def __init__(
        self,
        max_steps_per_episode: int = 200,
        state_encoder: Optional[StateEncoder] = None,
        reward_calculator: Optional[RewardCalculator] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.max_steps = max_steps_per_episode
        self.encoder = state_encoder or StateEncoder()
        self.reward_calculator = reward_calculator or RewardCalculator()

        self.observation_space = SpaceBox(low=0.0, high=1.0, shape=(STATE_DIM,), dtype=np.float32)
        self.action_space = SpaceDiscrete(n=ACTION_DIM)

        self._rng = random.Random(seed)
        self.state: SimState = SimState()
        self._action_history: List[int] = []

    def reset(
        self,
        scenario: Optional[Union[SimulationScenario, str]] = None,
        seed: Optional[int] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Reset simulated environment to initial conditions for the chosen scenario.
        Returns: (initial_state_vector, info_dict)
        """
        if seed is not None:
            self._rng = random.Random(seed)
            np.random.seed(seed)

        if scenario is None:
            # Pick scenario uniformly if none specified
            scenario = self._rng.choice(list(SimulationScenario))
        elif isinstance(scenario, str):
            scenario = SimulationScenario(scenario)

        self._action_history = []
        self.state = self._initialize_scenario(scenario)

        obs = self.encoder.encode_from_sim(self.state)
        info = {
            "scenario": self.state.scenario.value,
            "step": 0,
            "sim_state": self.state,
            "status": "initialized",
        }
        return obs, info

    def _initialize_scenario(self, scenario: SimulationScenario) -> SimState:
        """Create fresh initial state per scenario [SIMULATED]."""
        st = SimState(scenario=scenario, step_count=0)

        if scenario == SimulationScenario.CPU_INTENSIVE:
            st.system_cpu_percent = 45.0 + self._rng.uniform(0.0, 10.0)
            st.system_ram_percent = 40.0 + self._rng.uniform(0.0, 5.0)
            st.disk_percent = 35.0
            st.process_cpu_percent = 40.0 + self._rng.uniform(0.0, 10.0)
            st.process_memory_mb = 220.0
            st.anomaly_score = 0.6
            st.forecast_mins = 12.0
            st.historical_health = 0.65

        elif scenario == SimulationScenario.MEMORY_LEAK:
            st.system_cpu_percent = 25.0
            st.system_ram_percent = 55.0
            st.disk_percent = 40.0
            st.process_cpu_percent = 15.0
            st.process_memory_mb = 250.0
            st.memory_growth_rate = 25.0  # +25MB per step
            st.anomaly_score = 0.5
            st.forecast_mins = 8.0
            st.historical_health = 0.7

        elif scenario == SimulationScenario.HIGH_DISK_IO:
            st.system_cpu_percent = 35.0
            st.system_ram_percent = 50.0
            st.disk_percent = 75.0 + self._rng.uniform(0.0, 5.0)
            st.process_cpu_percent = 20.0
            st.process_memory_mb = 180.0
            st.anomaly_score = 0.7
            st.forecast_mins = 15.0
            st.historical_health = 0.6

        elif scenario == SimulationScenario.NORMAL_WORKLOAD:
            st.system_cpu_percent = 20.0 + self._rng.uniform(0.0, 10.0)
            st.system_ram_percent = 35.0 + self._rng.uniform(0.0, 10.0)
            st.disk_percent = 40.0
            st.process_cpu_percent = 8.0 + self._rng.uniform(0.0, 5.0)
            st.process_memory_mb = 120.0
            st.memory_growth_rate = 0.0
            st.anomaly_score = 0.0
            st.forecast_mins = None
            st.historical_health = 1.0

        elif scenario == SimulationScenario.MULTI_CONTENTION:
            st.system_cpu_percent = 85.0 + self._rng.uniform(0.0, 5.0)
            st.system_ram_percent = 65.0
            st.disk_percent = 50.0
            st.process_cpu_percent = 60.0
            st.process_memory_mb = 450.0
            st.thread_count = 32
            st.anomaly_score = 0.8
            st.forecast_mins = 5.0
            st.historical_health = 0.4

        elif scenario == SimulationScenario.RECOVERY:
            st.system_cpu_percent = 30.0
            st.system_ram_percent = 42.0
            st.disk_percent = 40.0
            st.process_cpu_percent = 12.0
            st.process_memory_mb = 160.0
            st.anomaly_score = 0.2
            st.forecast_mins = None
            st.historical_health = 0.85

        return st

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """
        Execute one simulated action step [SIMULATED].
        Returns Gymnasium standard: (obs, reward, terminated, truncated, info)
        """
        if not self.action_space.contains(action):
            raise ValueError(f"Invalid action {action}. Must be in [0, {ACTION_DIM - 1}].")

        prev_state = SimState(**self.state.__dict__)
        self.state.step_count += 1
        self._action_history.append(action)

        # 1. Apply action consequences to simulated state
        blocked = False
        was_suspended = prev_state.is_suspended

        # Check safety blacklist rule in simulation: action 6 (KILL) blocked in automatic mode
        if action == 6:
            # Policy rule: Automatic KILL is strictly blocked by safety gate
            blocked = True

        self._apply_action(action, blocked=blocked)

        # 2. Advance natural scenario progression
        self._progress_scenario()

        # 3. Calculate reward
        reward = self.reward_calculator.calculate(
            prev_state=prev_state,
            action=action,
            next_state=self.state,
            outcome={"blocked": blocked, "was_suspended": was_suspended},
        )

        # 4. Check termination criteria
        terminated = False
        truncated = False

        if self.state.is_terminated:
            terminated = True
        elif self.state.process_memory_mb >= 7500.0:
            # Simulated Out-Of-Memory crash
            terminated = True
        elif self.state.consecutive_critical_steps >= 20:
            # Prolonged unresolved system lockup
            terminated = True
        elif self.state.step_count >= self.max_steps:
            truncated = True

        # Next observation vector
        next_obs = self.encoder.encode_from_sim(self.state, prev_action_idx=action)

        info = {
            "step": self.state.step_count,
            "scenario": self.state.scenario.value,
            "action": action,
            "action_name": ACTION_NAMES[action],
            "reward": reward,
            "blocked": blocked,
            "sim_state": self.state,
        }

        return next_obs, reward, terminated, truncated, info

    def _apply_action(self, action: int, blocked: bool = False) -> None:
        """Apply mathematical state shifts corresponding to the chosen action [SIMULATED]."""
        self.state.previous_action = action

        if blocked:
            # Action was blocked by safety gate; state does not transition
            return

        # 0: OBSERVE_ONLY
        if action == 0:
            # Passive monitoring, no state intervention
            pass

        # 1: RENICE (lower priority)
        elif action == 1:
            self.state.process_priority = min(self.state.process_priority + 10, 19)
            if not self.state.is_suspended:
                self.state.process_cpu_percent = max(self.state.process_cpu_percent - 22.0, 5.0)
                self.state.system_cpu_percent = max(self.state.system_cpu_percent - 15.0, 15.0)
                self.state.historical_health = min(self.state.historical_health + 0.15, 1.0)

        # 2: THROTTLE (set lowest priority / idle)
        elif action == 2:
            self.state.process_priority = 19
            if not self.state.is_suspended:
                self.state.process_cpu_percent = max(self.state.process_cpu_percent - 45.0, 2.0)
                self.state.system_cpu_percent = max(self.state.system_cpu_percent - 30.0, 12.0)
                self.state.historical_health = min(self.state.historical_health + 0.25, 1.0)

        # 3: SUSPEND
        elif action == 3:
            self.state.is_suspended = True
            self.state.process_cpu_percent = 0.0
            self.state.system_cpu_percent = max(self.state.system_cpu_percent - 35.0, 10.0)
            self.state.historical_health = max(self.state.historical_health - 0.05, 0.2)

        # 4: RESUME
        elif action == 4:
            if self.state.is_suspended:
                self.state.is_suspended = False
                self.state.process_cpu_percent = 15.0
                self.state.system_cpu_percent += 10.0
                self.state.historical_health = min(self.state.historical_health + 0.1, 1.0)

        # 5: RESTART
        elif action == 5:
            # Reset process state to clean startup baseline
            self.state.is_suspended = False
            self.state.process_cpu_percent = 10.0
            self.state.process_memory_mb = 90.0
            self.state.memory_growth_rate = 0.0
            self.state.anomaly_score = 0.0
            self.state.forecast_mins = None
            self.state.process_priority = 0
            self.state.system_cpu_percent = max(self.state.system_cpu_percent - 25.0, 15.0)
            self.state.historical_health = 0.95

        # 6: KILL (if not blocked)
        elif action == 6:
            self.state.is_terminated = True
            self.state.process_cpu_percent = 0.0
            self.state.process_memory_mb = 0.0
            self.state.memory_growth_rate = 0.0
            self.state.system_cpu_percent = max(self.state.system_cpu_percent - 40.0, 10.0)

    def _progress_scenario(self) -> None:
        """Simulate autonomous environment workload drift [SIMULATED]."""
        sc = self.state.scenario

        if sc == SimulationScenario.CPU_INTENSIVE:
            if not self.state.is_suspended and not self.state.is_terminated:
                # If priority is standard, CPU continues growing
                if self.state.process_priority <= 0:
                    drift = self._rng.uniform(3.0, 6.0)
                    self.state.process_cpu_percent = min(self.state.process_cpu_percent + drift, 98.0)
                    self.state.system_cpu_percent = min(self.state.system_cpu_percent + drift * 0.7, 99.0)
                    self.state.historical_health = max(self.state.historical_health - 0.05, 0.1)
                elif self.state.process_priority <= 10:
                    # Reniced: grows much slower
                    self.state.process_cpu_percent = min(self.state.process_cpu_percent + 0.5, 50.0)
                else:
                    # Throttled: stays low
                    self.state.process_cpu_percent = max(self.state.process_cpu_percent - 0.5, 3.0)

        elif sc == SimulationScenario.MEMORY_LEAK:
            if not self.state.is_suspended and not self.state.is_terminated:
                if self.state.memory_growth_rate > 0:
                    self.state.process_memory_mb += self.state.memory_growth_rate
                    self.state.system_ram_percent = min(
                        self.state.system_ram_percent + (self.state.memory_growth_rate / 8192.0) * 100.0,
                        99.0,
                    )
                    # Urgent forecast countdown
                    rem_mb = max(8000.0 - self.state.process_memory_mb, 0.0)
                    self.state.forecast_mins = round(rem_mb / (self.state.memory_growth_rate * 60.0 + 1e-5), 1)
                    self.state.anomaly_score = min(self.state.anomaly_score + 0.05, 1.0)
                    self.state.historical_health = max(self.state.historical_health - 0.04, 0.1)

        elif sc == SimulationScenario.HIGH_DISK_IO:
            if not self.state.is_terminated:
                if self.state.process_priority <= 0:
                    self.state.disk_percent = min(self.state.disk_percent + 1.5, 96.0)
                    self.state.historical_health = max(self.state.historical_health - 0.03, 0.2)
                else:
                    self.state.disk_percent = max(self.state.disk_percent - 1.0, 45.0)

        elif sc == SimulationScenario.NORMAL_WORKLOAD:
            # Minor random walk around baseline
            noise = self._rng.uniform(-2.0, 2.0)
            self.state.process_cpu_percent = np.clip(self.state.process_cpu_percent + noise, 4.0, 25.0)
            self.state.system_cpu_percent = np.clip(self.state.system_cpu_percent + noise * 0.5, 15.0, 35.0)
            self.state.historical_health = 1.0

        elif sc == SimulationScenario.MULTI_CONTENTION:
            if not self.state.is_suspended and not self.state.is_terminated:
                if self.state.process_priority <= 0:
                    self.state.system_cpu_percent = min(self.state.system_cpu_percent + 1.0, 98.0)
                else:
                    self.state.system_cpu_percent = max(self.state.system_cpu_percent - 3.0, 30.0)

        elif sc == SimulationScenario.RECOVERY:
            # Gradually decay towards nominal
            self.state.process_cpu_percent = max(self.state.process_cpu_percent * 0.9, 10.0)
            self.state.system_cpu_percent = max(self.state.system_cpu_percent * 0.9, 20.0)
            self.state.historical_health = min(self.state.historical_health + 0.05, 1.0)

        # Track consecutive critical steps
        if self.state.process_cpu_percent >= 85.0 or self.state.system_ram_percent >= 85.0:
            self.state.consecutive_critical_steps += 1
        else:
            self.state.consecutive_critical_steps = 0
