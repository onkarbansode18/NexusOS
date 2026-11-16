"""
Nexus 2.0 — Application-Aware Resource Management
Mode Manager: Orchestrates the four intelligent operating modes:
- Gaming Mode
- Study Mode
- Meeting Mode
- Battery Saver Mode
Handles mode activation, switching, state restoration, battery telemetry,
and audit history persistence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import psutil
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApplicationModeRecord, ApplicationModeHistoryRecord
from app.executor.actions import ActionExecutor

logger = logging.getLogger("nexus.mode_manager")


class OperatingModeType:
    GAMING = "gaming"
    STUDY = "study"
    MEETING = "meeting"
    BATTERY_SAVER = "battery_saver"


DEFAULT_MODE_CONFIGS: Dict[str, Dict[str, Any]] = {
    OperatingModeType.GAMING: {
        "name": "Gaming Mode",
        "description": "Dedicates maximum system resources to your target game. Protects game processes, audio, and controller input while reducing priority on non-essential background tasks.",
        "icon": "Gamepad2",
        "protected_categories": ["Gaming", "System"],
        "protected_apps": ["steam.exe", "epicgameslauncher.exe", "discord.exe"],
        "protected_processes": ["audiodg.exe", "steam.exe"],
        "throttle_background": True,
        "allowed_actions": ["renice", "restore_priority"],
        "target_app_id": None,
    },
    OperatingModeType.STUDY: {
        "name": "Study Mode",
        "description": "Optimizes responsiveness for development and learning workflows. Protects code editors, compilers, terminals, research browsers, and documentation tools.",
        "icon": "BookOpen",
        "protected_categories": ["Development", "Education", "Browsing", "System"],
        "protected_apps": ["code.exe", "idea64.exe", "windowsterminal.exe", "notion.exe", "anki.exe"],
        "protected_processes": ["wt.exe", "powershell.exe", "conhost.exe"],
        "throttle_background": True,
        "allowed_actions": ["renice", "restore_priority"],
        "target_app_id": None,
    },
    OperatingModeType.MEETING: {
        "name": "Meeting Mode",
        "description": "Guarantees stutter-free audio and video conferencing. Strictly protects Zoom, Teams, Meet, and microphone/camera subsystems. Process termination or suspension is entirely forbidden.",
        "icon": "Video",
        "protected_categories": ["Communication", "System"],
        "protected_apps": ["zoom.exe", "teams.exe", "ms-teams.exe", "slack.exe", "discord.exe"],
        "protected_processes": ["audiodg.exe", "svchost.exe"],
        "throttle_background": True,
        "allowed_actions": ["renice", "restore_priority"],  # NO suspend, NO kill
        "target_app_id": None,
    },
    OperatingModeType.BATTERY_SAVER: {
        "name": "Battery Saver Mode",
        "description": "Extends laptop battery endurance by suppressing aggressive background resource usage, lowering background scheduling priorities, and monitoring battery discharge.",
        "icon": "BatteryCharging",
        "protected_categories": ["System"],
        "protected_apps": [],
        "protected_processes": ["explorer.exe", "dwm.exe"],
        "throttle_background": True,
        "allowed_actions": ["renice", "restore_priority"],
        "target_app_id": None,
    },
}


class ModeManager:
    """
    Manages active operating modes and ensures previous priority settings are
    faithfully restored upon mode deactivation or switching.
    """

    def __init__(self) -> None:
        self._active_mode_id: Optional[str] = None
        self._active_config: Dict[str, Any] = {}
        self._target_app_id: Optional[str] = None
        self._activated_at: Optional[str] = None

        # Tracks original priority of processes modified during active mode
        # {pid: original_priority_string}
        self._modified_priorities: Dict[int, str] = {}

    @property
    def active_mode_id(self) -> Optional[str]:
        return self._active_mode_id

    @property
    def is_mode_active(self) -> bool:
        return self._active_mode_id is not None

    def get_active_mode_info(self) -> Dict[str, Any]:
        """Returns details about the currently active operating mode."""
        if not self._active_mode_id:
            return {
                "is_active": False,
                "mode_id": None,
                "name": "Standard / Balanced",
                "description": "Normal system resource management. No application mode active.",
                "target_app_id": None,
                "activated_at": None,
                "battery": self.get_battery_status(),
                "modified_processes_count": len(self._modified_priorities),
            }

        cfg = DEFAULT_MODE_CONFIGS.get(self._active_mode_id, {})
        return {
            "is_active": True,
            "mode_id": self._active_mode_id,
            "name": cfg.get("name", self._active_mode_id.capitalize()),
            "description": cfg.get("description", ""),
            "icon": cfg.get("icon", "Sliders"),
            "target_app_id": self._target_app_id,
            "activated_at": self._activated_at,
            "configuration": self._active_config,
            "battery": self.get_battery_status(),
            "modified_processes_count": len(self._modified_priorities),
        }

    def get_all_modes(self) -> List[Dict[str, Any]]:
        """Returns all available operating modes and their configurations."""
        modes = []
        for mid, cfg in DEFAULT_MODE_CONFIGS.items():
            is_active = (self._active_mode_id == mid)
            modes.append({
                "id": mid,
                "name": cfg["name"],
                "description": cfg["description"],
                "icon": cfg.get("icon", "Sliders"),
                "is_active": is_active,
                "protected_categories": cfg.get("protected_categories", []),
                "protected_apps": cfg.get("protected_apps", []),
                "target_app_id": self._target_app_id if is_active else None,
                "activated_at": self._activated_at if is_active else None,
            })
        return modes

    # ── Battery Telemetry ─────────────────────────────────────────────────────

    @staticmethod
    def get_battery_status() -> Dict[str, Any]:
        """Collects live battery status using psutil."""
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return {
                    "has_battery": False,
                    "percent": 100.0,
                    "power_plugged": True,
                    "secsleft": -1,
                    "status_text": "AC Power (Desktop / No Battery Detected)",
                }

            secs = battery.secsleft
            time_str = "Calculating..."
            if secs > 0:
                hours = int(secs // 3600)
                mins = int((secs % 3600) // 60)
                time_str = f"{hours}h {mins}m remaining"
            elif battery.power_plugged:
                time_str = "Plugged in, charging"

            return {
                "has_battery": True,
                "percent": round(battery.percent, 1),
                "power_plugged": bool(battery.power_plugged),
                "secsleft": secs,
                "status_text": f"{round(battery.percent, 1)}% ({time_str})",
            }
        except Exception as e:
            logger.debug("Error collecting battery sensor data: %s", e)
            return {
                "has_battery": False,
                "percent": 100.0,
                "power_plugged": True,
                "secsleft": -1,
                "status_text": "Unavailable",
            }

    # ── Mode Lifecycle ────────────────────────────────────────────────────────

    async def activate_mode(
        self,
        mode_id: str,
        target_app_id: Optional[str] = None,
        custom_config: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
        executor: Optional[ActionExecutor] = None,
    ) -> Dict[str, Any]:
        """Activates a designated operating mode."""
        if mode_id not in DEFAULT_MODE_CONFIGS:
            raise ValueError(f"Unknown operating mode: '{mode_id}'")

        # If a different mode is currently active, restore previous priorities first
        if self._active_mode_id and self._active_mode_id != mode_id and executor:
            await self.restore_modified_priorities(executor)

        self._active_mode_id = mode_id
        cfg = dict(DEFAULT_MODE_CONFIGS[mode_id])
        if custom_config:
            cfg.update(custom_config)
        self._active_config = cfg
        self._target_app_id = target_app_id
        self._activated_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "Activated operating mode: '%s' (target_app=%s)",
            mode_id, target_app_id,
        )

        if db:
            # Update DB state
            await db.execute(update(ApplicationModeRecord).values(is_active=False))
            # Upsert mode record
            stmt = select(ApplicationModeRecord).where(ApplicationModeRecord.id == mode_id)
            res = await db.execute(stmt)
            mode_rec = res.scalar_one_or_none()
            if mode_rec:
                mode_rec.is_active = True
                mode_rec.activated_at = datetime.now(timezone.utc)
                mode_rec.target_app_id = target_app_id
                mode_rec.configuration = cfg
            else:
                mode_rec = ApplicationModeRecord(
                    id=mode_id,
                    name=cfg["name"],
                    description=cfg["description"],
                    is_active=True,
                    activated_at=datetime.now(timezone.utc),
                    target_app_id=target_app_id,
                    configuration=cfg,
                )
                db.add(mode_rec)

            # Audit history
            hist = ApplicationModeHistoryRecord(
                mode_id=mode_id,
                action="activated",
                details={"target_app_id": target_app_id, "config": cfg},
            )
            db.add(hist)
            await db.commit()

        return self.get_active_mode_info()

    async def deactivate_mode(
        self,
        db: Optional[AsyncSession] = None,
        executor: Optional[ActionExecutor] = None,
    ) -> Dict[str, Any]:
        """Deactivates active mode and restores any lowered priorities."""
        if not self._active_mode_id:
            return self.get_active_mode_info()

        prev_mode = self._active_mode_id
        logger.info("Deactivating operating mode '%s'", prev_mode)

        # Restore process priorities modified during this mode
        if executor:
            await self.restore_modified_priorities(executor)

        self._active_mode_id = None
        self._active_config = {}
        self._target_app_id = None
        self._activated_at = None

        if db:
            await db.execute(update(ApplicationModeRecord).values(is_active=False))
            hist = ApplicationModeHistoryRecord(
                mode_id=prev_mode,
                action="deactivated",
                details={},
            )
            db.add(hist)
            await db.commit()

        return self.get_active_mode_info()

    def record_priority_modification(self, pid: int, original_priority: str) -> None:
        """Remembers a process's original priority so it can be restored on mode exit."""
        if pid not in self._modified_priorities:
            self._modified_priorities[pid] = original_priority

    async def restore_modified_priorities(self, executor: ActionExecutor) -> int:
        """Restores normal priority for all processes modified during the active mode."""
        count = 0
        for pid, orig_prio in list(self._modified_priorities.items()):
            try:
                # Use ActionExecutor restore_priority
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    res = executor.restore_priority(pid, proc.name())
                    if res.success:
                        count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except Exception as e:
                logger.debug("Failed to restore priority for PID %d: %s", pid, e)

        logger.info("Restored priority for %d modified processes.", count)
        self._modified_priorities.clear()
        return count


mode_manager = ModeManager()
