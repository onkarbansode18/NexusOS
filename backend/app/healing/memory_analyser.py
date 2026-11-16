"""
Nexus — Memory Leak & Trend Analyser
======================================
Distinguishes between:
  - Normal high memory usage (large process, stable)
  - Temporary spikes (brief rise then falls back)
  - Steady upward trends (possible memory growth)
  - Sustained rapid growth (possible memory leak)
  - System-wide memory pressure (not one process's fault)

Does NOT use a heavy ML model — lightweight statistical analysis only.
Integrates with the existing forecasting.py linear regression.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("nexus.healing.memory")


# ── Finding types ─────────────────────────────────────────────────────────────

class MemoryFindingKind:
    NORMAL            = "normal"
    SPIKE             = "memory_spike"
    GROWTH            = "memory_growth"
    POSSIBLE_LEAK     = "possible_memory_leak"
    SYSTEM_PRESSURE   = "system_memory_pressure"


@dataclass
class MemoryFinding:
    pid: int
    process_name: str
    kind: str                          # MemoryFindingKind constant
    current_rss_mb: float
    growth_rate_mb_per_min: float      # positive = growing, 0 = stable
    slope_r_squared: float             # 0–1, confidence in trend line
    samples_analysed: int
    window_seconds: float
    system_ram_percent: float          # overall RAM pressure at time of finding
    description: str                   # plain-English
    is_actionable: bool                # True if the system recommends investigation
    minutes_until_breach: Optional[float] = None  # None if stable/declining


@dataclass
class _MemorySample:
    timestamp: float   # monotonic seconds
    rss_mb: float


@dataclass
class _ProcessMemoryState:
    pid: int
    name: str
    creation_key: str
    samples: Deque[_MemorySample] = field(
        default_factory=lambda: deque(maxlen=500)
    )
    baseline_rss_mb: Optional[float] = None  # first-observed stable baseline


# ── Analyser ─────────────────────────────────────────────────────────────────

class MemoryLeakAnalyser:
    """
    Stateful per-process memory trend analyser.
    Call .update() on every monitoring tick.
    """

    def __init__(
        self,
        analysis_window_seconds: float = 120.0,   # 2-minute window for trend
        min_samples: int = 15,                     # minimum samples before analysis
        growth_rate_mb_per_min: float = 10.0,      # threshold: growth to flag
        leak_rate_mb_per_min: float = 30.0,        # threshold: likely leak
        spike_tolerance_pct: float = 50.0,         # % spike above baseline = spike
        min_r_squared: float = 0.5,                # R² threshold for reliable trend
        process_rss_warning_mb: float = 1024.0,    # process RSS warning threshold
        process_rss_critical_mb: float = 2048.0,   # process RSS critical threshold
        system_ram_pressure_pct: float = 85.0,     # system-wide RAM % to flag pressure
        sample_interval_seconds: float = 2.0,
    ) -> None:
        self.analysis_window_seconds = analysis_window_seconds
        self.min_samples = min_samples
        self.growth_rate_threshold = growth_rate_mb_per_min
        self.leak_rate_threshold = leak_rate_mb_per_min
        self.spike_tolerance_pct = spike_tolerance_pct
        self.min_r_squared = min_r_squared
        self.process_rss_warning_mb = process_rss_warning_mb
        self.process_rss_critical_mb = process_rss_critical_mb
        self.system_ram_pressure_pct = system_ram_pressure_pct
        self.sample_interval_seconds = sample_interval_seconds

        self._states: Dict[int, _ProcessMemoryState] = {}

    # ── Public API ──────────────────────────────────────────────────────────────

    def record_sample(
        self,
        pid: int,
        name: str,
        creation_key: str,
        rss_mb: float,
        system_ram_percent: float = 0.0,
    ) -> MemoryFinding:
        """Feed one sample for tracking."""
        return self.update(pid, name, creation_key, rss_mb, system_ram_percent)

    def analyse(self, pid: int) -> MemoryFinding:
        """Return the current analysis finding for a process."""
        state = self._states.get(pid)
        if not state or not state.samples:
            return self._normal_finding(pid, "unknown", 0.0, 0.0, 0, 0.0, 0.0, "No samples tracked for PID.")
        latest = state.samples[-1]
        now = time.monotonic()
        cutoff = now - self.analysis_window_seconds
        window_samples = [s for s in state.samples if s.timestamp >= cutoff]
        if len(window_samples) < self.min_samples:
            return self._normal_finding(pid, state.name, latest.rss_mb, 0.0, len(window_samples), 0.0, 0.0, "Insufficient samples for trend analysis.")

        times = np.array([s.timestamp - window_samples[0].timestamp for s in window_samples])
        values = np.array([s.rss_mb for s in window_samples])
        slope, _, r_squared = _linear_fit(times, values)
        slope_mb_per_min = slope * 60.0
        kind, description, is_actionable, minutes = self._classify(
            name=state.name,
            rss_mb=latest.rss_mb,
            slope_mb_per_min=slope_mb_per_min,
            r_squared=r_squared,
            baseline_rss_mb=state.baseline_rss_mb,
            system_ram_percent=0.0,
            samples=window_samples,
        )
        return MemoryFinding(
            pid=pid,
            process_name=state.name,
            kind=kind,
            current_rss_mb=latest.rss_mb,
            growth_rate_mb_per_min=round(slope_mb_per_min, 2),
            slope_r_squared=round(r_squared, 3),
            samples_analysed=len(window_samples),
            window_seconds=self.analysis_window_seconds,
            system_ram_percent=0.0,
            description=description,
            is_actionable=is_actionable,
            minutes_until_breach=minutes,
        )

    def update(
        self,
        pid: int,
        name: str,
        creation_key: str,
        rss_mb: float,
        system_ram_percent: float,
    ) -> MemoryFinding:
        """
        Feed one sample. Returns a MemoryFinding (possibly NORMAL).
        """
        state = self._get_or_create(pid, name, creation_key)
        now = time.monotonic()

        sample = _MemorySample(timestamp=now, rss_mb=rss_mb)
        state.samples.append(sample)

        # Set baseline from stable early samples
        if state.baseline_rss_mb is None and len(state.samples) >= 5:
            first_five = list(state.samples)[:5]
            state.baseline_rss_mb = sum(s.rss_mb for s in first_five) / 5.0

        # System-wide pressure (not per-process)
        if system_ram_percent >= self.system_ram_pressure_pct:
            return MemoryFinding(
                pid=pid, process_name=name,
                kind=MemoryFindingKind.SYSTEM_PRESSURE,
                current_rss_mb=rss_mb,
                growth_rate_mb_per_min=0.0,
                slope_r_squared=0.0,
                samples_analysed=len(state.samples),
                window_seconds=self.analysis_window_seconds,
                system_ram_percent=system_ram_percent,
                description=(
                    f"System RAM at {system_ram_percent:.1f}% — widespread memory pressure. "
                    f"Process '{name}' uses {rss_mb:.0f} MB."
                ),
                is_actionable=True,
            )

        # Not enough samples yet
        if len(state.samples) < self.min_samples:
            return self._normal_finding(pid, name, rss_mb, system_ram_percent,
                                        len(state.samples), 0.0, 0.0,
                                        "Insufficient samples for trend analysis.")

        # Pull the analysis window
        cutoff = now - self.analysis_window_seconds
        window_samples = [s for s in state.samples if s.timestamp >= cutoff]

        if len(window_samples) < self.min_samples:
            return self._normal_finding(pid, name, rss_mb, system_ram_percent,
                                        len(window_samples), 0.0, 0.0,
                                        "Not enough samples within analysis window.")

        # Fit linear regression
        times = np.array([s.timestamp - window_samples[0].timestamp for s in window_samples])
        values = np.array([s.rss_mb for s in window_samples])
        slope, _, r_squared = _linear_fit(times, values)

        # slope is MB per second → convert to MB per minute
        slope_mb_per_min = slope * 60.0

        # Determine kind
        kind, description, is_actionable, minutes_until_breach = self._classify(
            name=name,
            rss_mb=rss_mb,
            slope_mb_per_min=slope_mb_per_min,
            r_squared=r_squared,
            baseline_rss_mb=state.baseline_rss_mb,
            system_ram_percent=system_ram_percent,
            samples=window_samples,
        )

        return MemoryFinding(
            pid=pid,
            process_name=name,
            kind=kind,
            current_rss_mb=rss_mb,
            growth_rate_mb_per_min=round(slope_mb_per_min, 3),
            slope_r_squared=round(r_squared, 3),
            samples_analysed=len(window_samples),
            window_seconds=float(times[-1] - times[0]),
            system_ram_percent=system_ram_percent,
            description=description,
            is_actionable=is_actionable,
            minutes_until_breach=minutes_until_breach,
        )

    def clear_process(self, pid: int) -> None:
        self._states.pop(pid, None)

    def clear_all(self) -> None:
        self._states.clear()

    # ── Private ─────────────────────────────────────────────────────────────────

    def _get_or_create(self, pid: int, name: str, creation_key: str) -> _ProcessMemoryState:
        existing = self._states.get(pid)
        if existing is None or existing.creation_key != creation_key:
            state = _ProcessMemoryState(pid=pid, name=name, creation_key=creation_key)
            self._states[pid] = state
            return state
        return existing

    def _classify(
        self,
        name: str,
        rss_mb: float,
        slope_mb_per_min: float,
        r_squared: float,
        baseline_rss_mb: Optional[float],
        system_ram_percent: float,
        samples: List[_MemorySample],
    ) -> Tuple[str, str, bool, Optional[float]]:
        """Return (kind, description, is_actionable, minutes_until_breach)."""

        # 1. Check for transient spike: high now but recent trend not persistently up
        if baseline_rss_mb and rss_mb > baseline_rss_mb * (1 + self.spike_tolerance_pct / 100):
            if slope_mb_per_min <= self.growth_rate_threshold and r_squared < self.min_r_squared:
                return (
                    MemoryFindingKind.SPIKE,
                    (f"Process '{name}' RSS is {rss_mb:.0f} MB, {self.spike_tolerance_pct:.0f}% "
                     f"above baseline ({baseline_rss_mb:.0f} MB), but trend is not sustained "
                     f"(slope={slope_mb_per_min:.1f} MB/min, R²={r_squared:.2f})."),
                    False,  # not actionable — likely transient
                    None,
                )

        # 2. Rapid, reliable upward trend → possible leak
        if slope_mb_per_min >= self.leak_rate_threshold and r_squared >= self.min_r_squared:
            minutes_until_breach = None
            if slope_mb_per_min > 0:
                remaining_mb = self.process_rss_critical_mb - rss_mb
                if remaining_mb > 0:
                    minutes_until_breach = round(remaining_mb / slope_mb_per_min, 1)
                else:
                    minutes_until_breach = 0.0
            return (
                MemoryFindingKind.POSSIBLE_LEAK,
                (f"Process '{name}' memory growing at {slope_mb_per_min:.1f} MB/min "
                 f"(R²={r_squared:.2f}, current {rss_mb:.0f} MB). "
                 f"Sustained upward trend — possible memory leak."),
                True,
                minutes_until_breach,
            )

        # 3. Moderate upward trend → memory growth
        if slope_mb_per_min >= self.growth_rate_threshold and r_squared >= self.min_r_squared:
            minutes_until_breach = None
            if slope_mb_per_min > 0:
                remaining_mb = self.process_rss_warning_mb - rss_mb
                if remaining_mb > 0:
                    minutes_until_breach = round(remaining_mb / slope_mb_per_min, 1)
                else:
                    minutes_until_breach = 0.0
            return (
                MemoryFindingKind.GROWTH,
                (f"Process '{name}' memory growing at {slope_mb_per_min:.1f} MB/min "
                 f"(R²={r_squared:.2f}, current {rss_mb:.0f} MB). "
                 f"Monitoring — not yet at critical rate."),
                rss_mb >= self.process_rss_warning_mb,
                minutes_until_breach,
            )

        # 4. Normal
        return (
            MemoryFindingKind.NORMAL,
            (f"Process '{name}' memory stable at {rss_mb:.0f} MB "
             f"(slope={slope_mb_per_min:.1f} MB/min, R²={r_squared:.2f})."),
            False,
            None,
        )

    @staticmethod
    def _normal_finding(
        pid: int, name: str, rss_mb: float,
        system_ram_percent: float, n_samples: int,
        slope: float, r_sq: float, reason: str,
    ) -> MemoryFinding:
        return MemoryFinding(
            pid=pid, process_name=name,
            kind=MemoryFindingKind.NORMAL,
            current_rss_mb=rss_mb,
            growth_rate_mb_per_min=slope,
            slope_r_squared=r_sq,
            samples_analysed=n_samples,
            window_seconds=0.0,
            system_ram_percent=system_ram_percent,
            description=reason,
            is_actionable=False,
        )


# ── Stats helper ──────────────────────────────────────────────────────────────

def _linear_fit(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float]:
    """Return (slope, intercept, r_squared)."""
    n = len(x)
    if n < 2:
        return 0.0, float(y[0]) if n else 0.0, 0.0
    coeffs = np.polyfit(x, y, 1)
    slope, intercept = float(coeffs[0]), float(coeffs[1])
    y_pred = slope * x + intercept
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r_sq = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return slope, intercept, max(0.0, r_sq)
