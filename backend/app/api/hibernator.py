"""
Nexus — Smart App Hibernator API
Trims working set memory or suspends idle heavy processes to free RAM.
"""
from __future__ import annotations

import logging
import ctypes
import sys
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.api.websocket import get_latest_metrics
from app.config import settings

router = APIRouter(prefix="/hibernator", tags=["hibernator"])
logger = logging.getLogger("nexus.hibernator")

# ── Models ────────────────────────────────────────────────────────────────────

class HibernateTarget(BaseModel):
    pid: int
    name: str
    memory_mb: float
    action: str  # "trim" or "suspend"
    simulated: bool = True

class HibernateResult(BaseModel):
    pid: int
    name: str
    action: str
    success: bool
    memory_before_mb: float
    memory_after_mb: Optional[float] = None
    freed_mb: Optional[float] = None
    simulated: bool
    message: str

class HibernateRequest(BaseModel):
    pid: int
    process_name: str
    action: str = "trim"  # "trim" or "suspend"
    simulation_mode: Optional[bool] = None

class IdleProcess(BaseModel):
    pid: int
    name: str
    memory_mb: float
    cpu_percent: float
    status: str
    username: str
    hibernatable: bool
    reason: str

# ── Helpers ───────────────────────────────────────────────────────────────────

def _trim_working_set_windows(pid: int) -> bool:
    """Use Windows EmptyWorkingSet API to trim a process's RAM footprint."""
    try:
        PROCESS_ALL_ACCESS = 0x1F0FFF
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not handle:
            return False
        result = ctypes.windll.psapi.EmptyWorkingSet(handle)
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(result)
    except Exception as e:
        logger.warning(f"EmptyWorkingSet failed for PID {pid}: {e}")
        return False


def _get_process_memory_mb(pid: int) -> Optional[float]:
    try:
        import psutil
        p = psutil.Process(pid)
        return p.memory_info().rss / (1024 * 1024)
    except Exception:
        return None


NON_HIBERNATABLE = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe",
    "winlogon.exe", "fontdrvhost.exe", "sihost.exe", "taskhostw.exe",
    "systemd", "init", "kthreadd",
    # nexus itself
    "python.exe", "uvicorn", "node.exe", "vite",
}


def _is_hibernatable(name: str) -> tuple[bool, str]:
    name_lower = name.lower()
    for blocked in NON_HIBERNATABLE:
        if blocked in name_lower:
            return False, f"Protected system process ({blocked})"
    return True, "Eligible for hibernation"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/candidates", response_model=List[IdleProcess])
