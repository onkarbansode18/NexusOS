"""
Nexus 2.0 — Tests for Phases 3, 4, 5, 6:
Application Profiles, Operating Modes, Optimization Engine, and REST APIs.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.db import init_db
from app.application_manager import (
    ApplicationCategory,
    mode_manager,
    profile_manager,
    resource_optimizer,
    OperatingModeType,
)


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    yield


@pytest.mark.asyncio
async def test_get_applications_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/applications")
        assert res.status_code == 200
        data = res.json()
        assert "total_applications" in data
        assert "applications" in data
        assert isinstance(data["applications"], list)


@pytest.mark.asyncio
async def test_application_scan_and_category_update():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Trigger scan
        scan_res = await client.post("/api/applications/scan")
        assert scan_res.status_code == 200
        assert scan_res.json()["status"] == "success"

        # Update category
        cat_res = await client.put(
            "/api/applications/app_test_dummy/category",
            json={"category": "Development"}
        )
        assert cat_res.status_code == 200
        assert cat_res.json()["category"] == "Development"


@pytest.mark.asyncio
async def test_application_profiles_crud():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        app_id = "app_vscode_test123"

        # Create
        create_res = await client.post(
            "/api/application-profiles",
            json={
                "app_id": app_id,
                "name": "Visual Studio Code",
                "executable_path": r"C:\VSCode\Code.exe",
                "category": "Development",
                "importance": "High",
                "is_protected": True,
                "associated_modes": ["study"],
            }
        )
        assert create_res.status_code == 200
        assert create_res.json()["app_id"] == app_id

        # List
        list_res = await client.get("/api/application-profiles")
        assert list_res.status_code == 200
        profiles = list_res.json()
        match = next((p for p in profiles if p["app_id"] == app_id), None)
        assert match is not None
        assert match["importance"] == "High"
        assert match["is_protected"] is True

        # Update
        update_res = await client.put(
            f"/api/application-profiles/{app_id}",
            json={"importance": "Critical", "is_protected": False}
        )
        assert update_res.status_code == 200

        # Verify updated cache
        cached = profile_manager.get_cached_profile(app_id)
        assert cached is not None
        assert cached.importance == "Critical"
        assert cached.is_protected is False

        # Delete
        del_res = await client.delete(f"/api/application-profiles/{app_id}")
        assert del_res.status_code == 200


@pytest.mark.asyncio
async def test_operating_modes_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get modes
        modes_res = await client.get("/api/application-modes")
        assert modes_res.status_code == 200
        data = modes_res.json()
        assert len(data["available_modes"]) == 4

        # Activate Meeting Mode
        act_res = await client.post(
            "/api/application-modes/activate",
            json={"mode_id": OperatingModeType.MEETING}
        )
        assert act_res.status_code == 200
        assert mode_manager.active_mode_id == OperatingModeType.MEETING

        # Verify Active endpoint
        active_res = await client.get("/api/application-modes/active")
        assert active_res.status_code == 200
        assert active_res.json()["mode_id"] == OperatingModeType.MEETING

        # Switch to Gaming Mode with target app
        game_res = await client.post(
            "/api/application-modes/activate",
            json={"mode_id": OperatingModeType.GAMING, "target_app_id": "app_cyberpunk_1"}
        )
        assert game_res.status_code == 200
        assert mode_manager.active_mode_id == OperatingModeType.GAMING

        # Deactivate
        deact_res = await client.post("/api/application-modes/deactivate")
        assert deact_res.status_code == 200
        assert mode_manager.active_mode_id is None


@pytest.mark.asyncio
async def test_resource_optimizer_analysis_and_emergency_stop():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Check status
        status_res = await client.get("/api/application-optimizer/status")
        assert status_res.status_code == 200
        assert "is_enabled" in status_res.json()

        # Run analysis
        analyze_res = await client.post("/api/application-optimizer/analyze")
        assert analyze_res.status_code == 200
        plan = analyze_res.json()
        assert "recommendations" in plan

        # Emergency stop
        stop_res = await client.post("/api/application-optimizer/emergency-stop")
        assert stop_res.status_code == 200
        assert "restored" in stop_res.json()["message"].lower()
        assert resource_optimizer.is_enabled is False

        # Re-enable
        enable_res = await client.post("/api/application-optimizer/enable")
        assert enable_res.status_code == 200
        assert resource_optimizer.is_enabled is True

        # Check history endpoint
        hist_res = await client.get("/api/application-optimizer/history")
        assert hist_res.status_code == 200
        assert isinstance(hist_res.json(), list)


def test_precedence_hierarchy_safety():
    # Test 1: System PID 4 (System) must NEVER be optimizable
    level, is_opt, reason = profile_manager.evaluate_precedence(
        pid=4, process_name="System", app_id="app_system_1"
    )
    assert not is_opt
    assert "Critical OS" in reason

    # Test 2: User Blacklist must NEVER be optimizable
    level, is_opt, reason = profile_manager.evaluate_precedence(
        pid=1234, process_name="custom_miner.exe", app_id="app_miner_1",
        user_blacklist=["custom_miner.exe"]
    )
    assert not is_opt
    assert "blacklisted" in reason

    # Test 3: Normal process is optimizable
    level, is_opt, reason = profile_manager.evaluate_precedence(
        pid=9876, process_name="background_indexer.exe", app_id="app_indexer_1"
    )
    assert is_opt
