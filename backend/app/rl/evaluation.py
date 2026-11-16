"""
Nexus Double DQN — Multi-Policy Evaluator
===========================================
Compares Double DQN Agent against Heuristic Rule-Based and Random Baseline policies
across all simulated scenarios. Produces structured comparison metrics for the UI.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.rl.environment import NexusRLEnvironment, SimulationScenario, ACTION_DIM, ACTION_NAMES
from app.rl.double_dqn_agent import DoubleDQNAgent

logger = logging.getLogger("nexus.rl.evaluation")


@dataclass
class PolicyBenchmark:
    policy_name: str
    avg_reward: float
    success_rate: float            # 0.0 - 100.0 %
    avg_steps: float
    recovery_rate: float           # 0.0 - 100.0 %
    invasive_action_rate: float    # % RESTART / KILL
    safety_violations: int
    episodes_evaluated: int
    scenario_breakdown: Dict[str, Dict[str, float]] = field(default_factory=dict)


class Evaluator:
    """
    Benchmarking suite for comparing autonomous healing policies.
    """

    def __init__(self, env: Optional[NexusRLEnvironment] = None) -> None:
        self.env = env or NexusRLEnvironment(max_steps_per_episode=100)

    def evaluate_all(
        self,
        agent: DoubleDQNAgent,
        episodes_per_scenario: int = 5,
    ) -> Dict[str, Any]:
        """
        Evaluate Random, Rule-Based, and Double DQN policies.
        Returns full comparative benchmark dictionary.
        """
        scenarios = list(SimulationScenario)

        dqn_bench = self._evaluate_dqn(agent, scenarios, episodes_per_scenario)
        rule_bench = self._evaluate_rule_based(scenarios, episodes_per_scenario)
        rand_bench = self._evaluate_random(scenarios, episodes_per_scenario)

        # Compute improvements
        dqn_reward = dqn_bench.avg_reward
        rule_reward = rule_bench.avg_reward
        reward_delta = round(dqn_reward - rule_reward, 2)
        success_delta = round(dqn_bench.success_rate - rule_bench.success_rate, 2)

        return {
            "summary": {
                "dqn_vs_rules_reward_delta": reward_delta,
                "dqn_vs_rules_success_delta": success_delta,
                "best_policy": "Double DQN" if dqn_reward >= rule_reward else "Rule-Based",
                "episodes_per_scenario": episodes_per_scenario,
                "total_episodes": len(scenarios) * episodes_per_scenario * 3,
            },
            "policies": {
                "double_dqn": dqn_bench.__dict__,
                "rule_based": rule_bench.__dict__,
                "random": rand_bench.__dict__,
            },
        }

    def _evaluate_dqn(
        self,
        agent: DoubleDQNAgent,
        scenarios: List[SimulationScenario],
        episodes_per_scenario: int,
    ) -> PolicyBenchmark:
        """Evaluate Double DQN in pure exploitation mode (evaluate=True)."""
        rewards: List[float] = []
        steps_list: List[int] = []
        successes: int = 0
        invasive_count: int = 0
        total_actions: int = 0
        safety_violations: int = 0
        sc_data: Dict[str, Dict[str, float]] = {}

        for sc in scenarios:
            sc_rewards: List[float] = []
            sc_success = 0
            for _ in range(episodes_per_scenario):
                obs, _ = self.env.reset(scenario=sc)
                term = False
                trunc = False
                ep_r = 0.0
                st = 0

                while not (term or trunc):
                    st += 1
                    total_actions += 1
                    action, _ = agent.select_action(obs, evaluate=True)
                    if action in (5, 6):  # RESTART or KILL
                        invasive_count += 1

                    obs, r, term, trunc, info = self.env.step(action)
                    if info.get("blocked", False):
                        safety_violations += 1
                    ep_r += r

                sc_rewards.append(ep_r)
                rewards.append(ep_r)
                steps_list.append(st)
                if ep_r > 10.0 or getattr(self.env.state, "historical_health", 0.0) >= 0.75:
                    successes += 1
                    sc_success += 1

            sc_data[sc.value] = {
                "avg_reward": round(float(np.mean(sc_rewards)), 2),
                "success_rate": round((sc_success / episodes_per_scenario) * 100.0, 1),
            }

        total_eps = len(scenarios) * episodes_per_scenario
        return PolicyBenchmark(
            policy_name="Double DQN",
            avg_reward=round(float(np.mean(rewards)), 2),
            success_rate=round((successes / total_eps) * 100.0, 1),
            avg_steps=round(float(np.mean(steps_list)), 1),
            recovery_rate=round((successes / total_eps) * 100.0, 1),
            invasive_action_rate=round((invasive_count / max(total_actions, 1)) * 100.0, 1),
            safety_violations=safety_violations,
            episodes_evaluated=total_eps,
            scenario_breakdown=sc_data,
        )

    def _evaluate_rule_based(
        self,
        scenarios: List[SimulationScenario],
        episodes_per_scenario: int,
    ) -> PolicyBenchmark:
        """Evaluate deterministic heuristic rules."""
        rewards: List[float] = []
        steps_list: List[int] = []
        successes: int = 0
        invasive_count: int = 0
        total_actions: int = 0
        safety_violations: int = 0
        sc_data: Dict[str, Dict[str, float]] = {}

        for sc in scenarios:
            sc_rewards: List[float] = []
            sc_success = 0
            for _ in range(episodes_per_scenario):
                obs, _ = self.env.reset(scenario=sc)
                term = False
                trunc = False
                ep_r = 0.0
                st = 0

                while not (term or trunc):
                    st += 1
                    total_actions += 1

                    # Rule-based policy logic
                    st_obj = self.env.state
                    if st_obj.memory_growth_rate > 10.0 and st_obj.process_memory_mb > 1500.0:
                        action = 5  # RESTART on severe memory leak
                    elif st_obj.process_cpu_percent >= 85.0:
                        action = 2  # THROTTLE
                    elif st_obj.process_cpu_percent >= 65.0:
                        action = 1  # RENICE
                    elif st_obj.disk_percent >= 85.0:
                        action = 1  # RENICE
                    else:
                        action = 0  # OBSERVE_ONLY

                    if action in (5, 6):
                        invasive_count += 1

                    obs, r, term, trunc, info = self.env.step(action)
                    if info.get("blocked", False):
                        safety_violations += 1
                    ep_r += r

                sc_rewards.append(ep_r)
                rewards.append(ep_r)
                steps_list.append(st)
                if ep_r > 10.0 or getattr(self.env.state, "historical_health", 0.0) >= 0.75:
                    successes += 1
                    sc_success += 1

            sc_data[sc.value] = {
                "avg_reward": round(float(np.mean(sc_rewards)), 2),
                "success_rate": round((sc_success / episodes_per_scenario) * 100.0, 1),
            }

        total_eps = len(scenarios) * episodes_per_scenario
        return PolicyBenchmark(
            policy_name="Rule-Based Heuristic",
            avg_reward=round(float(np.mean(rewards)), 2),
            success_rate=round((successes / total_eps) * 100.0, 1),
            avg_steps=round(float(np.mean(steps_list)), 1),
            recovery_rate=round((successes / total_eps) * 100.0, 1),
            invasive_action_rate=round((invasive_count / max(total_actions, 1)) * 100.0, 1),
            safety_violations=safety_violations,
            episodes_evaluated=total_eps,
            scenario_breakdown=sc_data,
        )

    def _evaluate_random(
        self,
        scenarios: List[SimulationScenario],
        episodes_per_scenario: int,
    ) -> PolicyBenchmark:
        """Evaluate uniform random action selection."""
        rewards: List[float] = []
        steps_list: List[int] = []
        successes: int = 0
        invasive_count: int = 0
        total_actions: int = 0
        safety_violations: int = 0
        sc_data: Dict[str, Dict[str, float]] = {}

        for sc in scenarios:
            sc_rewards: List[float] = []
            sc_success = 0
            for _ in range(episodes_per_scenario):
                obs, _ = self.env.reset(scenario=sc)
                term = False
                trunc = False
                ep_r = 0.0
                st = 0

                while not (term or trunc):
                    st += 1
                    total_actions += 1
                    # Random in [0..6]
                    action = random.randint(0, ACTION_DIM - 1)
                    if action in (5, 6):
                        invasive_count += 1

                    obs, r, term, trunc, info = self.env.step(action)
                    if info.get("blocked", False):
                        safety_violations += 1
                    ep_r += r

                sc_rewards.append(ep_r)
                rewards.append(ep_r)
                steps_list.append(st)
                if ep_r > 10.0 or getattr(self.env.state, "historical_health", 0.0) >= 0.75:
                    successes += 1
                    sc_success += 1

            sc_data[sc.value] = {
                "avg_reward": round(float(np.mean(sc_rewards)), 2),
                "success_rate": round((sc_success / episodes_per_scenario) * 100.0, 1),
            }

        total_eps = len(scenarios) * episodes_per_scenario
        return PolicyBenchmark(
            policy_name="Random Policy",
            avg_reward=round(float(np.mean(rewards)), 2),
            success_rate=round((successes / total_eps) * 100.0, 1),
            avg_steps=round(float(np.mean(steps_list)), 1),
            recovery_rate=round((successes / total_eps) * 100.0, 1),
            invasive_action_rate=round((invasive_count / max(total_actions, 1)) * 100.0, 1),
            safety_violations=safety_violations,
            episodes_evaluated=total_eps,
            scenario_breakdown=sc_data,
        )
