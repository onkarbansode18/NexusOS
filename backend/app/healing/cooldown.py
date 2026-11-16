"""
Nexus — Action Cooldown & Rate Limiter
=======================================
Enforces:
  1. Per-process cooldown — minimum time before the same PID can be acted on again.
  2. Global action velocity cap — maximum actions per rolling time window.
  3. Emergency stop — blocks ALL new automated actions when triggered.

Thread-safe for single-threaded asyncio use.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional

logger = logging.getLogger("nexus.healing.cooldown")


@dataclass
class CooldownCheckResult:
    allowed: bool
    reason: str
    next_allowed_at: Optional[float] = None   # monotonic seconds
    actions_in_window: int = 0
    max_actions_in_window: int = 0


class ActionCooldownManager:
    """
    Tracks action history and enforces cooldown / rate limits.

    Parameters
    ----------
    per_process_cooldown_seconds : float
        Minimum seconds between successive actions on the SAME process.
    max_actions_per_window : int
        Maximum total automated actions in the rolling window.
    window_seconds : float
        Duration of the rate-limiting window.
    """

    def __init__(
        self,
        per_process_cooldown_seconds: float = 300.0,  # 5 minutes
        max_actions_per_window: int = 5,
        window_seconds: float = 600.0,                # 10 minutes
    ) -> None:
        self._cooldown = per_process_cooldown_seconds
        self._max_actions = max_actions_per_window
        self._window = window_seconds

        # pid → monotonic timestamp of last action
        self._last_action: Dict[int, float] = {}
        # Global action timestamps (monotonic)
        self._global_history: Deque[float] = deque()
        # Emergency stop flag
        self._emergency_stop: bool = False
        self._emergency_stop_reason: str = ""

    # ── Public API ──────────────────────────────────────────────────────────────

    def check(self, pid: int) -> CooldownCheckResult:
        """
        Check whether an action on PID is currently allowed.
        Does NOT record the action — call record() after successful execution.
        """
        now = time.monotonic()

        if self._emergency_stop:
            return CooldownCheckResult(
                allowed=False,
                reason=f"Emergency stop active: {self._emergency_stop_reason}",
            )

        # Per-process cooldown
        last = self._last_action.get(pid)
        if last is not None:
            elapsed = now - last
            if elapsed < self._cooldown:
                remaining = self._cooldown - elapsed
                return CooldownCheckResult(
                    allowed=False,
                    reason=(
                        f"Per-process cooldown active for PID {pid}: "
                        f"{remaining:.0f}s remaining (cooldown={self._cooldown:.0f}s)."
                    ),
                    next_allowed_at=last + self._cooldown,
                    actions_in_window=self._count_window(now),
                    max_actions_in_window=self._max_actions,
                )

        # Global velocity cap
        count = self._count_window(now)
        if count >= self._max_actions:
            # Find oldest recent action to calculate when window clears
            self._prune_window(now)
            oldest = self._global_history[0] if self._global_history else now
            return CooldownCheckResult(
                allowed=False,
                reason=(
                    f"Global action velocity cap reached: {count}/{self._max_actions} "
                    f"actions in the last {self._window:.0f}s window."
                ),
                next_allowed_at=oldest + self._window,
                actions_in_window=count,
                max_actions_in_window=self._max_actions,
            )

        return CooldownCheckResult(
            allowed=True,
            reason="Action permitted.",
            actions_in_window=count,
            max_actions_in_window=self._max_actions,
        )

    def record(self, pid: int) -> None:
        """Record that an action was taken on PID right now."""
        now = time.monotonic()
        self._last_action[pid] = now
        self._global_history.append(now)
        self._prune_window(now)

    def clear_process(self, pid: int) -> None:
        """Remove cooldown for a specific PID (e.g., process exited)."""
        self._last_action.pop(pid, None)

    def reset(self) -> None:
        """Clear all history — for testing or policy reset."""
        self._last_action.clear()
        self._global_history.clear()

    # ── Emergency stop ───────────────────────────────────────────────────────────

    def trigger_emergency_stop(self, reason: str = "Operator requested emergency stop.") -> None:
        """Block ALL new automated actions immediately."""
        self._emergency_stop = True
        self._emergency_stop_reason = reason
        logger.critical("EMERGENCY STOP TRIGGERED: %s", reason)

    def clear_emergency_stop(self) -> None:
        """Re-enable automated actions."""
        self._emergency_stop = False
        self._emergency_stop_reason = ""
        logger.warning("Emergency stop cleared — automated actions re-enabled.")

    @property
    def emergency_stop_active(self) -> bool:
        return self._emergency_stop

    @property
    def emergency_stop_reason(self) -> str:
        return self._emergency_stop_reason

    # ── Private ─────────────────────────────────────────────────────────────────

    def _count_window(self, now: float) -> int:
        self._prune_window(now)
        return len(self._global_history)

    def _prune_window(self, now: float) -> None:
        cutoff = now - self._window
        while self._global_history and self._global_history[0] < cutoff:
            self._global_history.popleft()
