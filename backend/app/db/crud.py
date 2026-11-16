"""
Nexus DB — CRUD helpers for all models.
Thin async functions wrapping SQLAlchemy — business logic stays in services.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.monitoring.agent import SystemMetrics as CollectedMetrics
from .models import (
    HealingActionRecord,
    IncidentRecord,
    PolicyRecord,
    ProcessMetricsRecord,
    SystemMetricsRecord,
    RootCauseDiagnosisRecord,
    DiskCleanupRecord,
    RecoveryVerificationRecord,
)


# ── SystemMetrics ─────────────────────────────────────────────────────────────

async def save_system_metrics(
    db: AsyncSession, m: CollectedMetrics
) -> SystemMetricsRecord:
    """Persist one polling snapshot."""
    record = SystemMetricsRecord(
        timestamp=datetime.fromisoformat(m.timestamp),
        cpu_percent=m.cpu_percent,
        cpu_freq_mhz=m.cpu_freq_mhz,
        cpu_count_logical=m.cpu_count_logical,
        ram_total_mb=m.ram_total_mb,
        ram_used_mb=m.ram_used_mb,
        ram_percent=m.ram_percent,
        swap_total_mb=m.swap_total_mb,
        swap_used_mb=m.swap_used_mb,
        swap_percent=m.swap_percent,
        disk_path=m.disk.path,
        disk_total_gb=m.disk.total_gb,
        disk_used_gb=m.disk.used_gb,
        disk_percent=m.disk.percent,
        net_bytes_sent=m.network.delta_bytes_sent,
        net_bytes_recv=m.network.delta_bytes_recv,
    )
    db.add(record)
    await db.flush()   # get the auto-id without committing

    # Persist per-process snapshots
    for p in m.processes:
        db.add(ProcessMetricsRecord(
            system_metrics_id=record.id,
            timestamp=record.timestamp,
            pid=p.pid,
            name=p.name,
            status=p.status,
            username=p.username,
            cpu_percent=p.cpu_percent,
            memory_mb=p.memory_mb,
            memory_percent=p.memory_percent,
            num_threads=p.num_threads,
        ))

    await db.commit()
    return record


async def get_recent_system_metrics(
    db: AsyncSession, minutes: int = 60
) -> Sequence[SystemMetricsRecord]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    result = await db.execute(
        select(SystemMetricsRecord)
        .where(SystemMetricsRecord.timestamp >= cutoff)
        .order_by(SystemMetricsRecord.timestamp.desc())
    )
    return result.scalars().all()


async def prune_old_metrics(db: AsyncSession, keep_minutes: int = 60) -> int:
    """Delete metrics older than keep_minutes. Returns rows deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=keep_minutes)
    result = await db.execute(
        delete(SystemMetricsRecord).where(SystemMetricsRecord.timestamp < cutoff)
    )
    await db.commit()
    return result.rowcount


# ── Process history ───────────────────────────────────────────────────────────

async def get_process_history(
    db: AsyncSession, pid: int, minutes: int = 30
) -> Sequence[ProcessMetricsRecord]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    result = await db.execute(
        select(ProcessMetricsRecord)
        .where(ProcessMetricsRecord.pid == pid, ProcessMetricsRecord.timestamp >= cutoff)
        .order_by(ProcessMetricsRecord.timestamp)
    )
    return result.scalars().all()


# ── Incidents ─────────────────────────────────────────────────────────────────

