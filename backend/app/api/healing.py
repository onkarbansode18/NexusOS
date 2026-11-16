"""
Nexus — Healing & Diagnostics API Routes
==========================================
Provides HTTP endpoints for the 5 advanced self-healing features:
  1. Autonomous Self-Healing Engine (cooldown, emergency stop, verifications)
  2. Memory Leak and Memory Pressure Detection
  3. Intelligent Resource Optimization (priority restoration)
  4. Disk Space and Temporary File Management (scan, cleanup, audit)
  5. Root-Cause Diagnosis and Recovery History
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db import (
    get_db,
    get_policy,
    get_rca_by_incident,
    get_recent_rcas,
    create_disk_cleanup_record,
    get_disk_cleanup_records,
    get_recovery_verifications,
    get_healing_actions,
)
from app.executor import ActionExecutor
from app.healing import (
    cooldown_manager,
    disk_manager,
    memory_analyser,
    recovery_verifier,
    rca_engine,
    sustained_tracker,
)
from app.api.websocket import get_latest_metrics, manager

router = APIRouter(prefix="/healing", tags=["healing"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class EmergencyStopRequest(BaseModel):
    reason: Optional[str] = "Operator triggered emergency stop via dashboard."


class RestorePriorityRequest(BaseModel):
    pid: int
    process_name: str
    simulation_mode: Optional[bool] = None


class DiskCleanupRequest(BaseModel):
    simulation_mode: Optional[bool] = None
    min_age_hours: Optional[float] = 24.0


# ── 1. Autonomous Engine & Safety Controls ────────────────────────────────────

@router.get("/cooldown/status")
async def get_cooldown_status(_user: str = Depends(get_current_user)) -> Dict[str, Any]:
    """Get active cooldown status, emergency stop state, and velocity metrics."""
    return {
        "emergency_stop_active": cooldown_manager.emergency_stop_active,
        "emergency_stop_reason": cooldown_manager.emergency_stop_reason,
        "active_cooldown_processes_count": len(cooldown_manager._last_action),
    }


@router.post("/emergency-stop")
async def trigger_emergency_stop(
    req: EmergencyStopRequest,
    _user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """Immediately halt all automated healing actions."""
    cooldown_manager.trigger_emergency_stop(req.reason or "Operator triggered emergency stop.")
    await manager.broadcast({
        "event": "emergency_stop",
        "data": {"active": True, "reason": cooldown_manager.emergency_stop_reason},
    })
    return {
        "status": "success",
        "message": "Emergency stop activated. All automated healing actions are suspended.",
        "emergency_stop_active": True,
        "reason": cooldown_manager.emergency_stop_reason,
    }


@router.post("/emergency-stop/clear")
async def clear_emergency_stop(_user: str = Depends(get_current_user)) -> Dict[str, Any]:
    """Clear emergency stop and resume normal automated healing."""
    cooldown_manager.clear_emergency_stop()
    await manager.broadcast({
        "event": "emergency_stop",
        "data": {"active": False, "reason": ""},
    })
    return {
        "status": "success",
        "message": "Emergency stop cleared. Automated healing resumed.",
        "emergency_stop_active": False,
    }


# ── 2. Memory Leak and Pressure Detection ─────────────────────────────────────

@router.get("/memory/findings")
async def get_all_memory_findings(_user: str = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Analyze all actively tracked processes for memory leaks and spikes."""
    metrics = get_latest_metrics()
    findings = []
    if metrics:
        for proc in metrics.processes:
            finding = memory_analyser.analyse(proc.pid)
            if finding.kind != "normal":
                findings.append({
                    "pid": finding.pid,
                    "process_name": finding.process_name,
                    "kind": finding.kind,
                    "current_rss_mb": finding.current_rss_mb,
                    "growth_rate_mb_per_min": finding.growth_rate_mb_per_min,
                    "slope_r_squared": finding.slope_r_squared,
                    "samples_analysed": finding.samples_analysed,
                    "description": finding.description,
                    "is_actionable": finding.is_actionable,
                    "minutes_until_breach": finding.minutes_until_breach,
                })
    return findings


