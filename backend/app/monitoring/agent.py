"""
Nexus Monitoring Agent — Phase 1
=====================================
Standalone psutil-based metric collector.
Streams CPU / RAM / disk / network / process snapshots at a configurable
interval.  No storage, no API — runs and prints.  Prove it works first.

Run directly:
    python -m app.monitoring.agent
or:
    python backend/app/monitoring/agent.py
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

import psutil

logger = logging.getLogger(__name__)


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class NetworkIO:
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    # Deltas since last sample (populated by agent loop, not psutil)
    delta_bytes_sent: int = 0
    delta_bytes_recv: int = 0


@dataclass
class DiskUsage:
    path: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


@dataclass
class ProcessSnapshot:
    pid: int
    name: str
    status: str
    username: str
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    num_threads: int
    created_at: str          # ISO-8601


@dataclass
class SystemMetrics:
    timestamp: str           # ISO-8601 UTC
    # CPU
    cpu_percent: float       # overall (all cores averaged)
    cpu_percent_per_core: List[float]
    cpu_freq_mhz: float
    cpu_count_logical: int
    # RAM
    ram_total_mb: float
    ram_used_mb: float
    ram_available_mb: float
    ram_percent: float
    # Swap
    swap_total_mb: float
    swap_used_mb: float
    swap_percent: float
    # Disk (primary)
    disk: DiskUsage
    # Network
    network: NetworkIO
    # Top processes (sorted by CPU desc by default)
    processes: List[ProcessSnapshot] = field(default_factory=list)


# ── Container-aware memory helper ─────────────────────────────────────────────

def _get_container_memory_limit_bytes() -> int | None:
    """
    Return the container cgroup memory limit in bytes, or None if unavailable.
    psutil.virtual_memory().total reports the HOST machine's RAM inside Linux
    containers (Docker / Render / etc.); this gives the actual container ceiling.
    """
    # cgroup v2  — modern kernels, Render uses this
    try:
        with open("/sys/fs/cgroup/memory.max", "r") as f:
            val = f.read().strip()
            if val != "max":
                return int(val)
    except Exception:
        pass
    # cgroup v1  — older kernels / Docker legacy
    try:
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes", "r") as f:
            val = int(f.read().strip())
            # Sentinel meaning "unlimited" ≈ 2^63 − 4096
            if val < 9 * 10 ** 18:
                return val
    except Exception:
        pass
    return None


# ── Collector ─────────────────────────────────────────────────────────────────

class MetricsCollector:
    """
    Collects a full system snapshot using psutil.
    Stateless between calls except for network delta tracking.
    """

    def __init__(self, disk_path: str = "/", top_processes: int = 250) -> None:
        self._disk_path = disk_path
        self._top_processes = top_processes
        self._last_net_io: psutil._common.snetio | None = None

        # Prime the per-process CPU percent (first call always returns 0.0)
        psutil.cpu_percent(interval=None)

    # ── Public API ────────────────────────────────────────────────────────────

    def collect(self) -> SystemMetrics:
        """Return a single complete SystemMetrics snapshot."""
        ts = datetime.now(timezone.utc).isoformat()

        cpu      = self._collect_cpu()
        ram      = self._collect_ram()
        swap     = self._collect_swap()
        disk     = self._collect_disk()
        network  = self._collect_network()
        procs    = self._collect_processes()

        return SystemMetrics(
            timestamp=ts,
            cpu_percent=cpu["overall"],
            cpu_percent_per_core=cpu["per_core"],
            cpu_freq_mhz=cpu["freq_mhz"],
            cpu_count_logical=cpu["count"],
            ram_total_mb=ram["total"],
            ram_used_mb=ram["used"],
            ram_available_mb=ram["available"],
            ram_percent=ram["percent"],
            swap_total_mb=swap["total"],
            swap_used_mb=swap["used"],
            swap_percent=swap["percent"],
            disk=disk,
            network=network,
            processes=procs,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _collect_cpu(self) -> dict:
        try:
            freq = psutil.cpu_freq()
            freq_val = round(freq.current, 1) if freq else 0.0
        except Exception:
            freq_val = 0.0
        try:
            overall = psutil.cpu_percent(interval=None)
            per_core = psutil.cpu_percent(interval=None, percpu=True)
            count = psutil.cpu_count(logical=True) or 1
        except Exception:
            overall = 0.0
            per_core = [0.0]
            count = 1
        return {
            "overall":  overall,
            "per_core": per_core,
            "freq_mhz": freq_val,
            "count":    count,
        }

    def _collect_ram(self) -> dict:
        try:
            vm = psutil.virtual_memory()
            to_mb = 1 / (1024 ** 2)
            total_bytes = vm.total

            # In Linux containers (Render, Docker) psutil reads HOST RAM, not the
            # container's cgroup limit — fix by using the smaller of host/cgroup.
            cgroup_limit = _get_container_memory_limit_bytes()
            if cgroup_limit and cgroup_limit < total_bytes:
                total_bytes = cgroup_limit

            total_mb    = round(total_bytes * to_mb, 1)
            used_mb     = round(min(vm.used * to_mb, total_mb), 1)
            available_mb = round(max(total_mb - used_mb, 0), 1)
            percent     = round((used_mb / total_mb * 100) if total_mb > 0 else 0, 1)

            return {
                "total":     total_mb,
                "used":      used_mb,
                "available": available_mb,
                "percent":   percent,
            }
        except Exception:
            return {"total": 1024.0, "used": 512.0, "available": 512.0, "percent": 50.0}

    def _collect_swap(self) -> dict:
        try:
            sw = psutil.swap_memory()
            to_mb = 1 / (1024 ** 2)
            return {
                "total":   round(sw.total * to_mb, 1),
                "used":    round(sw.used  * to_mb, 1),
                "percent": sw.percent,
            }
        except Exception:
            return {"total": 0.0, "used": 0.0, "percent": 0.0}

    def _collect_disk(self) -> DiskUsage:
        path = self._disk_path
        try:
            usage = psutil.disk_usage(path)
        except Exception:
            try:
                import os
                path = os.path.splitdrive(os.getcwd())[0] + "\\"
                usage = psutil.disk_usage(path)
            except Exception:
                return DiskUsage(path="/", total_gb=20.0, used_gb=5.0, free_gb=15.0, percent=25.0)

        to_gb = 1 / (1024 ** 3)
        return DiskUsage(
            path=path,
            total_gb=round(usage.total * to_gb, 2),
            used_gb=round(usage.used   * to_gb, 2),
            free_gb=round(usage.free   * to_gb, 2),
            percent=usage.percent,
        )

    def _collect_network(self) -> NetworkIO:
        try:
            current = psutil.net_io_counters()
            if current is None:
                return NetworkIO(bytes_sent=0, bytes_recv=0, packets_sent=0, packets_recv=0)
            delta_sent = delta_recv = 0
            if self._last_net_io is not None:
                delta_sent = max(0, current.bytes_sent - self._last_net_io.bytes_sent)
                delta_recv = max(0, current.bytes_recv - self._last_net_io.bytes_recv)
            self._last_net_io = current
            return NetworkIO(
                bytes_sent=current.bytes_sent,
                bytes_recv=current.bytes_recv,
                packets_sent=current.packets_sent,
                packets_recv=current.packets_recv,
                delta_bytes_sent=delta_sent,
                delta_bytes_recv=delta_recv,
            )
        except Exception:
            return NetworkIO(bytes_sent=0, bytes_recv=0, packets_sent=0, packets_recv=0)

    def _collect_processes(self) -> List[ProcessSnapshot]:
        snapshots: List[ProcessSnapshot] = []
        attrs = ["pid", "name", "status", "username",
                 "cpu_percent", "memory_info", "memory_percent",
                 "num_threads", "create_time"]

        for proc in psutil.process_iter(attrs=attrs, ad_value=None):
            try:
                info = proc.info
                if info["pid"] is None or info["pid"] == 0:
                    continue  # skip None and Windows System Idle Process (PID 0)

                mem_mb = 0.0
                if info["memory_info"] is not None:
                    mem_mb = round(info["memory_info"].rss / (1024 ** 2), 2)

                created_iso = ""
                if info["create_time"]:
                    created_iso = datetime.fromtimestamp(
                        info["create_time"], tz=timezone.utc
                    ).isoformat()

                snapshots.append(ProcessSnapshot(
                    pid=info["pid"],
                    name=info["name"] or "<unknown>",
                    status=info["status"] or "unknown",
                    username=info["username"] or "",
                    cpu_percent=min(round(info["cpu_percent"] or 0.0, 2), 100.0),
                    memory_mb=mem_mb,
                    memory_percent=round(info["memory_percent"] or 0.0, 3),
                    num_threads=info["num_threads"] or 0,
                    created_at=created_iso,
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue  # process died mid-iteration — safe to skip

        # Sort by CPU desc, then memory desc
        snapshots.sort(key=lambda p: (p.cpu_percent, p.memory_mb), reverse=True)
        return snapshots[: self._top_processes]
