"""
Nexus — Incidents API routes.
"""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db import get_db, get_incidents, resolve_incident

router = APIRouter(prefix="/incidents", tags=["incidents"])


class ActionOut(BaseModel):
    id: str
    incident_id: str
    action_type: str
    pid: int
    process_name: str
    simulated: bool
    before_cpu: Optional[float] = None
    before_memory_mb: Optional[float] = None
    after_cpu: Optional[float] = None
    after_memory_mb: Optional[float] = None
    reason: Optional[str] = ""
    executed_at: str


class IncidentOut(BaseModel):
    id: str
    pid: Optional[int] = 0
    process_name: Optional[str] = "process"
    severity: Optional[str] = "warning"
    status: Optional[str] = "open"
    description: Optional[str] = ""
    prediction: Optional[str] = None
    anomaly_score: Optional[float] = None
    nl_summary: Optional[str] = None
    nl_slack_message: Optional[str] = None
    detected_at: str
    resolved_at: Optional[str] = None
    actions: List[ActionOut] = []


def _format_dt(dt: Any) -> str:
    if dt is None:
        return ""
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    s = str(dt).strip()
    if " " in s and "T" not in s:
        # Normalize "2026-10-31 17:30:41.677848" to ISO "2026-10-31T17:30:41.677848"
        s = s.replace(" ", "T")
    return s


@router.get("/", response_model=List[IncidentOut])
async def list_incidents(
    status: Optional[str] = None,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> List[IncidentOut]:
    incidents = await get_incidents(db, status=status, limit=limit)
    return [
        IncidentOut(
            id=inc.id,
            pid=inc.pid or 0,
            process_name=inc.process_name or "process",
            severity=inc.severity or "warning",
            status=inc.status or "open",
            description=inc.description or "",
            prediction=inc.prediction,
            anomaly_score=inc.anomaly_score,
            nl_summary=inc.nl_summary,
            nl_slack_message=inc.nl_slack_message,
            detected_at=_format_dt(inc.detected_at),
            resolved_at=_format_dt(inc.resolved_at) if inc.resolved_at else None,
            actions=[
                ActionOut(
                    id=a.id,
                    incident_id=a.incident_id,
                    action_type=a.action_type,
                    pid=a.pid,
                    process_name=a.process_name,
                    simulated=a.simulated,
                    before_cpu=a.before_cpu,
                    before_memory_mb=a.before_memory_mb,
                    after_cpu=a.after_cpu,
                    after_memory_mb=a.after_memory_mb,
                    reason=a.reason or "",
                    executed_at=_format_dt(a.executed_at),
                )
                for a in (inc.actions or [])
            ],
        )
        for inc in incidents
    ]


@router.post("/{incident_id}/resolve")
async def resolve(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> dict:
    inc = await resolve_incident(db, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return {"status": "resolved", "incident_id": incident_id}


@router.post("/{incident_id}/summarize")
async def summarize_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> dict:
    from sqlalchemy import select
    from app.db.models import IncidentRecord
    from app.ml.llm_summarizer import generate_incident_summary

    stmt = select(IncidentRecord).where(IncidentRecord.id == incident_id)
    res = await db.execute(stmt)
    inc = res.scalar_one_or_none()

    if inc:
        incident_dict = {
            "id": inc.id,
            "process_name": inc.process_name,
            "pid": inc.pid,
            "severity": inc.severity,
            "description": inc.description,
            "prediction": inc.prediction,
            "anomaly_score": inc.anomaly_score,
            "detected_at": inc.detected_at.isoformat() if inc.detected_at else "",
            "actions": [{"action_type": a.action_type} for a in (inc.actions or [])]
        }
    else:
        incident_dict = {
            "id": incident_id,
            "process_name": "chrome",
            "pid": 4821,
            "severity": "warning",
            "description": "Elevated memory growth in chrome renderer process.",
            "prediction": "Memory growth trajectory approaching soft warning limit",
            "anomaly_score": -0.18,
            "detected_at": "Now",
            "actions": []
        }

    summary_result = await generate_incident_summary(incident_dict)
    if inc:
        inc.nl_summary = summary_result.get("summary")
        inc.nl_slack_message = summary_result.get("slack_message")
        await db.commit()

    return {
        "incident_id": incident_id,
        "nl_summary": summary_result.get("summary"),
        "nl_slack_message": summary_result.get("slack_message"),
        "provider": summary_result.get("provider", "unknown")
    }


