"""
Nexus — Critical Incident Email Alert Service
Dispatches high-deliverability email alerts when critical anomalies occur or when manually tested.
Uses Gmail SMTP with RFC 2822 compliance, proper MIME boundaries, Message-ID, Date headers,
and clean multipart HTML/plain-text to ensure delivery straight to the Primary Inbox.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
import socket
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("nexus.notifications")

SETTINGS_FILE = Path(__file__).parent.parent.parent / "alert_settings.json"


class AlertSettings(BaseModel):
    email: str = Field(default="", description="Target email address for critical alerts")
    email_enabled: bool = Field(default=True, description="Whether Email alerts are enabled")
    critical_threshold_score: float = Field(default=-0.75, description="Anomaly score threshold")
    cooldown_seconds: int = Field(default=180, description="Minimum seconds between alerts for the same process")

    # Gmail SMTP Credentials
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_user: Optional[str] = Field(default=None, description="Sender Gmail address")
    smtp_password: Optional[str] = Field(default=None, description="Gmail 16-character App Password")


class AlertRecord(BaseModel):
    id: str
    timestamp: str
    target_phone: str = ""
    target_email: str
    channel: str = "Email"
    severity: str
    process_name: str
    message: str
    status: str  # "delivered" | "not_configured" | "failed"
    provider: str
    details: Optional[str] = None


class AlertService:
    def __init__(self) -> None:
        self._settings = self._load_settings()
        self._history: List[AlertRecord] = []
        self._last_alert_time: Dict[str, float] = {}
        self._load_history()

    def _load_settings(self) -> AlertSettings:
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
                valid = {k: v for k, v in data.items() if k in AlertSettings.model_fields}
                return AlertSettings(**valid)
            except Exception as e:
                logger.warning("Could not read alert_settings.json, using defaults: %s", e)
        return AlertSettings(
            email=os.getenv("NEXUS_ALERT_EMAIL", ""),
            email_enabled=True,
            smtp_user=os.getenv("SMTP_USER"),
            smtp_password=os.getenv("SMTP_PASSWORD"),
        )

    def _save_settings(self) -> None:
        try:
            SETTINGS_FILE.write_text(self._settings.model_dump_json(indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save alert_settings.json: %s", e)

    def _load_history(self) -> None:
        hist_file = SETTINGS_FILE.parent / "alert_history.json"
        if hist_file.exists():
            try:
                data = json.loads(hist_file.read_text(encoding="utf-8-sig"))
                self._history = [AlertRecord(**item) for item in data][-100:]
            except Exception:
                pass

    def _save_history(self) -> None:
        hist_file = SETTINGS_FILE.parent / "alert_history.json"
        try:
            items = [h.model_dump() for h in self._history[-100:]]
            hist_file.write_text(json.dumps(items, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_settings(self) -> AlertSettings:
        self._settings = self._load_settings()
        return self._settings

    def update_settings(self, updates: Dict[str, Any]) -> AlertSettings:
        cur = self._settings.model_dump()
        for k, v in updates.items():
            if k in cur and v is not None:
                cur[k] = v
        self._settings = AlertSettings(**cur)
        self._save_settings()
        return self._settings

    def get_history(self, limit: int = 50) -> List[AlertRecord]:
        return list(reversed(self._history))[:limit]

    # ── Anti-Spam Compliant SMTP Sender ──────────────────────────────────────

    async def _send_email_smtp(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str,
    ) -> tuple[bool, str]:
        # Always reload fresh settings to pick up UI changes immediately
        self._settings = self._load_settings()
        host = self._settings.smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        port = self._settings.smtp_port or int(os.getenv("SMTP_PORT", "587"))
        user = (self._settings.smtp_user or os.getenv("SMTP_USER", "")).strip()
        password = (self._settings.smtp_password or os.getenv("SMTP_PASSWORD", "")).strip()

        if not (user and password):
            return False, "Sender email and App Password not configured"

        password_clean = password.replace(" ", "")

        # Use MIMEMultipart("alternative") for proper client compatibility
        msg = MIMEMultipart("alternative")
        
        # 1. Standard RFC 2822 Deliverability Headers (prevents spam classifier flagging)
        sender_display = "Nexus OS Resource Guardian"
        msg["From"] = formataddr((sender_display, user))
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        domain = user.split("@")[-1] if "@" in user else "gmail.com"
        msg["Message-ID"] = make_msgid(domain=domain)
        msg["Reply-To"] = formataddr((sender_display, user))
        msg["Return-Path"] = user
        msg["MIME-Version"] = "1.0"
        msg["X-Mailer"] = "NexusOS-Guardian/2.0"
        msg["X-Priority"] = "1"
        msg["Auto-Submitted"] = "auto-generated"

        # 2. Plain Text Fallback
        part_text = MIMEText(body_text, "plain", "utf-8")
        msg.attach(part_text)

        # 3. Clean, Professional HTML Template
        part_html = MIMEText(body_html, "html", "utf-8")
        msg.attach(part_html)

        def _send():
            with smtplib.SMTP(host, port, timeout=14) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(user, password_clean)
                server.sendmail(user, [to_email], msg.as_string())

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _send)
            return True, f"Email delivered to {to_email} via {user}"
        except Exception as e:
            logger.warning("SMTP delivery failed: %s", e)
            return False, f"SMTP error ({user}): {e}"

    # ── Resend HTTPS API Sender (best deliverability, pre-authenticated domain) ─

    async def _send_email_resend(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str,
    ) -> tuple[bool, str]:
        """Send via Resend API — uses pre-authenticated domain, lands in inbox."""
        api_key = os.getenv("RESEND_API_KEY", "").strip()
        if not api_key:
            return False, "RESEND_API_KEY not configured"
        # Use Resend's pre-authenticated domain as from; user's Gmail as reply-to
        # This passes SPF/DKIM/DMARC — no spam folder
        reply_email = (self._settings.smtp_user or os.getenv("SMTP_USER", "")).strip()
        from_address = "NexusOS Guardian <onboarding@resend.dev>"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                payload: dict = {
                    "from": from_address,
                    "to": [to_email],
                    "subject": subject,
                    "text": body_text,
                    "html": body_html,
                }
                if reply_email:
                    payload["reply_to"] = reply_email
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code in (200, 201):
                return True, f"Email delivered via Resend to {to_email}"
            else:
                return False, f"Resend error {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, f"Resend exception: {e}"

    # ── SendGrid HTTPS API Sender (fallback) ──────────────────────────────────

    async def _send_email_sendgrid(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str,
    ) -> tuple[bool, str]:
        """Send via SendGrid HTTPS API — fallback if Resend not configured."""
        api_key = os.getenv("SENDGRID_API_KEY", "").strip()
        if not api_key:
            return False, "SENDGRID_API_KEY not configured"
        from_email = (self._settings.smtp_user or os.getenv("SMTP_USER", "")).strip()
        if not from_email:
            from_email = "noreply@nexusos.app"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "personalizations": [{"to": [{"email": to_email}]}],
                        "from": {"email": from_email, "name": "Nexus OS Resource Guardian"},
                        "reply_to": {"email": from_email, "name": "Nexus OS Resource Guardian"},
                        "subject": subject,
                        "content": [
                            {"type": "text/plain", "value": body_text},
                            {"type": "text/html", "value": body_html},
                        ],
                        "tracking_settings": {
                            "click_tracking": {"enable": False},
                            "open_tracking": {"enable": False},
                        },
                    },
                )
            if resp.status_code in (200, 202):
                return True, f"Email delivered via SendGrid to {to_email}"
            else:
                return False, f"SendGrid error {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            return False, f"SendGrid exception: {e}"

    # ── High-Level Dispatch ───────────────────────────────────────────────────

    async def send_critical_alert(
        self,
        process_name: str,
        pid: int,
        reason: str,
        severity: str = "critical",
        incident_id: Optional[str] = None,
    ) -> Optional[AlertRecord]:
        """Automatically called when a critical condition occurs. Sends email alert."""
        self._settings = self._load_settings()
        now = time.time()
        last_time = self._last_alert_time.get(process_name, 0.0)
        if (now - last_time) < self._settings.cooldown_seconds:
            logger.info("Alert for %s suppressed by cooldown", process_name)
            return None

        self._last_alert_time[process_name] = now
        email = self._settings.email.strip()

        if not email or not self._settings.email_enabled:
            return None

        inc_id = incident_id or f"INC-{int(now)}"
        alert_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        hostname = socket.gethostname()

        # Subject: Clean, professional, NO spam-triggering emojis
        email_subject = f"[Nexus Alert] Critical Anomaly Detected: {process_name} (PID {pid})"

        email_text = (
            f"NEXUS OS RESOURCE GUARDIAN — INCIDENT NOTIFICATION\n"
            f"====================================================\n\n"
            f"Incident ID   : {inc_id}\n"
            f"Target Process: {process_name} (PID: {pid})\n"
            f"Severity      : {severity.upper()}\n"
            f"Host System   : {hostname}\n"
            f"Timestamp     : {alert_time}\n\n"
            f"Diagnostic Summary:\n"
            f"{reason}\n\n"
            f"Autonomous Remediation:\n"
            f"The Nexus Autonomous Self-Healing engine executed safety policies "
            f"to stabilize host system resources.\n\n"
            f"Dashboard: http://localhost:5173/incidents\n\n"
            f"---\n"
            f"Nexus OS Resource Guardian (Automated Operational System Alert)\n"
        )

        email_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Nexus Critical Alert</title>
</head>
<body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F8FAFC; color: #1E293B;">
  <div style="max-width: 600px; margin: 0 auto; background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
    <div style="background: #DC2626; padding: 20px 24px; color: #FFFFFF;">
      <h2 style="margin: 0; font-size: 18px; font-weight: 700; letter-spacing: -0.02em;">Nexus OS Resource Guardian</h2>
      <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">High-Priority System Incident Alert</p>
    </div>
    <div style="padding: 24px;">
      <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 20px;">
        <tr style="border-bottom: 1px solid #F1F5F9;">
          <td style="padding: 8px 0; color: #64748B; font-weight: 600; width: 140px;">Incident ID</td>
          <td style="padding: 8px 0; color: #0F172A; font-family: monospace; font-weight: 700;">{inc_id}</td>
        </tr>
        <tr style="border-bottom: 1px solid #F1F5F9;">
          <td style="padding: 8px 0; color: #64748B; font-weight: 600;">Target Process</td>
          <td style="padding: 8px 0; color: #0F172A; font-weight: 600;">{process_name} (PID: {pid})</td>
        </tr>
        <tr style="border-bottom: 1px solid #F1F5F9;">
          <td style="padding: 8px 0; color: #64748B; font-weight: 600;">Severity</td>
          <td style="padding: 8px 0;"><span style="background: #FEE2E2; color: #DC2626; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700;">{severity.upper()}</span></td>
        </tr>
        <tr style="border-bottom: 1px solid #F1F5F9;">
          <td style="padding: 8px 0; color: #64748B; font-weight: 600;">Host System</td>
          <td style="padding: 8px 0; color: #0F172A;">{hostname}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; color: #64748B; font-weight: 600;">Detection Time</td>
          <td style="padding: 8px 0; color: #0F172A;">{alert_time}</td>
        </tr>
      </table>

      <div style="background: #F8FAFC; border-left: 4px solid #DC2626; padding: 14px 16px; border-radius: 4px; margin-bottom: 20px;">
        <div style="font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase; margin-bottom: 6px;">Root Cause & Diagnostic Summary</div>
        <div style="font-size: 13px; line-height: 1.5; color: #1E293B;">{reason}</div>
      </div>

      <div style="font-size: 13px; color: #475569; line-height: 1.5; margin-bottom: 24px;">
        <strong>Autonomous Action Taken:</strong> The Nexus Autonomous Self-Healing engine applied policy guardrails to protect system performance and prevent cascading resource starvation.
      </div>

      <div style="text-align: center;">
        <a href="http://localhost:5173/incidents" style="display: inline-block; background: #2563EB; color: #FFFFFF; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-size: 13px; font-weight: 600;">Open Live Dashboard</a>
      </div>
    </div>
    <div style="background: #F1F5F9; padding: 14px 24px; font-size: 11px; color: #64748B; border-top: 1px solid #E2E8F0; text-align: center;">
      This operational notification was generated automatically by Nexus OS Resource Guardian running on your system.
    </div>
  </div>
</body>
</html>"""

        return await self._dispatch_email(
            email=email,
            email_subject=email_subject,
            body_text=email_text,
            body_html=email_html,
            process_name=process_name,
            severity=severity,
        )

    async def send_test_alert(self, test_phone: str, test_email: str) -> AlertRecord:
        """Sends an anti-spam compliant test email to verify delivery."""
        self._settings = self._load_settings()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        email = (test_email or self._settings.email).strip()
        hostname = socket.gethostname()

        # Subject: Professional, clean, no emojis
        email_subject = "[Nexus System] Alert Notification Channel Verification"

        email_text = (
            f"NEXUS OS RESOURCE GUARDIAN — ALERT VERIFICATION\n"
            f"=================================================\n\n"
            f"Target Recipient: {email}\n"
            f"Host System     : {hostname}\n"
            f"Verification Time: {now_str}\n\n"
            f"Your emergency alert notification channel has been successfully verified.\n"
            f"You will now automatically receive high-priority alerts whenever system CPU, RAM,\n"
            f"or background process anomalies exceed critical safety thresholds.\n\n"
            f"Live Dashboard: http://localhost:5173\n\n"
            f"---\n"
            f"Nexus OS Resource Guardian (Automated System Notification)\n"
        )

        email_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Nexus Alert Verification</title>
