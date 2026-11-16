"""
Nexus — Actions API routes.
Executes or simulates manual corrective actions on processes.
"""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db import get_db, get_policy, log_action, create_incident, resolve_incident
from app.executor.actions import ActionExecutor
from app.api.websocket import manager

router = APIRouter(prefix="/actions", tags=["actions"])


class ActionExecuteRequest(BaseModel):
    action_type: str         # 'renice' | 'throttle' | 'suspend' | 'restart' | 'kill' | 'observe'
    pid: int
    process_name: str
    reason: Optional[str] = "Manual action triggered via dashboard."
    incident_id: Optional[str] = None
    simulation_mode: Optional[bool] = None


class ActionExecuteResponse(BaseModel):
    action_type: str
    pid: int
    process_name: str
    simulated: bool
    success: bool
    reason: str
    before_cpu: Optional[float] = None
    before_memory_mb: Optional[float] = None
    after_cpu: Optional[float] = None
    after_memory_mb: Optional[float] = None
    executed_at: str
    error: Optional[str] = None
    new_pid: Optional[int] = None   # populated after restart relaunches the process


@router.post("/execute", response_model=ActionExecuteResponse)
async def execute_action(
    req: ActionExecuteRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> ActionExecuteResponse:
    policy = await get_policy(db)
    sim_mode = req.simulation_mode if req.simulation_mode is not None else policy.simulation_mode
    executor = ActionExecutor(simulation_mode=sim_mode)

    result = executor.execute(
        action_type=req.action_type,
        pid=req.pid,
        process_name=req.process_name,
        reason=req.reason or "Manual dashboard action",
    )

    # Persist action to DB and link/create incident
    incident_id = req.incident_id
    try:
        if not incident_id or incident_id == 'manual':
            inc = await create_incident(
                db=db,
                pid=req.pid,
                process_name=req.process_name,
                severity="medium" if req.action_type in ("kill", "restart") else "low",
                description=f"Manual operator action: {req.action_type} on {req.process_name} (PID {req.pid})",
            )
            incident_id = inc.id

        await log_action(
            db=db,
            incident_id=incident_id,
            action_type=result.action_type,
            pid=result.pid,
            process_name=result.process_name,
            simulated=result.simulated,
            reason=result.reason,
            before_cpu=result.before_cpu,
            before_memory_mb=result.before_memory_mb,
            after_cpu=result.after_cpu,
            after_memory_mb=result.after_memory_mb,
        )

        if req.incident_id and req.incident_id != 'manual':
            await resolve_incident(db, req.incident_id)
    except Exception as exc:
        import logging
        logging.getLogger("nexus.actions").warning("Failed to persist manual action: %s", exc)

    # Broadcast action to all connected WebSocket clients for real-time UI updates
    try:
        await manager.broadcast({
            "event": "action",
            "data": {
                "id": f"act-{result.pid}-{result.action_type}",
                "incident_id": incident_id,
                "action_type": result.action_type,
                "action_title": f"{result.action_type.capitalize()} {result.process_name}",
                "pid": result.pid,
                "process_name": result.process_name,
                "simulated": result.simulated,
                "success": result.success,
                "reason": result.reason,
                "before_cpu": result.before_cpu,
                "before_memory_mb": result.before_memory_mb,
                "after_cpu": result.after_cpu,
                "after_memory_mb": result.after_memory_mb,
                "executed_at": result.executed_at,
                "new_pid": getattr(result, "new_pid", None),
            }
        })
    except Exception:
        pass

    return ActionExecuteResponse(
        action_type=result.action_type,
        pid=result.pid,
        process_name=result.process_name,
        simulated=result.simulated,
        success=result.success,
        reason=result.reason,
        before_cpu=result.before_cpu,
        before_memory_mb=result.before_memory_mb,
        after_cpu=result.after_cpu,
        after_memory_mb=result.after_memory_mb,
        executed_at=result.executed_at,
        error=result.error,
        new_pid=getattr(result, "new_pid", None),
    )
