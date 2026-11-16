"""
Integration Tests for RL API Router & Decision Engine (Phase 6)
===============================================================
Tests verify:
  1. GET /rl/status operational health and active model metadata
  2. POST /rl/mode autonomous mode toggle
  3. POST /rl/simulate interactive what-if inference sandbox
  4. GET /rl/models and POST /rl/models/active model management
  5. POST /rl/evaluate policy comparison benchmarks
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.rl import router as rl_router
from app.rl.rl_service import rl_service


@pytest.fixture(scope="module")
def client():
    test_app = FastAPI()
    test_app.include_router(rl_router)
    return TestClient(test_app)


def test_api_rl_status(client):
    """Verify /rl/status endpoint returns valid health payload."""
    res = client.get("/rl/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "autonomous_mode" in data
    assert "active_model" in data
    assert data["state_dimension"] == 14
    assert data["action_dimension"] == 7


def test_api_rl_mode_toggle(client):
    """Verify /rl/mode toggles between autonomous and shadow modes."""
    # Enable autonomous mode
    res = client.post("/rl/mode", json={"autonomous": True})
    assert res.status_code == 200
    assert res.json()["autonomous_mode"] is True
    assert rl_service.autonomous_mode is True

    # Revert to observe-only mode
    res = client.post("/rl/mode", json={"autonomous": False})
    assert res.status_code == 200
    assert res.json()["autonomous_mode"] is False
    assert rl_service.autonomous_mode is False


def test_api_rl_simulate_inference(client):
    """Verify interactive what-if simulation endpoint."""
    payload = {
        "scenario": "cpu_intensive",
        "system_cpu": 92.0,
        "system_ram": 65.0,
        "disk_percent": 45.0,
        "process_cpu": 88.0,
        "process_memory_mb": 1500.0,
        "memory_growth_rate": 2.0,
        "anomaly_score": 0.85,
        "forecast_mins": 3.2,
        "thread_count": 16,
        "process_name": "high_load_worker.exe",
        "pid": 4567,
    }
    res = client.post("/rl/simulate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["pid"] == 4567
    assert data["process_name"] == "high_load_worker.exe"
    assert 0 <= data["action_index"] < 7
    assert "q_values" in data
    assert "confidence" in data
    assert "state_summary" in data
    assert data["was_blocked"] is False


def test_api_rl_simulate_safety_blocked(client):
    """Verify safety guardrail blocks protected system processes."""
    payload = {
        "process_name": "csrss.exe",  # System blacklist process
        "pid": 555,
        "system_cpu": 90.0,
        "process_cpu": 85.0,
    }
    res = client.post("/rl/simulate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["was_blocked"] is True
    assert "blacklist" in data["block_reason"].lower() or "protected" in data["block_reason"].lower()


def test_api_rl_models_catalog(client):
    """Verify /rl/models returns registered models."""
    res = client.get("/rl/models")
    assert res.status_code == 200
    models = res.json()
    assert isinstance(models, list)
    assert len(models) >= 1
    active_models = [m for m in models if m.get("is_active")]
    assert len(active_models) >= 1


def test_api_rl_evaluation(client):
    """Verify /rl/evaluate runs policy benchmarking."""
    res = client.post("/rl/evaluate", json={"episodes_per_scenario": 1})
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "policies" in data
    assert "double_dqn" in data["policies"]
    assert "rule_based" in data["policies"]
    assert "random" in data["policies"]
