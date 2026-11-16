"""
Nexus — Ask Nexus AI Chatbot API
Natural language Q&A about system state powered by Google Gemini.
"""
from __future__ import annotations

import logging
import os
import json
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from datetime import datetime

from app.api.auth import get_current_user
from app.config import settings

router = APIRouter(prefix="/chatbot", tags=["chatbot"])
logger = logging.getLogger("nexus.chatbot")


class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = None
    # Optional live context — frontend passes current metrics snapshot
    context: Optional[dict] = None


class ChatResponse(BaseModel):
    answer: str
    provider: str
    suggested_actions: List[str] = []


SYSTEM_PROMPT = """You are Nexus AI, an intelligent system resource guardian assistant embedded inside the Nexus OS Dashboard.
You have access to real-time system telemetry and incident history.
Your job is to answer user questions about their system in plain, friendly English — like talking to a knowledgeable DevOps engineer.

Guidelines:
- Be concise: 2-4 sentences max unless the user asks for details.
- Reference actual numbers from the telemetry context when available.
- If you spot a problem in the telemetry, proactively mention it.
- Suggest actionable steps the user can take inside the Nexus dashboard.
- Never say "I don't have access to real-time data" — the telemetry is provided in the context.
- If a Gemini API key is not configured, still answer helpfully based on what you know.
"""


