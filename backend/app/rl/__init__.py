"""
Nexus Reinforcement Learning (Double DQN) Package
===================================================
Provides adaptive self-healing through Double Deep Q-Network reinforcement learning.
All simulation modules are strictly isolated from real OS processes.
"""

from app.rl.state_encoder import StateEncoder, STATE_DIM, FEATURE_NAMES
from app.rl.reward_calculator import RewardCalculator, RewardBreakdown
from app.rl.environment import (
    NexusRLEnvironment,
    SimulationScenario,
    SimState,
    ACTION_DIM,
    ACTION_NAMES,
    SpaceBox,
    SpaceDiscrete,
)

__all__ = [
    "NexusRLEnvironment",
    "SimulationScenario",
    "SimState",
    "ACTION_DIM",
    "ACTION_NAMES",
    "SpaceBox",
    "SpaceDiscrete",
    "StateEncoder",
    "STATE_DIM",
    "FEATURE_NAMES",
    "RewardCalculator",
    "RewardBreakdown",
]