</head>
<body style="margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F8FAFC; color: #1E293B;">
  <div style="max-width: 600px; margin: 0 auto; background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
    <div style="background: #2563EB; padding: 20px 24px; color: #FFFFFF;">
      <h2 style="margin: 0; font-size: 18px; font-weight: 700; letter-spacing: -0.02em;">Nexus OS Resource Guardian</h2>
      <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Emergency Notification Channel Verified</p>
    </div>
    <div style="padding: 24px;">
      <p style="font-size: 14px; color: #0F172A; line-height: 1.5; margin-top: 0;">
        Hello,
      </p>
      <p style="font-size: 13px; color: #334155; line-height: 1.6;">
        Your emergency alert channel has been successfully registered and verified for host system <strong>{hostname}</strong>.
      </p>

      <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin: 20px 0; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px;">
        <tr style="border-bottom: 1px solid #E2E8F0;">
          <td style="padding: 10px 14px; color: #64748B; font-weight: 600; width: 150px;">Registered Email</td>
          <td style="padding: 10px 14px; color: #0F172A; font-weight: 600;">{email}</td>
        </tr>
        <tr style="border-bottom: 1px solid #E2E8F0;">
          <td style="padding: 10px 14px; color: #64748B; font-weight: 600;">Status</td>
          <td style="padding: 10px 14px;"><span style="background: #ECFDF5; color: #059669; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700;">ACTIVE & VERIFIED</span></td>
        </tr>
        <tr>
          <td style="padding: 10px 14px; color: #64748B; font-weight: 600;">Timestamp</td>
          <td style="padding: 10px 14px; color: #0F172A;">{now_str}</td>
        </tr>
      </table>

      <p style="font-size: 13px; color: #334155; line-height: 1.6;">
        Whenever system CPU or memory exceeds critical thresholds or runaway anomalies are detected, an incident report will be delivered directly to this address.
      </p>

      <div style="text-align: center; margin-top: 24px;">
        <a href="http://localhost:5173" style="display: inline-block; background: #2563EB; color: #FFFFFF; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-size: 13px; font-weight: 600;">Open Guardian Console</a>
      </div>
    </div>
    <div style="background: #F1F5F9; padding: 14px 24px; font-size: 11px; color: #64748B; border-top: 1px solid #E2E8F0; text-align: center;">
      This operational notification was generated automatically by Nexus OS Resource Guardian on your local machine.
    </div>
  </div>