def _build_context_text(context: Optional[dict]) -> str:
    if not context:
        return "No live telemetry context provided."
    lines = ["=== CURRENT SYSTEM TELEMETRY ==="]
    if "cpu_percent" in context:
        lines.append(f"CPU Usage: {context['cpu_percent']:.1f}%")
    if "ram_percent" in context:
        lines.append(f"RAM Usage: {context['ram_percent']:.1f}% ({context.get('ram_used_mb', 0)/1024:.1f} GB / {context.get('ram_total_mb', 8192)/1024:.1f} GB)")
    if "disk_percent" in context:
        lines.append(f"Disk Usage: {context['disk_percent']:.1f}%")
    if "top_processes" in context and context["top_processes"]:
        lines.append("Top Processes by Memory:")
        for p in context["top_processes"][:5]:
            lines.append(f"  - {p.get('name','?')} (PID {p.get('pid','?')}): CPU {p.get('cpu_percent',0):.1f}%, RAM {p.get('memory_mb',0):.0f} MB [{p.get('health_status','healthy')}]")
    if "incidents" in context and context["incidents"]:
        lines.append("Active Incidents:")
        for inc in context["incidents"][:3]:
            lines.append(f"  - [{inc.get('severity','?').upper()}] {inc.get('title', inc.get('description','?'))} (Status: {inc.get('status','?')})")
    if "recent_actions" in context and context["recent_actions"]:
        lines.append("Recent Healing Actions:")
        for act in context["recent_actions"][:3]:
            lines.append(f"  - {act.get('action_type','?')} on {act.get('process_name','?')} at {act.get('executed_at','?')}")
    lines.append(f"Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    return "\n".join(lines)


def _fallback_answer(question: str, context: Optional[dict]) -> ChatResponse:
    """Template-based answer when Gemini API key is not configured."""
    q_lower = question.lower()
    ctx = context or {}

    if any(w in q_lower for w in ["slow", "lag", "freeze", "why", "problem", "issue"]):
        cpu = ctx.get("cpu_percent", 0)
        ram = ctx.get("ram_percent", 0)
        procs = ctx.get("top_processes", [])
        heavy = [p for p in procs if p.get("health_status") in ("critical", "warning")]
        if cpu > 85:
            answer = f"Your CPU is at {cpu:.0f}%, which is very high. Check the Processes page for processes using excessive CPU and consider using the Throttle or Renice actions."
        elif ram > 85:
            answer = f"Your RAM is at {ram:.0f}%. This is likely causing slowness. Use the Smart Hibernator to trim memory from idle apps, or check for memory leaks in the Incidents page."
        elif heavy:
            names = ", ".join(p["name"] for p in heavy[:3])
            answer = f"Nexus has flagged these processes as problematic: {names}. Check the Incidents page for details and recommended healing actions."
        else:
            answer = f"System resources look relatively normal (CPU: {cpu:.0f}%, RAM: {ram:.0f}%). If you're experiencing slowness, it might be a brief spike. Monitor the Dashboard for the next few minutes."
    elif any(w in q_lower for w in ["memory", "ram", "leak"]):
        ram = ctx.get("ram_percent", 0)
        answer = f"Current RAM usage is {ram:.0f}%. Check the Predictions page for memory growth trends and use the Smart Hibernator to free RAM from idle background apps."
    elif any(w in q_lower for w in ["cpu", "processor", "core"]):
        cpu = ctx.get("cpu_percent", 0)
        answer = f"CPU is currently at {cpu:.0f}%. Visit the Processes page, sort by CPU, and use Renice or Throttle on any process consuming too much."
    elif any(w in q_lower for w in ["disk", "storage", "space"]):
        disk = ctx.get("disk_percent", 0)
        answer = f"Disk is at {disk:.0f}% capacity. Use the Healing Activity page to run a disk cleanup and reclaim space from temp files and caches."
    elif any(w in q_lower for w in ["incident", "alert", "warn"]):
        incidents = ctx.get("incidents", [])
        open_inc = [i for i in incidents if i.get("status") in ("open", "investigating", "monitoring")]
        if open_inc:
            answer = f"There are {len(open_inc)} active incident(s). The most recent: {open_inc[0].get('title', 'Unknown incident')}. Visit the Incidents page to review and take action."
        else:
            answer = "No active incidents at the moment. All monitored processes are within normal thresholds."
    elif any(w in q_lower for w in ["safe", "kill", "terminate", "close"]):
        answer = "Before killing a process, check if it's on the Protected Blacklist in Settings. Nexus will prevent you from accidentally killing critical system services. Use the Process Drawer to see details before acting."
    elif any(w in q_lower for w in ["hibernate", "sleep", "suspend", "idle"]):
        answer = "Use the Smart Hibernator page to trim RAM from idle apps. Nexus will trim their working set memory without closing them — they'll wake up instantly when you switch back."
    else:
        cpu = ctx.get("cpu_percent", 0)
        ram = ctx.get("ram_percent", 0)
        answer = f"I'm Nexus AI, your system guardian. Right now: CPU is at {cpu:.0f}%, RAM at {ram:.0f}%. Everything looks stable. Ask me anything about your system performance or processes!"

    return ChatResponse(
        answer=answer,
        provider="template",
        suggested_actions=["Check Processes page", "View Incidents", "Open Smart Hibernator"],
    )


@router.post("/ask", response_model=ChatResponse)
async def ask_nexus(
    req: ChatRequest,
    _user: str = Depends(get_current_user),
):
    """Answer a natural language question about system state using Gemini."""
    raw_key = (settings.gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

    if not raw_key or raw_key.lower().startswith("your_") or "placeholder" in raw_key.lower():
        return _fallback_answer(req.question, req.context)

    context_text = _build_context_text(req.context)
    history = req.history or []

    # Build conversation for Gemini
    contents = []
    # System context as first user message
    contents.append({
        "role": "user",
        "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{context_text}"}]
    })
    contents.append({
        "role": "model",
        "parts": [{"text": "Understood. I'm Nexus AI, ready to help you understand your system. What would you like to know?"}]
    })
    # Previous history
    for msg in history[-6:]:  # keep last 6 messages for context window
        contents.append({
            "role": "user" if msg.role == "user" else "model",
            "parts": [{"text": msg.content}]
        })
    # Current question
    contents.append({
        "role": "user",
        "parts": [{"text": req.question}]
    })

    try:
        import httpx
        models_to_try = ["gemini-1.5-flash", "gemini-2.0-flash-exp", "gemini-1.5-pro"]

        async with httpx.AsyncClient(timeout=15.0) as client:
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={raw_key}"
                payload = {
                    "contents": contents,
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 512,
                    }
                }
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    answer_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

                    # Try to extract suggested_actions if Gemini returns them
                    suggested = []
                    if "processes page" in answer_text.lower():
                        suggested.append("Open Processes")
                    if "incident" in answer_text.lower():
                        suggested.append("View Incidents")
                    if "hibernat" in answer_text.lower():
                        suggested.append("Open Hibernator")
                    if "predict" in answer_text.lower():
                        suggested.append("View Predictions")
                    if "setting" in answer_text.lower():
                        suggested.append("Open Settings")

                    return ChatResponse(
                        answer=answer_text,
                        provider=f"gemini ({model_name})",
                        suggested_actions=suggested,
                    )
                else:
                    logger.warning(f"Gemini {model_name} returned {resp.status_code}: {resp.text[:200]}")

    except Exception as e:
        logger.warning(f"Gemini chatbot call failed: {e}")

    # Fallback if all Gemini calls fail
    return _fallback_answer(req.question, req.context)