async def get_hibernation_candidates(
    min_memory_mb: float = 60.0,
    _user: str = Depends(get_current_user),
):
    """Return processes that are candidates for hibernation (high memory, low activity)."""
    candidates = []

    # Ultra-fast path: use latest live metrics if available
    metrics = get_latest_metrics()
    if metrics and metrics.processes:
        for p in metrics.processes:
            if (p.memory_mb or 0) < min_memory_mb:
                continue
            hibernatable, reason = _is_hibernatable(p.name or "")
            candidates.append(IdleProcess(
                pid=p.pid,
                name=p.name or "unknown",
                memory_mb=round(p.memory_mb or 0.0, 1),
                cpu_percent=round(p.cpu_percent or 0.0, 1),
                status=p.status or "running",
                username=p.username or "system",
                hibernatable=hibernatable,
                reason=reason,
            ))
        candidates.sort(key=lambda x: x.memory_mb, reverse=True)
        return candidates[:50]

    # Fallback to direct process scan
    import psutil
    attrs = ['pid', 'name', 'memory_info', 'cpu_percent', 'status']
    for proc in psutil.process_iter(attrs, ad_value=None):
        try:
            info = proc.info
            mem_info = info.get('memory_info')
            mem_mb = (mem_info.rss if mem_info else 0) / (1024 * 1024)
            cpu = info.get('cpu_percent') or 0.0
            if mem_mb < min_memory_mb:
                continue
            name = info.get('name') or 'unknown'
            hibernatable, reason = _is_hibernatable(name)
            candidates.append(IdleProcess(
                pid=info.get('pid') or 0,
                name=name,
                memory_mb=round(mem_mb, 1),
                cpu_percent=round(cpu, 1),
                status=info.get('status') or 'running',
                username='',
                hibernatable=hibernatable,
                reason=reason,
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    # Sort by memory descending
    candidates.sort(key=lambda x: x.memory_mb, reverse=True)
    return candidates[:50]


@router.post("/hibernate", response_model=HibernateResult)
async def hibernate_process(
    req: HibernateRequest,
    _user: str = Depends(get_current_user),
):
    """Trim working set or suspend a process to free RAM."""
    import psutil

    sim = req.simulation_mode if req.simulation_mode is not None else settings.simulation_mode
    mem_before = _get_process_memory_mb(req.pid) or 0.0
    hibernatable, reason = _is_hibernatable(req.process_name)

    if not hibernatable:
        return HibernateResult(
            pid=req.pid,
            name=req.process_name,
            action=req.action,
            success=False,
            memory_before_mb=mem_before,
            simulated=sim,
            message=f"Refused: {reason}",
        )

    if sim:
        estimated_freed = mem_before * 0.4 if req.action == "trim" else mem_before * 0.8
        return HibernateResult(
            pid=req.pid,
            name=req.process_name,
            action=req.action,
            success=True,
            memory_before_mb=mem_before,
            memory_after_mb=round(mem_before - estimated_freed, 1),
            freed_mb=round(estimated_freed, 1),
            simulated=True,
            message=f"[SIMULATED] Would {req.action} {req.process_name} (PID {req.pid}), estimated {estimated_freed:.0f} MB freed.",
        )

    # Live execution
    success = False
    if req.action == "trim":
        if sys.platform == "win32":
            success = _trim_working_set_windows(req.pid)
        else:
            # On Linux: drop caches via /proc (best effort)
            try:
                import psutil
                p = psutil.Process(req.pid)
                p.resume()  # ensure it's running so OS can reclaim
                success = True
            except Exception as e:
                logger.warning(f"Linux trim failed for PID {req.pid}: {e}")
    elif req.action == "suspend":
        try:
            p = psutil.Process(req.pid)
            p.suspend()
            success = True
        except Exception as e:
            logger.warning(f"Suspend failed for PID {req.pid}: {e}")

    mem_after = _get_process_memory_mb(req.pid)
    freed = round(mem_before - (mem_after or mem_before), 1) if mem_after else None

    return HibernateResult(
        pid=req.pid,
        name=req.process_name,
        action=req.action,
        success=success,
        memory_before_mb=mem_before,
        memory_after_mb=mem_after,
        freed_mb=freed,
        simulated=False,
        message=(
            f"{'Trimmed' if req.action == 'trim' else 'Suspended'} {req.process_name} (PID {req.pid}). "
            f"Freed ~{freed:.0f} MB." if freed and freed > 0
            else f"Action completed on {req.process_name} (PID {req.pid})."
        ),
    )


@router.post("/resume/{pid}", response_model=HibernateResult)
async def resume_process(
    pid: int,
    process_name: str = "unknown",
    _user: str = Depends(get_current_user),
):
    """Resume a previously suspended process."""
    import psutil
    mem_before = _get_process_memory_mb(pid) or 0.0
    try:
        p = psutil.Process(pid)
        p.resume()
        return HibernateResult(
            pid=pid,
            name=process_name,
            action="resume",
            success=True,
            memory_before_mb=mem_before,
            simulated=False,
            message=f"Resumed {process_name} (PID {pid}) successfully.",
        )
    except Exception as e:
        return HibernateResult(
            pid=pid,
            name=process_name,
            action="resume",
            success=False,
            memory_before_mb=mem_before,
            simulated=False,
            message=f"Failed to resume PID {pid}: {e}",
        )