</body>
</html>"""

        return await self._dispatch_email(
            email=email,
            email_subject=email_subject,
            body_text=email_text,
            body_html=email_html,
            process_name="System Diagnostic Test",
            severity="test",
        )

    async def _dispatch_email(
        self,
        email: str,
        email_subject: str,
        body_text: str,
        body_html: str,
        process_name: str,
        severity: str,
    ) -> AlertRecord:
        details_list: List[str] = []
        email_delivered = False
        provider_str = "No Gmail credentials configured"

        if email and self._settings.email_enabled:
            smtp_user = (self._settings.smtp_user or os.getenv("SMTP_USER", "")).strip()
            smtp_pass = (self._settings.smtp_password or os.getenv("SMTP_PASSWORD", "")).strip()

            resend_key = os.getenv("RESEND_API_KEY", "").strip()
            sg_key = os.getenv("SENDGRID_API_KEY", "").strip()

            if resend_key:
                # 1st choice: Resend — pre-authenticated domain, best inbox delivery
                ok, msg = await self._send_email_resend(email, email_subject, body_text, body_html)
                details_list.append(msg)
                if ok:
                    email_delivered = True
                    provider_str = "Resend (onboarding@resend.dev)"
                elif sg_key:
                    # 2nd choice: SendGrid fallback
                    ok2, msg2 = await self._send_email_sendgrid(email, email_subject, body_text, body_html)
                    details_list.append(msg2)
                    if ok2:
                        email_delivered = True
                        provider_str = f"SendGrid ({smtp_user})"
                    else:
                        provider_str = f"Email failed: {msg} | {msg2}"
                else:
                    provider_str = f"Email failed: {msg}"
            elif sg_key and smtp_user and smtp_pass:
                # 2nd choice: SendGrid
                ok, msg = await self._send_email_sendgrid(email, email_subject, body_text, body_html)
                details_list.append(msg)
                if ok:
                    email_delivered = True
                    provider_str = f"SendGrid ({smtp_user})"
                else:
                    provider_str = f"Email failed: {msg}"
            elif smtp_user and smtp_pass:
                # Last resort: direct SMTP (works locally, blocked on Render free tier)
                ok, msg = await self._send_email_smtp(email, email_subject, body_text, body_html)
                details_list.append(msg)
                if ok:
                    email_delivered = True
                    provider_str = f"Gmail SMTP ({smtp_user})"
                else:
                    provider_str = f"Email failed: {msg}"
            else:
                details_list.append("No email credentials configured (set RESEND_API_KEY in Render)")
                provider_str = "No email credentials configured"

        overall_status = "delivered" if email_delivered else "not_configured"

        rec = AlertRecord(
            id=f"alt-{int(time.time() * 1000)}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            target_phone="",
            target_email=email or "—",
            channel="Email",
            severity=severity,
            process_name=process_name,
            message=email_subject,
            status=overall_status,
            provider=provider_str,
            details=" | ".join(details_list) if details_list else "No delivery attempted",
        )

        self._history.append(rec)
        self._save_history()
        return rec


# Global singleton instance
alert_service = AlertService()
