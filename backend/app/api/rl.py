"""
Nexus Double DQN — REST API Endpoints
=======================================
Router mounting at `/rl` providing:
  - Agent health, mode toggles, and live status
  - Asynchronous simulated training control and real-time loss telemetry
  - Policy benchmark comparison (Double DQN vs Rule-Based vs Random)
  - Model catalog registry and active model promotion
  - Real-time decision stream and explainability breakdown
  - Interactive scenario inference simulator ("What-If" sandbox)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.rl.rl_service import rl_service
from app.rl.environment import SimulationScenario, ACTION_NAMES

logger = logging.getLogger("nexus.api.rl")

router = APIRouter(prefix="/rl", tags=["Adaptive AI Reinforcement Learning"])


# ── Pydantic Request Models ─────────────────────────────────────────────────

class ModeToggleRequest(BaseModel):
    autonomous: bool = Field(..., description="Enable autonomous healing (True) or observe-only mode (False)")


class TrainRequest(BaseModel):
    episodes: int = Field(default=30, ge=1, le=500, description="Number of episodes to simulate")
    learning_rate: Optional[float] = Field(default=None, description="Optional override learning rate")


class EvaluateRequest(BaseModel):
    episodes_per_scenario: int = Field(default=5, ge=1, le=20, description="Episodes per scenario")


class SetActiveModelRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str = Field(..., description="Target model ID to activate")


class SimulateInferenceRequest(BaseModel):
    scenario: Optional[str] = Field(default="cpu_intensive", description="Scenario type")
    system_cpu: float = Field(default=75.0, ge=0.0, le=100.0)
    system_ram: float = Field(default=60.0, ge=0.0, le=100.0)
    disk_percent: float = Field(default=50.0, ge=0.0, le=100.0)
    process_cpu: float = Field(default=85.0, ge=0.0, le=100.0)
    process_memory_mb: float = Field(default=1200.0, ge=0.0)
    memory_growth_rate: float = Field(default=5.0)
    anomaly_score: float = Field(default=0.7)
    forecast_mins: Optional[float] = Field(default=4.5)
    thread_count: int = Field(default=12)
    process_name: str = Field(default="simulated_task.exe")
    pid: int = Field(default=1337)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/status")
def get_rl_status() -> Dict[str, Any]:
    """Get overall status of the Adaptive AI Double DQN system."""
    return rl_service.get_status()


@router.post("/mode")
def set_rl_mode(req: ModeToggleRequest) -> Dict[str, Any]:
    """Toggle between autonomous execution and observe-only shadow mode."""
    active = rl_service.set_autonomous_mode(req.autonomous)
    return {
        "autonomous_mode": active,
        "message": "Autonomous Self-Healing active" if active else "Observe & Advise shadow mode active",
    }


@router.get("/training/progress")
def get_training_progress() -> Dict[str, Any]:
    """Get real-time snapshot of training loss, rewards, and episode counts."""
    return rl_service.trainer.get_progress()


@router.post("/train")
def start_training(req: TrainRequest) -> Dict[str, Any]:
    """Trigger background Double DQN training loop over simulated scenarios."""
    if rl_service.trainer.is_training:
        raise HTTPException(status_code=400, detail="Training is already running.")

    if req.learning_rate:
        rl_service.trainer.config.learning_rate = req.learning_rate

    started = rl_service.trainer.start_training_async(episodes=req.episodes)
    return {
        "started": started,
        "episodes_scheduled": req.episodes,
        "message": f"Double DQN training started for {req.episodes} episodes.",
    }


@router.post("/stop")
def stop_training() -> Dict[str, Any]:
    """Halt any running training process safely."""
    rl_service.trainer.stop_training()
    return {"message": "Stop signal transmitted to RL training loop."}


@router.post("/evaluate")
def run_evaluation(req: EvaluateRequest) -> Dict[str, Any]:
    """Benchmark current Double DQN policy against Rule-Based and Random policies."""
    results = rl_service.evaluator.evaluate_all(
        agent=rl_service.agent,
        episodes_per_scenario=req.episodes_per_scenario,
    )
    return results


@router.get("/models")
def list_models() -> List[Dict[str, Any]]:
    """List all registered Double DQN checkpoints."""
    return rl_service.model_manager.list_models()


@router.post("/models/active")
def set_active_model(req: SetActiveModelRequest) -> Dict[str, Any]:
    """Activate a specific model checkpoint for live inference."""
    success = rl_service.model_manager.set_active_model(req.model_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Model {req.model_id} not found or file missing.")

    active = rl_service.model_manager.get_active_model()
    if active and "filepath" in active:
        rl_service.agent.load_checkpoint(active["filepath"])

    return {"success": True, "active_model": active}


@router.delete("/models/{model_id}")
def delete_model(model_id: str) -> Dict[str, Any]:
    """Delete a model checkpoint from registry."""
    success = rl_service.model_manager.delete_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Model could not be deleted.")
    return {"success": True, "model_id": model_id}


@router.get("/decisions")
def get_recent_decisions() -> List[Dict[str, Any]]:
    """Get stream of recent decisions made by the RL system with full explainability."""
    return list(reversed(rl_service.recent_decisions[-50:]))


@router.post("/simulate")
def simulate_inference(req: SimulateInferenceRequest) -> Dict[str, Any]:
    """
    Interactive 'What-If' sandbox: feed custom telemetry and inspect the agent's
    action selection, Q-values distribution, and explainability breakdown.
    """
    mock_metrics = type("Metrics", (), {
        "cpu_percent": req.system_cpu,
        "ram_percent": req.system_ram,
        "disk": type("Disk", (), {"percent": req.disk_percent})(),
        "network": type("Net", (), {"delta_bytes_sent": 1024 * 500, "delta_bytes_recv": 1024 * 500})(),
    })()

    mock_proc = type("Process", (), {
        "pid": req.pid,
        "name": req.process_name,
        "cpu_percent": req.process_cpu,
        "memory_mb": req.process_memory_mb,
        "num_threads": req.thread_count,
    })()

    decision = rl_service.infer_and_evaluate(
        system_metrics=mock_metrics,
        process_snapshot=mock_proc,
        anomaly_score=req.anomaly_score,
        forecast_mins=req.forecast_mins,
        memory_slope=req.memory_growth_rate,
    )
    return decision
