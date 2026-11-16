"""
Nexus — Email Alert Notification API Router
Provides endpoints to manage alert email, toggles, and send test email alerts.
"""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.notifications.alert_service import alert_service, AlertSettings, AlertRecord
from app.api.websocket import manager

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertSettingsUpdateRequest(BaseModel):
    email: str = ""
    email_enabled: bool = True
    smtp_user: str = ""
    smtp_password: str = ""


class SendTestAlertRequest(BaseModel):
    phone_number: str = ""
    email: str = ""


@router.get("/settings", response_model=AlertSettings)
async def get_alert_settings() -> AlertSettings:
    """Returns current SMS and Email alert configuration."""
    return alert_service.get_settings()


@router.post("/settings", response_model=AlertSettings)
async def update_alert_settings(req: AlertSettingsUpdateRequest) -> AlertSettings:
    """Updates target phone number, email, and alert toggles."""
    updated = alert_service.update_settings(req.model_dump())
    await manager.broadcast({
        "event": "alert_settings_updated",
        "data": {
            "email": updated.email,
            "email_enabled": updated.email_enabled,
        },
    })
    return updated


@router.post("/test", response_model=AlertRecord)
async def send_test_alert(req: SendTestAlertRequest) -> AlertRecord:
    """Sends an immediate test alert via SMS and Email to verify phone connectivity."""
    if not req.phone_number.strip() and not req.email.strip():
        raise HTTPException(status_code=400, detail="Please enter a valid phone number or email to receive test alert.")

    rec = await alert_service.send_test_alert(
        test_phone=req.phone_number.strip(),
        test_email=req.email.strip(),
    )
    await manager.broadcast({
        "event": "alert_dispatched",
        "data": rec.model_dump(),
    })
    return rec


@router.get("/history", response_model=List[AlertRecord])
async def get_alert_history(limit: int = 50) -> List[AlertRecord]:
    """Returns past alert notification history."""
    return alert_service.get_history(limit=limit)

