"""
Nexus 2.0 — Application-Aware Resource Management
Application Detection Engine: Scans live OS processes via psutil, resolves parent-child
process trees, groups multi-process applications, tracks lifecycle events (start/exit/restart),
and handles PID reuse and permission barriers safely.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import psutil

from app.application_manager.application_models import (
    ApplicationCategory,
    ApplicationEntity,
    ApplicationEvent,
    ApplicationLifecycleEvent,
    ProcessDetail,
)
from app.application_manager.application_registry import ApplicationRegistry
from app.application_manager.process_classifier import ProcessClassifier
from app.application_manager.process_tree import ProcessTreeResolver
from app.decision.engine import SYSTEM_PIDS, SYSTEM_PROCESS_BLACKLIST

logger = logging.getLogger("nexus.app_detector")


class ApplicationDetector:
    """
    Dedicated detection engine for discovering real running applications,
    grouping related child processes, and maintaining lifecycle history.
    """

    def __init__(
        self,
        classifier: Optional[ProcessClassifier] = None,
        tree_resolver: Optional[ProcessTreeResolver] = None,
        max_event_history: int = 500,
    ) -> None:
        self.classifier = classifier or ProcessClassifier()
        self.tree_resolver = tree_resolver or ProcessTreeResolver()
        self.max_event_history = max_event_history

        # Active applications indexed by app_id
        self._active_apps: Dict[str, ApplicationEntity] = {}

        # Prior PID tracking to detect exits and PID reuse
        # {pid: (app_id, create_time)}
        self._known_pids: Dict[int, tuple[str, float]] = {}

        # Lifecycle event history (started, exited, restarted)
        self._events: List[ApplicationEvent] = []

        # High-performance cache (2s TTL) for fast UI polling
        self._cached_apps: Optional[List[ApplicationEntity]] = None
        self._last_cache_time: float = 0.0

    # ── Process Collection ────────────────────────────────────────────────────

    def collect_processes(self) -> List[ProcessDetail]:
        """
        Scans all running OS processes using psutil, extracting complete telemetry.
        Safely catches NoSuchProcess, AccessDenied, and ZombieProcess.
        """
        results: List[ProcessDetail] = []
        attrs = [
            "pid", "ppid", "name", "exe", "cpu_percent",
            "memory_info", "memory_percent", "num_threads", "status",
            "create_time",
        ]

        for proc in psutil.process_iter(attrs=attrs, ad_value=None):
            try:
                info = proc.info
                pid = info.get("pid")
                if pid is None or pid == 0:
                    continue  # skip idle / invalid

                # Memory RSS
                mem_mb = 0.0
                mem_info = info.get("memory_info")
                if mem_info is not None:
                    mem_mb = round(mem_info.rss / (1024 ** 2), 2)

                # Creation time
                c_time = info.get("create_time") or 0.0
                created_iso = ""
                if c_time > 0:
                    try:
                        created_iso = datetime.fromtimestamp(c_time, tz=timezone.utc).isoformat()
                    except Exception:
                        pass

                detail = ProcessDetail(
                    pid=pid,
                    ppid=info.get("ppid"),
                    name=info.get("name") or "<unknown>",
                    exe=info.get("exe"),
                    cmdline=None,
                    cpu_percent=min(round(info.get("cpu_percent") or 0.0, 2), 100.0),
                    memory_mb=mem_mb,
                    memory_percent=round(info.get("memory_percent") or 0.0, 3),
                    num_threads=info.get("num_threads") or 0,
                    status=info.get("status") or "running",
                    created_at=created_iso,
                    create_time=c_time,
                    priority="NORMAL",
                    read_bytes=None,
                    write_bytes=None,
                    network_bytes=None,
                )
                results.append(detail)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as e:
                logger.debug("Unexpected error collecting process info: %s", e)
                continue

        return results

    def _resolve_priority_string(self, nice_val: Optional[int]) -> str:
        """Converts OS priority/nice value to a human-readable priority string."""
        if nice_val is None:
            return "NORMAL"

        if sys.platform == "win32":
            # Windows Priority Classes
            try:
                if nice_val == getattr(psutil, "IDLE_PRIORITY_CLASS", 0x0040):
                    return "IDLE"
                elif nice_val == getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", 0x4000):
                    return "BELOW_NORMAL"
                elif nice_val == getattr(psutil, "NORMAL_PRIORITY_CLASS", 0x0020):
                    return "NORMAL"
                elif nice_val == getattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS", 0x8000):
                    return "ABOVE_NORMAL"
                elif nice_val == getattr(psutil, "HIGH_PRIORITY_CLASS", 0x0080):
                    return "HIGH"
                elif nice_val == getattr(psutil, "REALTIME_PRIORITY_CLASS", 0x0100):
                    return "REALTIME"
            except Exception:
                pass
            return f"PRIORITY_{nice_val}"
        else:
            # Unix nice values (-20 to 19)
            if nice_val > 5:
                return "LOW"
            elif nice_val < -5:
                return "HIGH"
            return "NORMAL"

    # ── Application Detection & Grouping ──────────────────────────────────────

    def detect_applications(
        self, processes: Optional[List[ProcessDetail]] = None
    ) -> List[ApplicationEntity]:
        """
        Executes a complete application detection sweep:
        1. Gathers processes (or uses provided snapshot)
        2. Groups related processes using ProcessTreeResolver
        3. Identifies stable application identity and classifies categories
        4. Detects lifecycle events (started, exited, restarted)
        5. Returns list of detected ApplicationEntity objects
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        if processes is None and self._cached_apps is not None and (now_ts - self._last_cache_time < 2.0):
            return self._cached_apps

        if processes is None:
            processes = self.collect_processes()

        # Group related processes into clusters
        process_groups = self.tree_resolver.group_processes(processes)

        current_apps: Dict[str, ApplicationEntity] = {}
        current_pids: Dict[int, tuple[str, float]] = {}

        for group in process_groups:
            if not group:
                continue

            # Identify root process (earliest created process in cluster)
            root_proc = min(group, key=lambda p: (p.create_time, p.pid))
            app_id = ApplicationRegistry.generate_app_id(root_proc.name, root_proc.exe)

            # Friendly display name
            app_name = ApplicationRegistry.get_friendly_name(root_proc.name, root_proc.exe)

            # Is system process?
            is_sys = (
                root_proc.pid in SYSTEM_PIDS or
                root_proc.name.lower() in SYSTEM_PROCESS_BLACKLIST or
                root_proc.name.lower().removesuffix(".exe") in SYSTEM_PROCESS_BLACKLIST or
                (root_proc.exe and "\\windows\\system32\\" in root_proc.exe.lower())
            )

            # Classification
            category = self.classifier.classify(
                app_id=app_id,
                name=root_proc.name,
                executable_path=root_proc.exe,
                is_system_flag=is_sys,
            )

            # Aggregate resource consumption
            total_cpu = sum(p.cpu_percent for p in group)
            total_mem_mb = sum(p.memory_mb for p in group)
            total_mem_pct = sum(p.memory_percent for p in group)
            total_threads = sum(p.num_threads for p in group)
            pids = [p.pid for p in group]

            # Track PIDs and creation times for PID reuse detection
            for p in group:
                current_pids[p.pid] = (app_id, p.create_time)

            entity = ApplicationEntity(
                app_id=app_id,
                name=app_name,
                category=category,
                executable_path=root_proc.exe,
                root_pid=root_proc.pid,
                pids=pids,
                process_count=len(group),
                processes=group,
                total_cpu_percent=total_cpu,
                total_memory_mb=total_mem_mb,
                total_memory_percent=total_mem_pct,
                total_threads=total_threads,
                is_system=is_sys,
                is_protected=is_sys,
                started_at=root_proc.created_at,
                status="active",
                user_classified=self.classifier.is_user_classified(app_id),
            )

            # If an application entity with this app_id already exists in this sweep
            # (e.g. multiple decoupled instances), merge them into the single logical entity
            if app_id in current_apps:
                existing = current_apps[app_id]
                existing.processes.extend(group)
                existing.pids.extend(pids)
                existing.process_count += len(group)
                existing.total_cpu_percent += total_cpu
                existing.total_memory_mb += total_mem_mb
                existing.total_memory_percent += total_mem_pct
                existing.total_threads += total_threads
            else:
                current_apps[app_id] = entity

        # ── Lifecycle Event Tracking ──────────────────────────────────────────
        self._detect_lifecycle_events(current_apps, current_pids)

        self._active_apps = current_apps
        self._known_pids = current_pids

        # Return applications sorted by CPU desc, then memory desc
        sorted_apps = sorted(
            list(current_apps.values()),
            key=lambda a: (a.total_cpu_percent, a.total_memory_mb),
            reverse=True,
        )
        self._cached_apps = sorted_apps
        self._last_cache_time = now_ts
        return sorted_apps

    def _detect_lifecycle_events(
        self,
        current_apps: Dict[str, ApplicationEntity],
        current_pids: Dict[int, tuple[str, float]],
    ) -> None:
        """
        Detects application start, exit, and restart events.
        Also validates process creation timestamps to handle PID reuse.
        """
        # 1. Detect Started Applications
        for app_id, app in current_apps.items():
            if app_id not in self._active_apps:
                self._record_event(
                    app_id=app_id,
                    app_name=app.name,
                    event_type=ApplicationLifecycleEvent.STARTED.value,
                    details={
                        "root_pid": app.root_pid,
                        "process_count": app.process_count,
                        "category": app.category.value if isinstance(app.category, ApplicationCategory) else str(app.category),
                    },
                )
            else:
                # Check for Restart: same app_id, but root PID changed with a new create_time
                prev_app = self._active_apps[app_id]
                if prev_app.root_pid != app.root_pid:
                    # Previous root PID no longer exists or creation time is newer
                    self._record_event(
                        app_id=app_id,
                        app_name=app.name,
                        event_type=ApplicationLifecycleEvent.RESTARTED.value,
                        details={
                            "previous_root_pid": prev_app.root_pid,
                            "new_root_pid": app.root_pid,
                        },
                    )

        # 2. Detect Exited Applications
        for app_id, prev_app in self._active_apps.items():
            if app_id not in current_apps:
                self._record_event(
                    app_id=app_id,
                    app_name=prev_app.name,
                    event_type=ApplicationLifecycleEvent.EXITED.value,
                    details={
                        "last_root_pid": prev_app.root_pid,
                        "last_process_count": prev_app.process_count,
                    },
                )

        # 3. Handle PID Reuse Check
        # If a PID existed before but now belongs to a different app or has a distinct create_time
        for pid, (old_app_id, old_create_time) in self._known_pids.items():
            if pid in current_pids:
                new_app_id, new_create_time = current_pids[pid]
                if old_app_id != new_app_id or abs(old_create_time - new_create_time) > 0.5:
                    logger.debug(
                        "Detected PID reuse: PID %d was %s (c=%s), now %s (c=%s)",
                        pid, old_app_id, old_create_time, new_app_id, new_create_time,
                    )

    def _record_event(
        self, app_id: str, app_name: str, event_type: str, details: dict
    ) -> None:
        """Records an application lifecycle event in history."""
        event = ApplicationEvent(
            app_id=app_id,
            app_name=app_name,
            event_type=event_type,
            details=details,
        )
        self._events.append(event)
        if len(self._events) > self.max_event_history:
            self._events.pop(0)

        logger.info(
            "Application lifecycle: [%s] %s (%s) — details: %s",
            event_type.upper(), app_name, app_id, details,
        )

    # ── Public Query API ──────────────────────────────────────────────────────

    def get_active_applications(self) -> List[ApplicationEntity]:
        """Returns the most recent snapshot of active applications."""
        return list(self._active_apps.values())

    def get_application(self, app_id: str) -> Optional[ApplicationEntity]:
        """Finds an active application by its stable app_id."""
        return self._active_apps.get(app_id)

    def get_events(self, limit: int = 50) -> List[ApplicationEvent]:
        """Returns recent application lifecycle events."""
        return self._events[-limit:]
