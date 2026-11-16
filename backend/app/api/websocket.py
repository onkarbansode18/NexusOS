"""
Nexus — WebSocket endpoint + background agent orchestrator.
This module:
  1. Runs the monitoring → ML → decision → executor pipeline in a background task.
  2. Broadcasts live metrics + incident events to all connected WebSocket clients.
  3. Persists everything to the DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
import time
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sqlalchemy import select
from app.config import settings
from app.db import (
    AsyncSessionLocal,
    create_incident,
    get_active_incident_for_process,
    get_policy,
    log_action,
    save_system_metrics,
    prune_old_metrics,
    resolve_incident,
    create_rca_diagnosis,
    create_recovery_verification,
    create_disk_cleanup_record,
)
from app.healing import (
    sustained_tracker,
    memory_analyser,
    cooldown_manager,
    recovery_verifier,
    disk_manager,
    rca_engine,
)
from app.db.models import MaintenanceWindowRecord
from app.api.maintenance import is_window_active
from app.decision import DecisionEngine, ActionType
from app.executor import ActionExecutor
from app.ml import update_and_detect, get_history, forecast_breach
from app.ml.llm_summarizer import generate_incident_summary
from app.notifications.alert_service import alert_service
from app.monitoring import MetricsCollector, run_loop, SystemMetrics


logger = logging.getLogger("nexus.ws")

router = APIRouter(tags=["websocket"])

# ── Connection manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self) -> None:
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)
        logger.info("WebSocket connected — total=%d", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)
        logger.info("WebSocket disconnected — total=%d", len(self.active))

    async def broadcast(self, message: dict) -> None:
        if not self.active:
            return
        text = json.dumps(message, default=str)
        dead: Set[WebSocket] = set()
        for ws in list(self.active):
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active.discard(ws)


manager = ConnectionManager()

# ── Shared latest snapshot (for HTTP endpoints that need current state) ────────
_latest_metrics: SystemMetrics | None = None


def get_latest_metrics() -> SystemMetrics | None:
    return _latest_metrics


# ── Background pipeline ───────────────────────────────────────────────────────

_last_disk_check: float = 0.0



async def _verify_and_record_recovery(
    action_id: str,
    incident_id: str,
    action_type: str,
    pid: int,
    process_name: str,
    before_cpu: float | None,
    before_memory_mb: float | None,
    simulated: bool,
) -> None:
    """Asynchronously observe the process after healing action and verify outcome."""
    try:
        ver_res = await recovery_verifier.verify(
            incident_id=incident_id,
            action_type=action_type,
            pid=pid,
            process_name=process_name,
            before_cpu=before_cpu,
            before_memory_mb=before_memory_mb,
            simulated=simulated,
            observation_window_seconds=6.0,
        )
        async with AsyncSessionLocal() as vdb:
            await create_recovery_verification(
                db=vdb,
                action_id=action_id,
                state=ver_res.state,
                before_cpu=ver_res.before_cpu,
                before_memory_mb=ver_res.before_memory_mb,
                after_cpu=ver_res.after_cpu,
                after_memory_mb=ver_res.after_memory_mb,
                cpu_delta=ver_res.cpu_delta,
                memory_delta_mb=ver_res.memory_delta_mb,
                description=ver_res.description,
            )
            if ver_res.state == "verified_improved":
                await resolve_incident(vdb, incident_id)

        await manager.broadcast({
            "event": "recovery_verification",
            "ts": datetime.now(timezone.utc).isoformat(),
            "data": {
                "action_id": action_id,
                "incident_id": incident_id,
                "state": ver_res.state,
                "pid": pid,
                "process_name": process_name,
                "cpu_delta": ver_res.cpu_delta,
                "memory_delta_mb": ver_res.memory_delta_mb,
                "description": ver_res.description,
            },
        })
    except Exception as exc:
        logger.warning("Recovery verification task error: %s", exc)


async def _pipeline_tick(metrics: SystemMetrics) -> None:
    """Run the full Sense → Think → Act → Log → Broadcast cycle."""
    global _latest_metrics, _last_disk_check
    _latest_metrics = metrics

    async with AsyncSessionLocal() as db:
        # ── 1. Persist metrics ────────────────────────────────────────────────
        try:
            await save_system_metrics(db, metrics)
        except Exception as exc:
            logger.error("DB write failed: %s", exc)

        # ── 2. Load current policy ────────────────────────────────────────────
        policy = await get_policy(db)
        engine = DecisionEngine(
            simulation_mode=policy.simulation_mode,
            cpu_warning_pct=policy.cpu_warning_pct,
            cpu_critical_pct=policy.cpu_critical_pct,
            ram_warning_pct=policy.ram_warning_pct,
            ram_critical_pct=policy.ram_critical_pct,
            process_whitelist=policy.process_whitelist or [],
            process_blacklist=policy.process_blacklist or [],
        )
        executor = ActionExecutor(simulation_mode=policy.simulation_mode)

        # ── 3. Broadcast live metrics ─────────────────────────────────────────
        process_payload = []
        for p in metrics.processes:
            h = "healthy"
            if p.cpu_percent >= policy.cpu_critical_pct or p.memory_percent >= policy.ram_critical_pct or p.memory_mb >= 2048:
                h = "critical"
            elif p.cpu_percent >= policy.cpu_warning_pct or p.memory_percent >= policy.ram_warning_pct:
                h = "warning"
            process_payload.append({
                "pid":            p.pid,
                "name":           p.name,
                "cpu_percent":    p.cpu_percent,
                "memory_mb":      p.memory_mb,
                "memory_percent": p.memory_percent,
                "status":         p.status,
                "username":       p.username,
                "created_at":     p.created_at,
                "health_status":  h,
            })

        await manager.broadcast({
            "event": "metrics",
            "ts": metrics.timestamp,
            "data": {
                "cpu_percent":    metrics.cpu_percent,
                "cpu_freq_mhz":   metrics.cpu_freq_mhz,
                "ram_percent":    metrics.ram_percent,
                "ram_used_mb":    metrics.ram_used_mb,
                "ram_total_mb":   metrics.ram_total_mb,
                "disk_percent":   metrics.disk.percent,
                "disk_used_gb":   metrics.disk.used_gb,
                "disk_total_gb":  metrics.disk.total_gb,
                "net_bytes_sent": metrics.network.delta_bytes_sent,
                "net_bytes_recv": metrics.network.delta_bytes_recv,
                "processes":       process_payload,
            },
        })

        # ── 4. ML + Decision per process ──────────────────────────────────────
        for proc in metrics.processes:
            anomaly_results = update_and_detect(
                pid=proc.pid,
                process_name=proc.name,
                cpu_percent=proc.cpu_percent,
                memory_mb=proc.memory_mb,
                memory_percent=proc.memory_percent,
                contamination=settings.anomaly_contamination,
            )

            # Features 1 & 2: Sustained Pressure Tracker & Memory Leak Analyser
            creation_key = f"{proc.pid}_{proc.created_at}"
            sustained_result = sustained_tracker.update(
                pid=proc.pid,
                name=proc.name,
                creation_key=creation_key,
                cpu_percent=proc.cpu_percent,
                memory_mb=proc.memory_mb,
                memory_percent=proc.memory_percent,
            )

            memory_analyser.record_sample(
                pid=proc.pid,
                name=proc.name,
                creation_key=creation_key,
                rss_mb=proc.memory_mb,
                system_ram_percent=metrics.ram_percent,
            )
            mem_finding = memory_analyser.analyse(proc.pid)

            # Forecast (RAM exhaustion per-process)
            mem_history = get_history(proc.pid, "memory_mb")
            forecast = forecast_breach(
                history=mem_history,
                threshold=2048.0,           # 2 GB per-process threshold
                metric="memory_mb",
                process_name=proc.name,
                sample_interval_seconds=settings.metrics_interval_seconds,
                horizon_minutes=settings.forecast_horizon_minutes,
            )

            # Maintenance window check
            # Windows are periods (like nightly backup windows) where autonomous interventions are paused.
            # Outside active windows, normal healing is allowed.
            stmt_maint = select(MaintenanceWindowRecord).where(MaintenanceWindowRecord.active == True)
            res_maint = await db.execute(stmt_maint)
            windows = res_maint.scalars().all()
            healing_allowed = True
            if windows:
                now_utc = datetime.now(timezone.utc)
                # If inside any active maintenance window, pause autonomous healing to protect backups
                inside_pause_window = any(is_window_active(w, now_utc) for w in windows)
                healing_allowed = not inside_pause_window

            decision = engine.evaluate(proc, anomaly_results, forecast, metrics, is_maintenance_allowed=healing_allowed)

            # Gate: require sustained elevation or imminent breach (<= 2 min) before actions
            if decision.action not in (ActionType.NONE, ActionType.ALERT_ONLY):
                is_imminent = bool(forecast and forecast.minutes_until_breach is not None and forecast.minutes_until_breach <= 2.0)
                if not (sustained_result.is_sustained_cpu or sustained_result.is_sustained_memory or is_imminent):
                    decision.action = ActionType.ALERT_ONLY
                    decision.reason += f" [Transient spike — {sustained_result.summary}]"

                # Check cooldown velocity limits and emergency stop
                cd_res = cooldown_manager.check(decision.pid)
                if not cd_res.allowed:
                    decision.action = ActionType.ALERT_ONLY
                    decision.reason += f" [{cd_res.reason}]"

            if decision.action == ActionType.NONE:
                continue

            # ── 5. Execute action ─────────────────────────────────────────────
            result = executor.execute(
                action_type=decision.action,
                pid=decision.pid,
                process_name=decision.process_name,
                reason=decision.reason,
            )
            if result.action_type not in (ActionType.NONE, ActionType.ALERT_ONLY):
                cooldown_manager.record(decision.pid)

            # ── 6. Deduplicate & Persist incident + RCA + action ──────────────
            incident = None
            rca_diag = None
            try:
                # Find active open incident for this process within 5 minutes (prevents duplicate explosion)
                existing_inc = await get_active_incident_for_process(db, decision.pid, decision.process_name)
                if existing_inc:
                    incident = existing_inc
                    incident.severity = decision.severity
                    incident.description = decision.reason
                    await db.commit()
                else:
                    incident = await create_incident(
                        db=db,
                        pid=decision.pid,
                        process_name=decision.process_name,
                        severity=decision.severity,
                        description=decision.reason,
                        anomaly_score=anomaly_results[0].score if anomaly_results else None,
                        prediction=forecast.explanation if forecast else None,
                    )

                # Feature 5: Root-Cause Diagnosis
                rca_diag = rca_engine.diagnose(
                    incident_id=incident.id,
                    proc=proc,
                    system_metrics=metrics,
                    anomaly_results=anomaly_results,
                    forecast=forecast,
                    memory_finding=mem_finding,
                    sustained_result=sustained_result,
                )
                await create_rca_diagnosis(
                    db=db,
                    incident_id=incident.id,
                    root_cause=rca_diag.root_cause,
                    confidence=rca_diag.confidence,
                    causal_chain=[{"factor": c.factor, "evidence": c.evidence, "weight": c.weight} for c in rca_diag.causal_chain],
                    remediation_steps=[{"priority": r.priority, "action": r.action, "description": r.description} for r in rca_diag.remediation_steps],
                    cpu_at_diagnosis=rca_diag.cpu_at_diagnosis,
                    memory_mb_at_diagnosis=rca_diag.memory_mb_at_diagnosis,
                    system_ram_pct=rca_diag.system_ram_pct_at_diagnosis,
                    disk_pct=rca_diag.disk_pct_at_diagnosis,
                    summary=rca_diag.summary,
                )

                # Generate AI summary if not already present
                if not incident.nl_summary:
                    inc_dict = {
                        "id": incident.id,
                        "process_name": decision.process_name,
                        "pid": decision.pid,
                        "severity": decision.severity,
                        "description": decision.reason,
                        "prediction": forecast.explanation if forecast else None,
                        "anomaly_score": anomaly_results[0].score if anomaly_results else None,
                        "root_cause": rca_diag.root_cause,
                    }
                    sum_res = await generate_incident_summary(inc_dict)
                    incident.nl_summary = sum_res.get("summary")
                    incident.nl_slack_message = sum_res.get("slack_message")
                    await db.commit()

                # Feature 6: Critical Condition SMS & Email Alert Notification
                if decision.severity == "critical" or (anomaly_results and anomaly_results[0].score <= -0.80):
                    alert_reason = incident.nl_summary or decision.reason
                    asyncio.create_task(
                        alert_service.send_critical_alert(
                            process_name=decision.process_name,
                            pid=decision.pid,
                            reason=alert_reason,
                            severity=decision.severity,
                            incident_id=incident.id,
                        )
                    )

                act_rec = await log_action(
                    db=db,
                    incident_id=incident.id,
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

                # Feature 1 & 5: Post-Action Recovery Verification (asynchronous)
                if result.action_type != ActionType.NONE:
                    asyncio.create_task(
                        _verify_and_record_recovery(
                            action_id=act_rec.id,
                            incident_id=incident.id,
                            action_type=result.action_type,
                            pid=result.pid,
                            process_name=result.process_name,
                            before_cpu=result.before_cpu,
                            before_memory_mb=result.before_memory_mb,
                            simulated=result.simulated,
                        )
                    )
            except Exception as exc:
                logger.error("Failed to persist incident / RCA: %s", exc)

            # ── 7. Broadcast incident event with RCA ─────────────────────────
            await manager.broadcast({
                "event": "incident",
                "ts": datetime.now(timezone.utc).isoformat(),
                "data": {
                    "id":           incident.id if incident else None,
                    "pid":          decision.pid,
                    "process_name": decision.process_name,
                    "severity":     decision.severity,
                    "action":       decision.action,
                    "reason":       decision.reason,
                    "simulated":    result.simulated,
                    "nl_summary":   incident.nl_summary if incident else None,
                    "root_cause":   rca_diag.root_cause if rca_diag else None,
                    "confidence":   rca_diag.confidence if rca_diag else None,
                },
            })

        # ── 8. Feature 4: Periodic Disk Space & Temp File Monitoring ──────────
        now_mono = time.monotonic()
        if (now_mono - _last_disk_check >= 120.0) or (metrics.disk.percent >= policy.disk_warning_pct):
            _last_disk_check = now_mono
            try:
                disk_rep = await asyncio.to_thread(disk_manager.disk_report)
                await manager.broadcast({
                    "event": "disk_status",
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "data": {
                        "disk_path": disk_rep.disk_path,
                        "used_percent": disk_rep.used_percent,
                        "total_gb": disk_rep.total_gb,
                        "free_gb": disk_rep.free_gb,
                        "total_reclaimable_mb": disk_rep.total_reclaimable_mb,
                        "warning": disk_rep.warning,
                        "critical": disk_rep.critical,
                    }
                })
            except Exception as d_exc:
                logger.warning("Disk periodic scan error: %s", d_exc)

        # ── 9. Auto-Resolution Check: Transition normalized processes to Resolved ──
        try:
            stmt_open = (
                select(IncidentRecord)
                .where(IncidentRecord.status.in_(["open", "investigating", "monitoring"]))
                .order_by(IncidentRecord.detected_at.desc())
                .limit(50)
            )
            res_open = await db.execute(stmt_open)
            open_incidents = res_open.scalars().all()

            if open_incidents:
                proc_by_pid = {p.pid: p for p in metrics.processes}
                now_utc = datetime.now(timezone.utc)

                for inc in open_incidents:
                    inc_dt = inc.detected_at if inc.detected_at.tzinfo else inc.detected_at.replace(tzinfo=timezone.utc)
                    age_seconds = (now_utc - inc_dt).total_seconds()

                    if age_seconds >= 10.0:
                        matching_proc = proc_by_pid.get(inc.pid)

                        if matching_proc is None:
                            inc.status = "resolved"
                            inc.resolved_at = now_utc
                            await db.commit()
                            await manager.broadcast({
                                "event": "incident_resolved",
                                "data": {
                                    "id": inc.id,
                                    "pid": inc.pid,
                                    "process_name": inc.process_name,
                                    "reason": f"Process {inc.process_name} exited normally — workload contention cleared.",
                                    "resolved_at": now_utc.isoformat(),
                                }
                            })
                        elif (matching_proc.cpu_percent < policy.cpu_warning_pct and 
                              matching_proc.memory_percent < policy.ram_warning_pct):
                            inc.status = "resolved"
                            inc.resolved_at = now_utc
                            await db.commit()
                            await manager.broadcast({
                                "event": "incident_resolved",
                                "data": {
                                    "id": inc.id,
                                    "pid": inc.pid,
                                    "process_name": inc.process_name,
                                    "reason": f"Telemetry verified: {inc.process_name} CPU settled to {matching_proc.cpu_percent}% (below {policy.cpu_warning_pct}% threshold). Health recovered.",
                                    "resolved_at": now_utc.isoformat(),
                                }
                            })
        except Exception as res_err:
            logger.debug("Auto-resolution check error: %s", res_err)

        # ── 10. Prune old metrics (keep rolling window) ─────────────────────────
        try:
            await prune_old_metrics(db, keep_minutes=settings.metrics_history_minutes)
        except Exception:
            pass



async def _agent_loop() -> None:
    """Run the monitoring agent in a thread, calling the async pipeline for each tick."""
    collector = MetricsCollector(
        top_processes=settings.top_processes,
        disk_path="C:\\",
    )
    interval = settings.metrics_interval_seconds

    while True:
        try:
            metrics = await asyncio.to_thread(collector.collect)
            await _pipeline_tick(metrics)
        except Exception as exc:
            logger.error("Pipeline error: %s", exc, exc_info=True)
        await asyncio.sleep(interval)


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        # Send the current snapshot immediately on connect
        if _latest_metrics:
            await websocket.send_text(json.dumps({
                "event": "connected",
                "ts": datetime.now(timezone.utc).isoformat(),
                "data": {"message": "Connected to Nexus live stream."},
            }))
        while True:
            # Keep connection alive — actual data is pushed by the pipeline
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"event": "ping", "ts": datetime.now(timezone.utc).isoformat()}))
    except (WebSocketDisconnect, RuntimeError):
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# ── Startup hook (called from main.py) ───────────────────────────────────────

_agent_task: asyncio.Task | None = None


def start_agent_background() -> None:
    """Launch the agent loop as a background asyncio task."""
    global _agent_task
    _agent_task = asyncio.create_task(_agent_loop())
    logger.info("Nexus monitoring agent started as background task.")
