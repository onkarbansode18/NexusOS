"""
Nexus — Sustained Pressure Tracker
====================================
Tracks how long each process has been in a high-resource state.
Prevents the decision engine from firing on transient single-sample spikes.

Design:
- Pure in-memory data structure, no DB, no async.
- One entry per PID tracking a rolling window of boolean "elevated" flags.
- Thread-safe for single-threaded asyncio use (no explicit locks needed).
- Handles PID reuse via creation-time fingerprinting.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Tuple

logger = logging.getLogger("nexus.healing.sustained")


@dataclass
class ProcessPressureRecord:
    """Rolling history of elevated-state samples for one process."""
    pid: int
    name: str
    # creation_key: (pid, create_time_str) — detects PID reuse
    creation_key: str
    # Ring buffer: (unix_timestamp, is_elevated) tuples
    samples: Deque[Tuple[float, bool]] = field(default_factory=lambda: deque(maxlen=300))
    # Count of consecutive elevated samples
    consecutive_elevated: int = 0
    # Total elevated samples in window
    elevated_count: int = 0
    # Timestamp when the process first became elevated in the current run
    first_elevated_at: Optional[float] = None


class SustainedPressureTracker:
    """
    Tracks whether a process has sustained elevated resource usage.

    Usage:
        tracker = SustainedPressureTracker(
            cpu_threshold=85.0,
            memory_mb_threshold=2048.0,
            sustained_seconds=30.0,
            sample_interval=2.0,
        )
        # Each monitoring tick:
        result = tracker.update(pid=1234, name="python", creation_key="1234_1700000000",
                                cpu_percent=91.0, memory_mb=512.0)
        if result.is_sustained_cpu:
            # safe to act
    """

    def __init__(
        self,
        cpu_threshold: float = 85.0,
        memory_mb_threshold: float = 2048.0,
        memory_percent_threshold: float = 80.0,
        sustained_seconds: float = 30.0,
        sample_interval: float = 2.0,
        history_window_seconds: float = 300.0,
    ) -> None:
        self.cpu_threshold = cpu_threshold
        self.memory_mb_threshold = memory_mb_threshold
        self.memory_percent_threshold = memory_percent_threshold
        self.sustained_seconds = sustained_seconds
        self.sample_interval = sample_interval
        self.history_window_seconds = history_window_seconds

        # Minimum samples required before we call something "sustained"
        self._min_samples = max(2, int(sustained_seconds / max(sample_interval, 0.5)))
        # Storage: pid → ProcessPressureRecord
        self._records: Dict[int, ProcessPressureRecord] = {}

    # ── Public API ──────────────────────────────────────────────────────────────

    def update(
        self,
        pid: int,
        name: str,
        creation_key: str,
        cpu_percent: float,
        memory_mb: float,
        memory_percent: float = 0.0,
    ) -> "SustainedCheckResult":
        """
        Feed one monitoring sample for a process.
        Returns a SustainedCheckResult indicating whether sustained conditions hold.
        """
        now = time.monotonic()
        record = self._get_or_create(pid, name, creation_key)

        is_elevated_cpu = cpu_percent >= self.cpu_threshold
        is_elevated_mem = (
            memory_mb >= self.memory_mb_threshold
            or memory_percent >= self.memory_percent_threshold
        )
        is_elevated = is_elevated_cpu or is_elevated_mem

        # Prune samples outside the window
        cutoff = now - self.history_window_seconds
        while record.samples and record.samples[0][0] < cutoff:
            record.samples.popleft()

        record.samples.append((now, is_elevated))

        # Track consecutive streak
        if is_elevated:
            record.consecutive_elevated += 1
            if record.first_elevated_at is None:
                record.first_elevated_at = now
        else:
            record.consecutive_elevated = 0
            record.first_elevated_at = None

        # Count elevated in recent window
        recent_window = now - self.sustained_seconds
        recent_samples = [(t, e) for t, e in record.samples if t >= recent_window]
        elevated_in_window = sum(1 for _, e in recent_samples if e)
        total_in_window = len(recent_samples)

        # "Sustained" = at least min_samples in the window AND most of them elevated
        is_sustained = (
            total_in_window >= self._min_samples
            and elevated_in_window >= self._min_samples
            and (elevated_in_window / total_in_window) >= 0.75
        )

        # Refined per-resource sustained checks
        recent_cpu_elevated = sum(
            1 for t, e in record.samples
            if t >= recent_window
        )  # reuse elevated flag for cpu check (already aggregated)
        # We need per-resource tracking for more granularity
        elapsed_elevated = (now - record.first_elevated_at) if record.first_elevated_at else 0.0

        return SustainedCheckResult(
            pid=pid,
            process_name=name,
            is_elevated=is_elevated,
            is_elevated_cpu=is_elevated_cpu,
            is_elevated_memory=is_elevated_mem,
            is_sustained=is_sustained,
            elapsed_elevated_seconds=elapsed_elevated,
            consecutive_elevated_samples=record.consecutive_elevated,
            total_samples_in_window=total_in_window,
            elevated_samples_in_window=elevated_in_window,
        )

    def clear_process(self, pid: int) -> None:
        """Remove tracking state for a PID (call when process exits)."""
        self._records.pop(pid, None)

    def clear_all(self) -> None:
        """Clear all state — for testing."""
        self._records.clear()

    def get_elevated_pids(self) -> list[int]:
        """Return PIDs currently flagged as sustained-elevated."""
        now = time.monotonic()
        result = []
        for pid, rec in self._records.items():
            if rec.first_elevated_at and (now - rec.first_elevated_at) >= self.sustained_seconds:
                result.append(pid)
        return result

    # ── Private ─────────────────────────────────────────────────────────────────

    def _get_or_create(self, pid: int, name: str, creation_key: str) -> ProcessPressureRecord:
        """Return existing record, or create a fresh one (handles PID reuse)."""
        existing = self._records.get(pid)
        if existing is None or existing.creation_key != creation_key:
            # New process or PID was reused
            record = ProcessPressureRecord(pid=pid, name=name, creation_key=creation_key)
            self._records[pid] = record
            return record
        return existing


# ── Result type ──────────────────────────────────────────────────────────────

@dataclass
class SustainedCheckResult:
    pid: int
    process_name: str
    is_elevated: bool              # currently above any threshold
    is_elevated_cpu: bool          # specifically CPU above threshold
    is_elevated_memory: bool       # specifically memory above threshold
    is_sustained: bool             # elevated long enough to consider action
    elapsed_elevated_seconds: float  # seconds since first became elevated
    consecutive_elevated_samples: int
    total_samples_in_window: int
    elevated_samples_in_window: int

    @property
    def is_sustained_cpu(self) -> bool:
        return self.is_sustained and self.is_elevated_cpu

    @property
    def is_sustained_memory(self) -> bool:
        return self.is_sustained and self.is_elevated_memory

    @property
    def consecutive_elevated(self) -> int:
        return self.consecutive_elevated_samples

    @property
    def summary(self) -> str:
        return f"consecutive={self.consecutive_elevated_samples}, elapsed={self.elapsed_elevated_seconds:.1f}s"


