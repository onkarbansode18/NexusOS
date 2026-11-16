"""
Nexus Double DQN — Reward Calculator
======================================
Calculates multi-objective rewards for RL actions based on:
  1. Resource improvement (CPU & RAM drops)
  2. Health status transitions (critical -> healthy/warning)
  3. Action cost penalties (discouraging heavy/disruptive actions)
  4. Stability bonus (rewarding observe-only when healthy)
  5. Safety violation penalties (-50.0 for blocked/blacklisted actions)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("nexus.rl.reward_calculator")


@dataclass
class RewardBreakdown:
    total_reward: float
    resource_cpu_reward: float = 0.0
    resource_ram_reward: float = 0.0
    health_transition_reward: float = 0.0
    action_cost_penalty: float = 0.0
    stability_bonus: float = 0.0
    safety_penalty: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class RewardCalculator:
    """
    Computes scalar reward for state transitions (s, a, s').
    """

    # Action constants
    ACTION_OBSERVE = 0
    ACTION_RENICE = 1
    ACTION_THROTTLE = 2
    ACTION_SUSPEND = 3
    ACTION_RESUME = 4
    ACTION_RESTART = 5
    ACTION_KILL = 6

    def __init__(
        self,
        cpu_crit_threshold: float = 85.0,
        cpu_warn_threshold: float = 65.0,
        ram_crit_threshold: float = 85.0,
        ram_warn_threshold: float = 65.0,
    ) -> None:
        self.cpu_crit_threshold = cpu_crit_threshold
        self.cpu_warn_threshold = cpu_warn_threshold
        self.ram_crit_threshold = ram_crit_threshold
        self.ram_warn_threshold = ram_warn_threshold

    def _determine_health(self, cpu: float, ram: float, health_score: Optional[float] = None) -> str:
        """Categorize into 'critical', 'warning', or 'healthy'."""
        if health_score is not None and health_score <= 0.35:
            return "critical"
        if cpu >= self.cpu_crit_threshold or ram >= self.ram_crit_threshold:
            return "critical"
        if health_score is not None and health_score <= 0.65:
            return "warning"
        if cpu >= self.cpu_warn_threshold or ram >= self.ram_warn_threshold:
            return "warning"
        return "healthy"

    def compute_breakdown(
        self,
        prev_cpu: float,
        next_cpu: float,
        prev_ram_mb: float,
        next_ram_mb: float,
        action: int,
        prev_health: float = 1.0,
        next_health: float = 1.0,
        blocked: bool = False,
        was_suspended: bool = False,
    ) -> RewardBreakdown:
        """
        Compute granular reward components.
        """
        if blocked:
            return RewardBreakdown(
                total_reward=-50.0,
                safety_penalty=-50.0,
                details={"reason": "Action blocked by safety policy or blacklist"},
            )

        # 1. Resource improvement
        r_cpu = 0.0
        cpu_drop = prev_cpu - next_cpu
        if cpu_drop > 20.0:
            r_cpu = 10.0
        elif cpu_drop >= 10.0:
            r_cpu = 5.0
        elif cpu_drop >= 5.0:
            r_cpu = 3.0

        r_ram = 0.0
        ram_drop = prev_ram_mb - next_ram_mb
        if ram_drop > 200.0:
            r_ram = 10.0
        elif ram_drop >= 100.0:
            r_ram = 5.0

        # 2. Health status transitions
        prev_status = self._determine_health(prev_cpu, (prev_ram_mb / 8192.0) * 100.0, prev_health)
        next_status = self._determine_health(next_cpu, (next_ram_mb / 8192.0) * 100.0, next_health)

        r_health = 0.0
        if prev_status == "critical":
            if next_status == "healthy":
                r_health += 15.0
            elif next_status == "warning":
                r_health += 8.0
        elif prev_status == "warning" and next_status == "healthy":
            r_health += 5.0

        # Health worsened penalty
        if (prev_status == "healthy" and next_status in ("warning", "critical")) or (
            prev_status == "warning" and next_status == "critical"
        ):
            r_health -= 5.0

        # 3. Action cost / penalty & stability bonus
        r_cost = 0.0
        r_stability = 0.0

        if action == self.ACTION_OBSERVE:
            if prev_status == "critical":
                # Inaction penalty when critical
                r_cost = -0.5
            elif prev_status == "healthy":
                # Correct observe when already healthy
                r_stability = 2.0
        elif action == self.ACTION_RENICE:
            r_cost = -1.0
        elif action == self.ACTION_THROTTLE:
            r_cost = -2.0
        elif action == self.ACTION_SUSPEND:
            r_cost = -5.0
        elif action == self.ACTION_RESUME:
            if not was_suspended:
                # Resuming non-suspended process penalty
                r_cost = -3.0
            else:
                r_cost = -1.0
        elif action == self.ACTION_RESTART:
            r_cost = -8.0
        elif action == self.ACTION_KILL:
            r_cost = -20.0

        total = r_cpu + r_ram + r_health + r_cost + r_stability
        return RewardBreakdown(
            total_reward=round(total, 2),
            resource_cpu_reward=r_cpu,
            resource_ram_reward=r_ram,
            health_transition_reward=r_health,
            action_cost_penalty=r_cost,
            stability_bonus=r_stability,
            safety_penalty=0.0,
            details={
                "prev_status": prev_status,
                "next_status": next_status,
                "cpu_drop": round(cpu_drop, 2),
                "ram_drop_mb": round(ram_drop, 2),
            },
        )

    def calculate(
        self,
        prev_state: Any,
        action: int,
        next_state: Any,
        outcome: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Calculates scalar reward. Handles both vector states and SimState objects.
        """
        outcome = outcome or {}
        blocked = outcome.get("blocked", False)
        was_suspended = outcome.get("was_suspended", False)

        # Handle SimState
        if hasattr(prev_state, "process_cpu_percent") and hasattr(next_state, "process_cpu_percent"):
            bd = self.compute_breakdown(
                prev_cpu=getattr(prev_state, "process_cpu_percent", 0.0),
                next_cpu=getattr(next_state, "process_cpu_percent", 0.0),
                prev_ram_mb=getattr(prev_state, "process_memory_mb", 0.0),
                next_ram_mb=getattr(next_state, "process_memory_mb", 0.0),
                action=action,
                prev_health=getattr(prev_state, "historical_health", 1.0),
                next_health=getattr(next_state, "historical_health", 1.0),
                blocked=blocked,
                was_suspended=getattr(prev_state, "is_suspended", was_suspended),
            )
            return bd.total_reward

        # Handle 14-dim numpy array
        # Index 4 is process_cpu_percent (0-1 -> * 100)
        # Index 5 is process_memory_mb (0-1 -> * 8192)
        # Index 11 is historical_health
        if hasattr(prev_state, "__len__") and len(prev_state) >= 14:
            prev_cpu = float(prev_state[4]) * 100.0
            next_cpu = float(next_state[4]) * 100.0
            prev_ram = float(prev_state[5]) * 8192.0
            next_ram = float(next_state[5]) * 8192.0
            prev_health = float(prev_state[11])
            next_health = float(next_state[11])

            bd = self.compute_breakdown(
                prev_cpu=prev_cpu,
                next_cpu=next_cpu,
                prev_ram_mb=prev_ram,
                next_ram_mb=next_ram,
                action=action,
                prev_health=prev_health,
                next_health=next_health,
                blocked=blocked,
                was_suspended=was_suspended,
            )
            return bd.total_reward

        # Fallback default
        return 0.0