async def create_incident(
    db: AsyncSession,
    pid: int,
    process_name: str,
    severity: str,
    description: str,
    anomaly_score: float | None = None,
    prediction: str | None = None,
) -> IncidentRecord:
    inc = IncidentRecord(
        pid=pid,
        process_name=process_name,
        severity=severity,
        description=description,
        anomaly_score=anomaly_score,
        prediction=prediction,
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    return inc


async def get_incidents(
    db: AsyncSession,
    status: Optional[str] = None,
    limit: int = 500,
) -> Sequence[IncidentRecord]:
    q = (
        select(IncidentRecord)
        .options(selectinload(IncidentRecord.actions))
        .order_by(IncidentRecord.detected_at.desc())
        .limit(limit)
    )
    if status:
        q = q.where(IncidentRecord.status == status)
    return (await db.execute(q)).scalars().all()


async def resolve_incident(db: AsyncSession, incident_id: str) -> Optional[IncidentRecord]:
    inc = await db.get(IncidentRecord, incident_id)
    if inc:
        inc.status = "resolved"
        inc.resolved_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(inc)
    return inc


# ── Healing Actions ───────────────────────────────────────────────────────────

async def log_action(
    db: AsyncSession,
    incident_id: str,
    action_type: str,
    pid: int,
    process_name: str,
    simulated: bool,
    reason: str,
    before_cpu: float | None = None,
    before_memory_mb: float | None = None,
    after_cpu: float | None = None,
    after_memory_mb: float | None = None,
) -> HealingActionRecord:
    action = HealingActionRecord(
        incident_id=incident_id,
        action_type=action_type,
        pid=pid,
        process_name=process_name,
        simulated=simulated,
        reason=reason,
        before_cpu=before_cpu,
        before_memory_mb=before_memory_mb,
        after_cpu=after_cpu,
        after_memory_mb=after_memory_mb,
    )
    db.add(action)
    await db.commit()
    await db.refresh(action)
    return action


# ── Policy ────────────────────────────────────────────────────────────────────

async def get_policy(db: AsyncSession) -> PolicyRecord:
    policy = await db.get(PolicyRecord, 1)
    if policy is None:
        policy = PolicyRecord(id=1)
        db.add(policy)
        await db.commit()
        await db.refresh(policy)
    return policy


async def update_policy(db: AsyncSession, **kwargs) -> PolicyRecord:
    policy = await get_policy(db)
    for key, value in kwargs.items():
        if hasattr(policy, key):
            setattr(policy, key, value)
    await db.commit()
    await db.refresh(policy)
    return policy


# ── Incident Deduplication Helper ─────────────────────────────────────────────

async def get_active_incident_for_process(
    db: AsyncSession,
    pid: int,
    process_name: str,
    max_age_seconds: int = 300,
) -> Optional[IncidentRecord]:
    """
    Finds an unresolved incident for the same process PID within the max_age window.
    Prevents incident explosion / duplicate record creation for sustained events.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    stmt = (
        select(IncidentRecord)
        .where(
            IncidentRecord.pid == pid,
            IncidentRecord.process_name == process_name,
            IncidentRecord.status == "open",
            IncidentRecord.detected_at >= cutoff,
        )
        .order_by(IncidentRecord.detected_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ── Root Cause Diagnosis CRUD ─────────────────────────────────────────────────

async def create_rca_diagnosis(
    db: AsyncSession,
    incident_id: str,
    root_cause: str,
    confidence: float,
    causal_chain: list | None = None,
    remediation_steps: list | None = None,
    cpu_at_diagnosis: float | None = None,
    memory_mb_at_diagnosis: float | None = None,
    system_ram_pct: float | None = None,
    disk_pct: float | None = None,
    summary: str | None = None,
) -> RootCauseDiagnosisRecord:
    rec = RootCauseDiagnosisRecord(
        incident_id=incident_id,
        root_cause=root_cause,
        confidence=confidence,
        causal_chain=causal_chain or [],
        remediation_steps=remediation_steps or [],
        cpu_at_diagnosis=cpu_at_diagnosis,
        memory_mb_at_diagnosis=memory_mb_at_diagnosis,
        system_ram_pct=system_ram_pct,
        disk_pct=disk_pct,
        summary=summary,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def get_rca_by_incident(
    db: AsyncSession, incident_id: str
) -> Optional[RootCauseDiagnosisRecord]:
    stmt = (
        select(RootCauseDiagnosisRecord)
        .where(RootCauseDiagnosisRecord.incident_id == incident_id)
        .order_by(RootCauseDiagnosisRecord.diagnosed_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_recent_rcas(
    db: AsyncSession, limit: int = 50
) -> Sequence[RootCauseDiagnosisRecord]:
    stmt = (
        select(RootCauseDiagnosisRecord)
        .order_by(RootCauseDiagnosisRecord.diagnosed_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Disk Cleanup CRUD ─────────────────────────────────────────────────────────

async def create_disk_cleanup_record(
    db: AsyncSession,
    simulated: bool,
    disk_path: str | None = None,
    disk_used_pct_before: float | None = None,
    disk_used_pct_after: float | None = None,
    total_files_scanned: int = 0,
    total_reclaimable_mb: float = 0.0,
    files_deleted: int = 0,
    space_recovered_mb: float = 0.0,
    errors: list | None = None,
    triggered_by: str = "manual",
) -> DiskCleanupRecord:
    rec = DiskCleanupRecord(
        simulated=simulated,
        disk_path=disk_path,
        disk_used_pct_before=disk_used_pct_before,
        disk_used_pct_after=disk_used_pct_after,
        total_files_scanned=total_files_scanned,
        total_reclaimable_mb=total_reclaimable_mb,
        files_deleted=files_deleted,
        space_recovered_mb=space_recovered_mb,
        errors=errors or [],
        triggered_by=triggered_by,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def get_disk_cleanup_records(
    db: AsyncSession, limit: int = 50
) -> Sequence[DiskCleanupRecord]:
    stmt = (
        select(DiskCleanupRecord)
        .order_by(DiskCleanupRecord.ran_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Recovery Verification CRUD ────────────────────────────────────────────────

async def create_recovery_verification(
    db: AsyncSession,
    action_id: str,
    state: str,
    before_cpu: float | None = None,
    before_memory_mb: float | None = None,
    after_cpu: float | None = None,
    after_memory_mb: float | None = None,
    cpu_delta: float | None = None,
    memory_delta_mb: float | None = None,
    description: str | None = None,
) -> RecoveryVerificationRecord:
    rec = RecoveryVerificationRecord(
        action_id=action_id,
        state=state,
        before_cpu=before_cpu,
        before_memory_mb=before_memory_mb,
        after_cpu=after_cpu,
        after_memory_mb=after_memory_mb,
        cpu_delta=cpu_delta,
        memory_delta_mb=memory_delta_mb,
        description=description,
    )
    db.add(rec)

    # Also update the parent HealingActionRecord
    action = await db.get(HealingActionRecord, action_id)
    if action:
        action.verification_state = state
        action.verification_summary = description
        action.verified_at = datetime.now(timezone.utc)
        if after_cpu is not None:
            action.after_cpu = after_cpu
        if after_memory_mb is not None:
            action.after_memory_mb = after_memory_mb

    await db.commit()
    await db.refresh(rec)
    return rec


async def get_action_by_id(
    db: AsyncSession, action_id: str
) -> Optional[HealingActionRecord]:
    return await db.get(HealingActionRecord, action_id)


async def get_healing_actions(
    db: AsyncSession, limit: int = 100
) -> Sequence[HealingActionRecord]:
    stmt = (
        select(HealingActionRecord)
        .order_by(HealingActionRecord.executed_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_recovery_verifications(
    db: AsyncSession, limit: int = 50
) -> Sequence[RecoveryVerificationRecord]:
    stmt = (
        select(RecoveryVerificationRecord)
        .order_by(RecoveryVerificationRecord.verified_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

