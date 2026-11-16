"""
Nexus Double DQN — Central RL Service (Singleton)
==================================================
Coordinates state encoding, neural inference, explainability generation,
safety policy enforcement, model lifecycle management, and WebSocket broadcasting.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.rl.state_encoder import StateEncoder, STATE_DIM, FEATURE_NAMES
from app.rl.reward_calculator import RewardCalculator
from app.rl.environment import NexusRLEnvironment, ACTION_DIM, ACTION_NAMES
from app.rl.double_dqn_agent import DoubleDQNAgent
from app.rl.trainer import RLTrainer, TrainerConfig
from app.rl.evaluation import Evaluator
from app.rl.model_manager import ModelManager
from app.decision.engine import ActionType, SYSTEM_PROCESS_BLACKLIST, SYSTEM_PIDS

logger = logging.getLogger("nexus.rl.service")

# Mapping between RL action index (0..6) and Nexus ActionType constants
RL_TO_NEXUS_ACTION: Dict[int, str] = {
    0: ActionType.NONE,
    1: ActionType.RENICE,
    2: ActionType.THROTTLE,
    3: ActionType.SUSPEND,
    4: ActionType.RESTORE_PRIORITY,
    5: ActionType.RESTART,
    6: ActionType.KILL,
}


class RLService:
    """
    Singleton service managing the lifecycle, runtime inference, and safety gates of the Double DQN agent.
    """

    _instance: Optional["RLService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, checkpoints_dir: str = "app/rl/checkpoints") -> None:
        if getattr(self, "_initialized", False):
            return

        self.checkpoints_dir = os.path.abspath(checkpoints_dir)
        self.encoder = StateEncoder()
        self.reward_calculator = RewardCalculator()
        self.model_manager = ModelManager(checkpoints_dir=self.checkpoints_dir)

        # Core Agent
        self.agent = DoubleDQNAgent(state_dim=STATE_DIM, action_dim=ACTION_DIM)

        # Trainer & Evaluator
        self.env = NexusRLEnvironment()
        self.trainer = RLTrainer(agent=self.agent, env=self.env)
        self.evaluator = Evaluator(env=self.env)

        # Operational state
        self.autonomous_mode: bool = False  # False = Observe/Shadow mode; True = Active Autonomous Healing
        self.decision_count: int = 0
        self.recent_decisions: List[Dict[str, Any]] = []

        # Load active model from registry
        self._load_initial_model()
        self._initialized = True

    def _load_initial_model(self) -> None:
        """Attempt to load active model from registry or default checkpoint."""
        try:
            active_meta = self.model_manager.get_active_model()
            if active_meta and os.path.exists(active_meta.get("filepath", "")):
                self.agent.load_checkpoint(active_meta["filepath"])
                logger.info("RLService loaded active model: %s", active_meta.get("name"))
            else:
                default_ckpt = os.path.join(self.checkpoints_dir, "nexus_ddqn_default.pt")
                if os.path.exists(default_ckpt):
                    self.agent.load_checkpoint(default_ckpt)
                    logger.info("RLService loaded default checkpoint: %s", default_ckpt)
        except Exception as e:
            logger.warning("Could not load initial RL checkpoint (starting fresh): %s", e)

    def get_status(self) -> Dict[str, Any]:
        """Return operational status and agent telemetry."""
        active_model = self.model_manager.get_active_model()
        return {
            "status": "online",
            "autonomous_mode": self.autonomous_mode,
            "mode_label": "Autonomous Self-Healing" if self.autonomous_mode else "Observe & Advise (Shadow Mode)",
            "device": str(self.agent.device),
            "epsilon": round(float(self.agent.epsilon), 4),
            "is_training": self.trainer.is_training,
            "decision_count": self.decision_count,
            "active_model": active_model,
            "models_available": len(self.model_manager.list_models()),
            "state_dimension": STATE_DIM,
            "action_dimension": ACTION_DIM,
            "action_names": ACTION_NAMES,
        }

    def set_autonomous_mode(self, enabled: bool) -> bool:
        """Toggle between shadow/observe mode and active autonomous healing."""
        self.autonomous_mode = bool(enabled)
        logger.info("RL autonomous mode set to %s", self.autonomous_mode)
        return self.autonomous_mode

    def infer_and_evaluate(
        self,
        system_metrics: Any,
        process_snapshot: Any,
        anomaly_score: float = 0.0,
        forecast_mins: Optional[float] = None,
        memory_slope: float = 0.0,
        prev_action_idx: int = 0,
        action_success_rate: float = 1.0,
        process_health_history: float = 1.0,
        nice_value: int = 0,
    ) -> Dict[str, Any]:
        """
        Run forward inference through Double DQN, evaluate safety gates, and generate explainability telemetry.
        """
        pid = getattr(process_snapshot, "pid", 0) if process_snapshot else 0
        pname = getattr(process_snapshot, "name", "unknown") if process_snapshot else "unknown"

        # 1. Encode 14-dim observation vector
        state_vec = self.encoder.encode_from_real(
            system_metrics=system_metrics,
            process_snapshot=process_snapshot,
            anomaly_score=anomaly_score,
            forecast_mins=forecast_mins,
            memory_slope=memory_slope,
            prev_action_idx=prev_action_idx,
            action_success_rate=action_success_rate,
            process_health_history=process_health_history,
            nice_value=nice_value,
        )

        # 2. Select action with Double DQN policy (pure evaluation in inference)
        action_idx, explain_dict = self.agent.select_action(state_vec, evaluate=True)
        nexus_action = RL_TO_NEXUS_ACTION.get(action_idx, ActionType.NONE)

        # 3. SAFETY ENFORCEMENT GUARDRAILS
        was_blocked = False
        block_reason = None

        # Check PID blacklist
        if pid in SYSTEM_PIDS:
            was_blocked = True
            block_reason = f"PID {pid} is a protected core system process."

        # Check process name blacklist
        elif pname.lower() in SYSTEM_PROCESS_BLACKLIST:
            was_blocked = True
            block_reason = f"Process '{pname}' is protected by permanent safety blacklist."

        # Check action 6 (KILL)
        elif action_idx == 6:
            was_blocked = True
            block_reason = "SIGKILL action is strictly prohibited from automatic RL execution."

        # Enforce Observe-Only / Shadow Mode if not autonomous
        effective_action = nexus_action
        if not self.autonomous_mode and nexus_action != ActionType.NONE:
            effective_action = ActionType.ALERT_ONLY

        if was_blocked:
            effective_action = ActionType.NONE

        # 4. Construct human-readable state summary
        state_summary = {
            "system_cpu": round(float(state_vec[0]) * 100.0, 1),
            "system_ram": round(float(state_vec[1]) * 100.0, 1),
            "process_cpu": round(float(state_vec[4]) * 100.0, 1),
            "process_memory_mb": round(float(state_vec[5]) * 8192.0, 1),
            "anomaly_score": round(float(state_vec[7]), 3),
            "urgency": round(float(state_vec[8]), 2),
            "health": round(float(state_vec[11]), 2),
        }

        decision_record = {
            "pid": pid,
            "process_name": pname,
            "action_index": action_idx,
            "action_name": ACTION_NAMES[action_idx],
            "nexus_action": nexus_action,
            "effective_action": effective_action,
            "confidence": explain_dict.get("confidence", 0.0),
            "is_exploration": explain_dict.get("is_exploration", False),
            "q_values": explain_dict.get("q_values", {}),
            "probabilities": explain_dict.get("probabilities", {}),
            "state_vector": [round(float(v), 4) for v in state_vec.tolist()],
            "state_summary": state_summary,
            "was_blocked": was_blocked,
            "block_reason": block_reason,
            "autonomous_mode": self.autonomous_mode,
        }

        self.decision_count += 1
        self.recent_decisions.append(decision_record)
        if len(self.recent_decisions) > 100:
            self.recent_decisions.pop(0)

        return decision_record


# Global singleton instance
rl_service = RLService()
