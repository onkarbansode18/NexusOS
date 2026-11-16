"""
Nexus 2.0 — Application-Aware Resource Management API Router
Endpoints for applications, profiles, operating modes, and smart optimizations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_manager import (
    ApplicationCategory,
    ApplicationImportance,
    ApplicationDetector,
    application_registry,
    profile_manager,
    mode_manager,
    resource_optimizer,
    OptimizationStrategy,
)
from app.application_manager.application_models import ProcessDetail
from app.db import get_db, get_policy
from app.db.models import (
    ApplicationProfileRecord,
    ApplicationModeRecord,
    ApplicationOptimizationRecord,
    ApplicationModeHistoryRecord,
)
from app.executor.actions import ActionExecutor
from app.api.websocket import manager, get_latest_metrics

logger = logging.getLogger("nexus.api.applications")

router = APIRouter(prefix="/api", tags=["applications"])

# Shared global detector instance
detector = ApplicationDetector()


# ── Pydantic Request / Response Schemas ───────────────────────────────────────

class CategoryUpdateRequest(BaseModel):
    category: str


class ProfileCreateRequest(BaseModel):
    app_id: str
    name: str
    executable_path: Optional[str] = None
    category: str = "Unknown"
    importance: str = "Normal"
    is_protected: bool = False
    preferred_priority: str = "NORMAL"
    allowed_actions: List[str] = Field(default_factory=lambda: ["renice", "restore_priority"])
    associated_modes: List[str] = Field(default_factory=list)
    user_notes: Optional[str] = None


class ProfileUpdateRequest(BaseModel):
    importance: Optional[str] = None
    is_protected: Optional[bool] = None
    category: Optional[str] = None
    preferred_priority: Optional[str] = None
    is_enabled: Optional[bool] = None
    allowed_actions: Optional[List[str]] = None
    associated_modes: Optional[List[str]] = None
    user_notes: Optional[str] = None
    max_cpu_percent: Optional[float] = None
    max_memory_mb: Optional[float] = None


class ModeActivateRequest(BaseModel):
    mode_id: str
    target_app_id: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None


class ModeConfigureRequest(BaseModel):
    configuration: Dict[str, Any]


class StrategyUpdateRequest(BaseModel):
    strategy: str


# ── APPLICATIONS ENDPOINTS ────────────────────────────────────────────────────

@router.get("/applications")
async def get_applications() -> Dict[str, Any]:
    """Returns all currently running detected applications, sorted by resource footprint."""
    # Ultra-fast path: use latest live processes from background monitoring agent if available
    metrics = get_latest_metrics()
    if metrics and metrics.processes:
        proc_details = [
            ProcessDetail(
                pid=p.pid,
                ppid=None,
                name=p.name,
                exe=None,
                cmdline=None,
                cpu_percent=p.cpu_percent,
                memory_mb=p.memory_mb,
                memory_percent=p.memory_percent,
                num_threads=p.num_threads or 1,
                status=p.status or "running",
                created_at=p.created_at or "",
                create_time=0.0,
                priority="NORMAL",
                read_bytes=None,
                write_bytes=None,
                network_bytes=None,
            )
            for p in metrics.processes
        ]
        apps = detector.detect_applications(proc_details)
    else:
        apps = detector.detect_applications()

    # Enrich with profile status if saved in DB
    enriched = []
    for app in apps:
        app_dict = app.to_dict()
        prof = profile_manager.get_cached_profile(app.app_id)
        if prof:
            app_dict["importance"] = prof.importance
            app_dict["is_protected"] = prof.is_protected
            app_dict["associated_modes"] = prof.associated_modes
        else:
            app_dict["importance"] = "Critical" if app.is_system else "Normal"
        enriched.append(app_dict)

    return {
        "total_applications": len(enriched),
        "total_processes": sum(a["process_count"] for a in enriched),
        "total_cpu_percent": round(sum(a["total_cpu_percent"] for a in enriched), 2),
        "total_memory_mb": round(sum(a["total_memory_mb"] for a in enriched), 2),
        "applications": enriched,
    }


@router.get("/applications/{app_id}")
async def get_application(app_id: str) -> Dict[str, Any]:
    """Returns detailed information for a specific application."""
    app = detector.get_application(app_id)
    if not app:
        # Check active scan
        apps = detector.detect_applications()
        app = next((a for a in apps if a.app_id == app_id), None)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found or no longer active.")

    app_dict = app.to_dict()
    prof = profile_manager.get_cached_profile(app_id)
    if prof:
        app_dict["profile"] = {
            "importance": prof.importance,
            "is_protected": prof.is_protected,
            "preferred_priority": prof.preferred_priority,
            "allowed_actions": prof.allowed_actions,
            "associated_modes": prof.associated_modes,
            "user_notes": prof.user_notes,
        }
    return app_dict


@router.get("/applications/{app_id}/processes")
async def get_application_processes(app_id: str) -> Dict[str, Any]:
    """Returns the list and process tree of all child PIDs belonging to this application."""
    app = detector.get_application(app_id)
    if not app:
        apps = detector.detect_applications()
        app = next((a for a in apps if a.app_id == app_id), None)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found.")

    return {
        "app_id": app.app_id,
        "name": app.name,
        "root_pid": app.root_pid,
        "process_count": app.process_count,
        "processes": [p.to_dict() for p in app.processes],
    }


@router.post("/applications/scan")
async def scan_applications() -> Dict[str, Any]:
    """Triggers an immediate on-demand application discovery sweep."""
    apps = detector.detect_applications()
    await manager.broadcast({
        "event": "applications_updated",
        "data": {
            "total_applications": len(apps),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    })
    return {"status": "success", "detected_count": len(apps)}


@router.put("/applications/{app_id}/category")
async def update_application_category(
    app_id: str,
    req: CategoryUpdateRequest,
) -> Dict[str, Any]:
    """Updates the user-corrected category for an application persistently."""
    try:
        cat = ApplicationCategory(req.category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: '{req.category}'")

    detector.classifier.set_user_classification(app_id, cat)

    # Broadcast update
    await manager.broadcast({
        "event": "application_category_updated",
        "data": {"app_id": app_id, "category": cat.value},
    })
    return {"status": "success", "app_id": app_id, "category": cat.value}


# ── APPLICATION PROFILES ENDPOINTS ────────────────────────────────────────────

@router.get("/application-profiles")
async def get_profiles(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """Returns all saved application profiles."""
    profiles = await profile_manager.load_profiles_from_db(db)
    return [
        {
            "id": p.id,
            "app_id": p.app_id,
            "name": p.name,
            "executable_path": p.executable_path,
            "category": p.category,
            "importance": p.importance,
            "preferred_priority": p.preferred_priority,
            "is_protected": p.is_protected,
            "is_enabled": p.is_enabled,
            "allowed_actions": p.allowed_actions,
            "max_cpu_percent": p.max_cpu_percent,
            "max_memory_mb": p.max_memory_mb,
            "associated_modes": p.associated_modes,
            "user_notes": p.user_notes,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in profiles
    ]


@router.post("/application-profiles")
async def create_profile(
    req: ProfileCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Creates a persistent application profile."""
    profile = await profile_manager.get_or_create_profile(
        db=db,
        app_id=req.app_id,
        name=req.name,
        executable_path=req.executable_path,
        category=req.category,
        importance=req.importance,
        is_protected=req.is_protected,
    )
    # Update optional fields
    await profile_manager.update_profile(
        db=db,
        app_id=req.app_id,
        preferred_priority=req.preferred_priority,
        allowed_actions=req.allowed_actions,
        associated_modes=req.associated_modes,
        user_notes=req.user_notes,
    )
    return {"status": "success", "profile_id": profile.id, "app_id": profile.app_id}