@router.get("/memory/analysis/{pid}")
async def get_process_memory_analysis(
    pid: int,
    _user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve detailed trend analysis for a specific PID."""
    finding = memory_analyser.analyse(pid)
    return {
        "pid": finding.pid,
        "process_name": finding.process_name,
        "kind": finding.kind,
        "current_rss_mb": finding.current_rss_mb,
        "growth_rate_mb_per_min": finding.growth_rate_mb_per_min,
        "slope_r_squared": finding.slope_r_squared,
        "samples_analysed": finding.samples_analysed,
        "window_seconds": finding.window_seconds,
        "system_ram_percent": finding.system_ram_percent,
        "description": finding.description,
        "is_actionable": finding.is_actionable,
        "minutes_until_breach": finding.minutes_until_breach,
    }


# ── 3. Intelligent Resource Optimization (Priority Reversal) ──────────────────

@router.post("/priority/restore")
async def restore_process_priority(
    req: RestorePriorityRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """Revert a throttled or reniced process back to standard operating priority."""
    policy = await get_policy(db)
    sim = req.simulation_mode if req.simulation_mode is not None else policy.simulation_mode
    executor = ActionExecutor(simulation_mode=sim)
    result = executor.restore_priority(pid=req.pid, process_name=req.process_name)
    return {
        "success": result.success,
        "action_type": result.action_type,
        "pid": result.pid,
        "process_name": result.process_name,
        "simulated": result.simulated,
        "reason": result.reason,
        "before_cpu": result.before_cpu,
        "after_cpu": result.after_cpu,
        "error": result.error,
    }


# ── 4. Disk Space and Temporary File Management ───────────────────────────────

@router.get("/disk/report")
async def get_disk_report(_user: str = Depends(get_current_user)) -> Dict[str, Any]:
    """Scan OS temp locations and return current disk usage and reclaimable space."""
    rep = await asyncio.to_thread(disk_manager.disk_report)
    return {
        "timestamp": rep.timestamp,
        "disk_path": rep.disk_path,
        "total_gb": rep.total_gb,
        "used_gb": rep.used_gb,
        "free_gb": rep.free_gb,
        "used_percent": rep.used_percent,
        "total_reclaimable_mb": rep.total_reclaimable_mb,
        "warning": rep.warning,
        "critical": rep.critical,
        "temp_dirs_scanned": [
            {
                "path": d.path,
                "total_files": d.total_files,
                "total_size_mb": d.total_size_mb,
                "reclaimable_files": d.reclaimable_files,
                "reclaimable_size_mb": d.reclaimable_size_mb,
                "error": d.error,
            }
            for d in rep.temp_dirs_scanned
        ],
    }


@router.post("/disk/cleanup")
async def execute_disk_cleanup(
    req: DiskCleanupRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """Execute or simulate cleanup of aged temporary files and log the audit record."""
    policy = await get_policy(db)
    sim = req.simulation_mode if req.simulation_mode is not None else policy.simulation_mode

    # Configure disk manager mode
    orig_sim = disk_manager.simulation_mode
    disk_manager.simulation_mode = sim
    try:
        report_before = await asyncio.to_thread(disk_manager.disk_report)
        plan = await asyncio.to_thread(disk_manager.execute_cleanup)
        report_after = await asyncio.to_thread(disk_manager.disk_report)

        # Audit trail persistence
        deleted_count = sum(1 for e in plan.entries if e.deleted)
        recovered_mb = sum(e.size_mb for e in plan.entries if e.deleted)

        rec = await create_disk_cleanup_record(
            db=db,
            simulated=plan.simulated,
            disk_path=report_before.disk_path,
            disk_used_pct_before=report_before.used_percent,
            disk_used_pct_after=report_after.used_percent,
            total_files_scanned=plan.total_files,
            total_reclaimable_mb=plan.total_reclaimable_mb,
            files_deleted=deleted_count,
            space_recovered_mb=round(recovered_mb, 2),
            errors=plan.errors,
            triggered_by="manual_dashboard",
        )

        return {
            "record_id": rec.id,
            "simulated": plan.simulated,
            "total_files_planned": plan.total_files,
            "total_reclaimable_mb": plan.total_reclaimable_mb,
            "files_deleted": deleted_count,
            "space_recovered_mb": round(recovered_mb, 2),
            "disk_used_pct_before": report_before.used_percent,
            "disk_used_pct_after": report_after.used_percent,
            "executed_at": plan.executed_at,
            "errors": plan.errors,
        }
    finally:
        disk_manager.simulation_mode = orig_sim


@router.get("/disk/history")
async def get_disk_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Retrieve history of disk cleanup operations."""
    records = await get_disk_cleanup_records(db, limit=limit)
    return [
        {
            "id": r.id,
            "ran_at": r.ran_at.isoformat(),
            "simulated": r.simulated,
            "disk_path": r.disk_path,
            "disk_used_pct_before": r.disk_used_pct_before,
            "disk_used_pct_after": r.disk_used_pct_after,
            "total_files_scanned": r.total_files_scanned,
            "total_reclaimable_mb": r.total_reclaimable_mb,
            "files_deleted": r.files_deleted,
            "space_recovered_mb": r.space_recovered_mb,
            "triggered_by": r.triggered_by,
        }
        for r in records
    ]


# ── 5. Root-Cause Diagnosis & Recovery History ────────────────────────────────

@router.get("/rca/recent")
async def get_recent_rca_diagnoses(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List recent structured Root-Cause Diagnoses."""
    records = await get_recent_rcas(db, limit=limit)
    return [
        {
            "id": r.id,
            "incident_id": r.incident_id,
            "root_cause": r.root_cause,
            "confidence": r.confidence,
            "causal_chain": r.causal_chain,
            "remediation_steps": r.remediation_steps,
            "cpu_at_diagnosis": r.cpu_at_diagnosis,
            "memory_mb_at_diagnosis": r.memory_mb_at_diagnosis,
            "system_ram_pct": r.system_ram_pct,
            "disk_pct": r.disk_pct,
            "summary": r.summary,
            "diagnosed_at": r.diagnosed_at.isoformat(),
        }
        for r in records
    ]


@router.get("/rca/{incident_id}")
async def get_rca_for_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve structured Root-Cause Diagnosis for a specific incident."""
    rca = await get_rca_by_incident(db, incident_id)
    if not rca:
        raise HTTPException(status_code=404, detail="No RCA found for this incident.")
    return {
        "id": rca.id,
        "incident_id": rca.incident_id,
        "root_cause": rca.root_cause,
        "confidence": rca.confidence,
        "causal_chain": rca.causal_chain,
        "remediation_steps": rca.remediation_steps,
        "cpu_at_diagnosis": rca.cpu_at_diagnosis,
        "memory_mb_at_diagnosis": rca.memory_mb_at_diagnosis,
        "system_ram_pct": rca.system_ram_pct,
        "disk_pct": rca.disk_pct,
        "summary": rca.summary,
        "diagnosed_at": rca.diagnosed_at.isoformat(),
    }


@router.get("/verifications")
async def get_recovery_verification_audit(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Retrieve post-action verification outcomes and measured metric deltas."""
    records = await get_recovery_verifications(db, limit=limit)
    return [
        {
            "id": r.id,
            "action_id": r.action_id,
            "state": r.state,
            "before_cpu": r.before_cpu,
            "after_cpu": r.after_cpu,
            "cpu_delta": r.cpu_delta,
            "before_memory_mb": r.before_memory_mb,
            "after_memory_mb": r.after_memory_mb,
            "memory_delta_mb": r.memory_delta_mb,
            "description": r.description,
            "verified_at": r.verified_at.isoformat(),
        }
        for r in records
    ]


@router.get("/actions-history")
async def get_healing_actions_history(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Comprehensive audit trail of all executed healing actions with verification states."""
    actions = await get_healing_actions(db, limit=limit)
    return [
        {
            "id": a.id,
            "incident_id": a.incident_id,
            "action_type": a.action_type,
            "pid": a.pid,
            "process_name": a.process_name,
            "simulated": a.simulated,
            "reason": a.reason,
            "before_cpu": a.before_cpu,
            "after_cpu": a.after_cpu,
            "before_memory_mb": a.before_memory_mb,
            "after_memory_mb": a.after_memory_mb,
            "verification_state": a.verification_state,
            "verification_summary": a.verification_summary,
            "verified_at": a.verified_at.isoformat() if a.verified_at else None,
            "executed_at": a.executed_at.isoformat(),
        }
        for a in actions
    ]