@router.put("/application-profiles/{app_id}")
async def update_profile(
    app_id: str,
    req: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Updates an existing application profile."""
    updated = await profile_manager.update_profile(
        db=db,
        app_id=app_id,
        importance=req.importance,
        is_protected=req.is_protected,
        category=req.category,
        preferred_priority=req.preferred_priority,
        is_enabled=req.is_enabled,
        allowed_actions=req.allowed_actions,
        associated_modes=req.associated_modes,
        user_notes=req.user_notes,
        max_cpu_percent=req.max_cpu_percent,
        max_memory_mb=req.max_memory_mb,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Profile not found.")

    await manager.broadcast({
        "event": "application_profile_updated",
        "data": {
            "app_id": app_id,
            "importance": updated.importance,
            "is_protected": updated.is_protected,
        },
    })
    return {"status": "success", "app_id": app_id}


@router.delete("/application-profiles/{app_id}")
async def delete_profile(
    app_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Deletes an application profile."""
    success = await profile_manager.delete_profile(db, app_id)
    if not success:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return {"status": "success", "app_id": app_id}


# ── OPERATING MODES ENDPOINTS ─────────────────────────────────────────────────

@router.get("/application-modes")
async def get_operating_modes() -> Dict[str, Any]:
    """Returns all 4 operating modes, their details, and active status."""
    return {
        "active_mode": mode_manager.get_active_mode_info(),
        "available_modes": mode_manager.get_all_modes(),
        "battery": mode_manager.get_battery_status(),
    }


@router.get("/application-modes/active")
async def get_active_operating_mode() -> Dict[str, Any]:
    """Returns the currently active operating mode."""
    return mode_manager.get_active_mode_info()


@router.post("/application-modes/activate")
async def activate_operating_mode(
    req: ModeActivateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Activates an operating mode (Gaming, Study, Meeting, Battery Saver)."""
    policy = await get_policy(db)
    executor = ActionExecutor(simulation_mode=policy.simulation_mode)

    try:
        active_info = await mode_manager.activate_mode(
            mode_id=req.mode_id,
            target_app_id=req.target_app_id,
            custom_config=req.configuration,
            db=db,
            executor=executor,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await manager.broadcast({
        "event": "operating_mode_changed",
        "data": active_info,
    })
    return {"status": "success", "active_mode": active_info}


@router.post("/application-modes/deactivate")
async def deactivate_operating_mode(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Deactivates active mode and restores any lowered priorities."""
    policy = await get_policy(db)
    executor = ActionExecutor(simulation_mode=policy.simulation_mode)
    active_info = await mode_manager.deactivate_mode(db=db, executor=executor)

    await manager.broadcast({
        "event": "operating_mode_changed",
        "data": active_info,
    })
    return {"status": "success", "active_mode": active_info}


@router.put("/application-modes/{mode_id}/configuration")
async def update_mode_configuration(
    mode_id: str,
    req: ModeConfigureRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Customizes settings and protected applications for an operating mode."""
    stmt = select(ApplicationModeRecord).where(ApplicationModeRecord.id == mode_id)
    res = await db.execute(stmt)
    mode_rec = res.scalar_one_or_none()
    if mode_rec:
        mode_rec.configuration = req.configuration
        mode_rec.updated_at = datetime.now(timezone.utc)
        await db.commit()
    return {"status": "success", "mode_id": mode_id}


# ── OPTIMIZATION ENDPOINTS ────────────────────────────────────────────────────

@router.get("/application-optimizer/status")
async def get_optimizer_status() -> Dict[str, Any]:
    """Returns optimization engine status, active strategy, and pending recommendations."""
    return {
        "is_enabled": resource_optimizer.is_enabled,
        "strategy": resource_optimizer.strategy,
        "pending_recommendations_count": len(resource_optimizer.get_pending_recommendations()),
        "active_mode": mode_manager.active_mode_id,
        "action_cooldown_seconds": resource_optimizer.action_cooldown_seconds,
    }


@router.post("/application-optimizer/analyze")
async def analyze_and_optimize(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Analyzes live system telemetry, evaluates operating mode directives,
    and formulates an optimization plan. In autonomous mode, executes safe recommendations.
    """
    metrics = get_latest_metrics()
    cpu_pct = metrics.cpu_percent if metrics else 0.0
    ram_pct = metrics.ram_percent if metrics else 0.0

    policy = await get_policy(db)
    apps = detector.detect_applications()

    # Pre-populate profile cache
    await profile_manager.load_profiles_from_db(db)

    plan = resource_optimizer.analyze_and_plan(
        applications=apps,
        system_cpu_percent=cpu_pct,
        system_ram_percent=ram_pct,
        user_whitelist=policy.process_whitelist,
        user_blacklist=policy.process_blacklist,
    )

    # In Autonomous mode, execute safe low-risk recommendations
    executed_results = []
    if resource_optimizer.is_enabled and resource_optimizer.strategy == OptimizationStrategy.AUTONOMOUS:
        executor = ActionExecutor(simulation_mode=policy.simulation_mode)
        for item in plan.recommendations:
            if item.is_safe and item.risk_level == "low" and item.proposed_action != "observe_only":
                res = await resource_optimizer.execute_plan_item(item, executor, db)
                executed_results.append({
                    "plan_item_id": item.plan_item_id,
                    "pid": item.pid,
                    "process_name": item.process_name,
                    "action": item.proposed_action,
                    "success": res.success,
                    "simulated": res.simulated,
                })
                await manager.broadcast({
                    "event": "optimization_executed",
                    "data": {
                        "pid": item.pid,
                        "process_name": item.process_name,
                        "action": item.proposed_action,
                        "simulated": res.simulated,
                    },
                })

    plan_dict = plan.to_dict()
    plan_dict["executed_autonomous_actions"] = executed_results
    return plan_dict


@router.post("/application-optimizer/enable")
async def enable_optimizer() -> Dict[str, Any]:
    resource_optimizer.enable()
    return {"status": "success", "is_enabled": True}


@router.post("/application-optimizer/disable")
async def disable_optimizer() -> Dict[str, Any]:
    resource_optimizer.disable()
    return {"status": "success", "is_enabled": False}


@router.post("/application-optimizer/strategy")
async def set_optimizer_strategy(req: StrategyUpdateRequest) -> Dict[str, Any]:
    try:
        resource_optimizer.set_strategy(req.strategy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "strategy": resource_optimizer.strategy}


@router.post("/application-optimizer/emergency-stop")
async def emergency_stop(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Emergency disable: stops optimization immediately and restores all priorities."""
    policy = await get_policy(db)
    executor = ActionExecutor(simulation_mode=policy.simulation_mode)
    restored_count = await resource_optimizer.emergency_disable(executor, db)

    await manager.broadcast({
        "event": "emergency_stop_triggered",
        "data": {
            "restored_count": restored_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    })
    return {"status": "success", "message": f"Emergency stop engaged. Restored {restored_count} process priorities."}


@router.get("/application-optimizer/recommendations")
async def get_recommendations(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """Returns all currently pending optimization recommendations (auto-formulates on open if empty)."""
    items = resource_optimizer.get_pending_recommendations()
    if not items:
        try:
            metrics = get_latest_metrics()
            cpu_pct = metrics.cpu_percent if metrics else 0.0
            ram_pct = metrics.ram_percent if metrics else 0.0
            policy = await get_policy(db)
            if metrics and metrics.processes:
                proc_details = [
                    ProcessDetail(
                        pid=p.pid,
                        ppid=None,
                        name=p.name,
                        exe=None,
                        cmdline=None,
                        cpu_percent=p.cpu_percent,
                        memory_mb=p.memory_mb,
                        memory_percent=p.memory_percent,
                        num_threads=p.num_threads or 1,
                        status=p.status or "running",
                        created_at=p.created_at or "",
                        create_time=0.0,
                        priority="NORMAL",
                        read_bytes=None,
                        write_bytes=None,
                        network_bytes=None,
                    )
                    for p in metrics.processes
                ]
                apps = detector.detect_applications(proc_details)
            else:
                apps = detector.detect_applications()
            plan = resource_optimizer.analyze_and_plan(
                applications=apps,
                system_cpu_percent=cpu_pct,
                system_ram_percent=ram_pct,
                user_whitelist=policy.process_whitelist,
                user_blacklist=policy.process_blacklist,
            )
            items = plan.recommendations
        except Exception as e:
            logger.debug("Auto recommendation generation: %s", e)
    return [i.to_dict() for i in items]


@router.post("/application-optimizer/recommendations/{plan_item_id}/approve")
async def approve_recommendation(
    plan_item_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Approves and executes a specific pending recommendation."""
    item = resource_optimizer.get_recommendation(plan_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Recommendation not found or already dispatched.")

    policy = await get_policy(db)
    executor = ActionExecutor(simulation_mode=policy.simulation_mode)

    result = await resource_optimizer.execute_plan_item(item, executor, db)

    await manager.broadcast({
        "event": "optimization_executed",
        "data": {
            "plan_item_id": plan_item_id,
            "pid": item.pid,
            "process_name": item.process_name,
            "action": item.proposed_action,
            "success": result.success,
            "simulated": result.simulated,
        },
    })
    return {
        "status": "success",
        "action_result": {
            "pid": result.pid,
            "action": result.action_type,
            "success": result.success,
            "simulated": result.simulated,
            "reason": result.reason,
            "before_cpu": result.before_cpu,
            "after_cpu": result.after_cpu,
        },
    }


@router.post("/application-optimizer/recommendations/{plan_item_id}/reject")
async def reject_recommendation(plan_item_id: str) -> Dict[str, Any]:
    """Rejects and dismisses a recommendation."""
    success = resource_optimizer.reject_recommendation(plan_item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    return {"status": "success", "plan_item_id": plan_item_id, "action": "rejected"}


@router.get("/application-optimizer/history")
async def get_optimization_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Returns past optimization actions and outcomes."""
    stmt = (
        select(ApplicationOptimizationRecord)
        .order_by(desc(ApplicationOptimizationRecord.created_at))
        .limit(limit)
    )
    res = await db.execute(stmt)
    records = res.scalars().all()

    return [
        {
            "id": r.id,
            "app_id": r.app_id,
            "app_name": r.app_name,
            "pid": r.pid,
            "action_type": r.action_type,
            "operating_mode": r.operating_mode,
            "status": r.status,
            "risk_level": r.risk_level,
            "reason": r.reason,
            "before_priority": r.before_priority,
            "after_priority": r.after_priority,
            "before_cpu": r.before_cpu,
            "after_cpu": r.after_cpu,
            "before_memory_mb": r.before_memory_mb,
            "after_memory_mb": r.after_memory_mb,
            "executed_at": r.executed_at.isoformat() if r.executed_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
