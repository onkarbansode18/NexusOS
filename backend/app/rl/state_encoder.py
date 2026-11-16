"""
Nexus Double DQN — State Encoder
==================================
Transforms real OS telemetry (from psutil/SystemMetrics) or simulated telemetry
(from SimState) into a normalized 14-dimensional float32 vector in [0.0, 1.0].

Guarantees:
  - Exact output shape: (14,)
  - Strict dtype: np.float32
  - Range bound: [0.0, 1.0] for every dimension
  - Zero NaN / Inf resilience (automatic sanitization to safe defaults)
"""

from __future__ import annotations

import math
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger("nexus.rl.state_encoder")

STATE_DIM: int = 14

FEATURE_NAMES: List[str] = [
    "system_cpu_percent",     # [0]  System CPU utilization (0-100 -> 0.0-1.0)
    "system_ram_percent",     # [1]  System RAM utilization (0-100 -> 0.0-1.0)
    "disk_percent",           # [2]  Primary disk utilization (0-100 -> 0.0-1.0)
    "net_utilization",        # [3]  Network IO utilization (sigmoid normalized 0.0-1.0)
    "process_cpu_percent",    # [4]  Process CPU utilization (0-100 -> 0.0-1.0)
    "process_memory_mb",      # [5]  Process RSS memory (capped at 8192 MB -> 0.0-1.0)
    "memory_growth_rate",     # [6]  Memory slope (MB/min or MB/step via tanh -> 0.0-1.0)
    "anomaly_score",          # [7]  IsolationForest / detector score (-1 to 1 -> 0.0-1.0)
    "forecast_urgency",       # [8]  Time to threshold breach (1 - min(mins/10, 1) -> 0.0-1.0)
    "process_priority",       # [9]  Nice value (-20 to +19 -> 0.0-1.0)
    "thread_count",           # [10] Thread count (capped at 100 -> 0.0-1.0)
    "historical_health",      # [11] Rolling health score (0.0 critical to 1.0 healthy)
    "previous_action",        # [12] Last action taken (0 to 6 -> 0.0-1.0)
    "action_success_rate",    # [13] Historical action success rate (0.0 to 1.0)
]


class StateEncoder:
    """
    Encodes multi-modal telemetry into a normalized RL observation vector.
    """

    def __init__(self, mem_cap_mb: float = 8192.0, max_threads: float = 100.0) -> None:
        self.mem_cap_mb = mem_cap_mb
        self.max_threads = max_threads

    @staticmethod
    def _sanitize_float(val: Any, default: float = 0.0) -> float:
        """Sanitize any numeric or null input to a finite float."""
        if val is None:
            return default
        try:
            f = float(val)
            if math.isnan(f) or math.isinf(f):
                return default
            return f
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _sigmoid(x: float) -> float:
        """Numerically stable sigmoid."""
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        else:
            z = math.exp(x)
            return z / (1.0 + z)

    def encode(
        self,
        system_cpu_percent: float = 0.0,
        system_ram_percent: float = 0.0,
        disk_percent: float = 0.0,
        net_utilization: float = 0.0,
        process_cpu_percent: float = 0.0,
        process_memory_mb: float = 0.0,
        memory_growth_rate: float = 0.0,
        anomaly_score: float = 0.0,
        forecast_mins: Optional[float] = None,
        process_priority: float = 0.0,
        thread_count: float = 1.0,
        historical_health: float = 1.0,
        previous_action: int = 0,
        action_success_rate: float = 1.0,
    ) -> np.ndarray:
        """
        Encode raw feature primitives into a sanitized shape-(14,) float32 vector.
        All output values are strictly clipped to [0.0, 1.0].
        """
        # [0] System CPU: 0-100% -> 0.0-1.0
        f0 = self._sanitize_float(system_cpu_percent, 0.0) / 100.0

        # [1] System RAM: 0-100% -> 0.0-1.0
        f1 = self._sanitize_float(system_ram_percent, 0.0) / 100.0

        # [2] Primary Disk: 0-100% -> 0.0-1.0
        f2 = self._sanitize_float(disk_percent, 0.0) / 100.0

        # [3] Network: if already in 0-1 range, use directly; otherwise sigmoid
        net_raw = self._sanitize_float(net_utilization, 0.0)
        if 0.0 <= net_raw <= 1.0:
            f3 = net_raw
        elif 1.0 < net_raw <= 100.0:
            f3 = net_raw / 100.0
        else:
            # Scaled bytes / MB/s
            f3 = (self._sigmoid(net_raw / 10.0) - 0.5) * 2.0

        # [4] Process CPU: 0-100% -> 0.0-1.0
        f4 = self._sanitize_float(process_cpu_percent, 0.0) / 100.0

        # [5] Process Memory: 0 to mem_cap_mb -> 0.0-1.0
        f5 = self._sanitize_float(process_memory_mb, 0.0) / self.mem_cap_mb

        # [6] Memory growth rate (slope): tanh(slope * 10) mapped [-1, 1] -> [0.0, 1.0]
        slope = self._sanitize_float(memory_growth_rate, 0.0)
        tanh_slope = math.tanh(slope * 10.0)
        f6 = (tanh_slope + 1.0) / 2.0

        # [7] Anomaly score: IsolationForest yields [-1, 1], mapped to [0.0, 1.0]
        anom = self._sanitize_float(anomaly_score, 0.0)
        # If score is already 0.0 to 1.0
        if 0.0 <= anom <= 1.0 and anom != 0.0:
            f7 = anom
        else:
            f7 = (anom + 1.0) / 2.0

        # [8] Forecast urgency: minutes until breach -> 1 - min(mins/10, 1)
        if forecast_mins is None:
            f8 = 0.0
        else:
            fm = self._sanitize_float(forecast_mins, -1.0)
            if fm < 0.0:
                f8 = 0.0
            else:
                f8 = 1.0 - min(fm / 10.0, 1.0)

        # [9] Process priority / nice value: [-20, 19] -> [0.0, 1.0]
        nice = self._sanitize_float(process_priority, 0.0)
        if -20.0 <= nice <= 20.0:
            f9 = (nice + 20.0) / 40.0
        else:
            f9 = nice / 100.0

        # [10] Thread count: 0 to max_threads -> 0.0-1.0
        threads = self._sanitize_float(thread_count, 1.0)
        f10 = min(max(threads, 0.0) / self.max_threads, 1.0)

        # [11] Historical health: 0.0 (critical) to 1.0 (healthy)
        f11 = self._sanitize_float(historical_health, 1.0)

        # [12] Previous action: 0 to 6 -> 0.0-1.0
        prev_act = self._sanitize_float(previous_action, 0.0)
        f12 = prev_act / 6.0

        # [13] Action success rate: 0.0 to 1.0
        f13 = self._sanitize_float(action_success_rate, 1.0)

        vec = np.array([f0, f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12, f13], dtype=np.float32)

        # Zero NaN/Inf safeguard and clamp strictly to [0.0, 1.0]
        vec = np.nan_to_num(vec, nan=0.0, posinf=1.0, neginf=0.0)
        vec = np.clip(vec, 0.0, 1.0)
        return vec

    def encode_from_real(
        self,
        system_metrics: Any,
        process_snapshot: Any,
        anomaly_score: float = 0.0,
        forecast_mins: Optional[float] = None,
        memory_slope: float = 0.0,
        prev_action_idx: int = 0,
        action_success_rate: float = 1.0,
        process_health_history: float = 1.0,
        nice_value: int = 0,
    ) -> np.ndarray:
        """
        Encode from live SystemMetrics and ProcessSnapshot dataclasses.
        """
        sys_cpu = getattr(system_metrics, "cpu_percent", 0.0) if system_metrics else 0.0
        sys_ram = getattr(system_metrics, "ram_percent", 0.0) if system_metrics else 0.0

        # Disk
        disk_pct = 0.0
        if system_metrics and hasattr(system_metrics, "disk") and system_metrics.disk:
            disk_pct = getattr(system_metrics.disk, "percent", 0.0)

        # Network
        net_util = 0.0
        if system_metrics and hasattr(system_metrics, "network") and system_metrics.network:
            # Bytes delta in MB/s
            net = system_metrics.network
            sent_mb = getattr(net, "delta_bytes_sent", 0) / (1024 * 1024)
            recv_mb = getattr(net, "delta_bytes_recv", 0) / (1024 * 1024)
            net_util = sent_mb + recv_mb

        proc_cpu = getattr(process_snapshot, "cpu_percent", 0.0) if process_snapshot else 0.0
        proc_mem = getattr(process_snapshot, "memory_mb", 0.0) if process_snapshot else 0.0
        threads = getattr(process_snapshot, "num_threads", 1) if process_snapshot else 1

        return self.encode(
            system_cpu_percent=sys_cpu,
            system_ram_percent=sys_ram,
            disk_percent=disk_pct,
            net_utilization=net_util,
            process_cpu_percent=proc_cpu,
            process_memory_mb=proc_mem,
            memory_growth_rate=memory_slope,
            anomaly_score=anomaly_score,
            forecast_mins=forecast_mins,
            process_priority=float(nice_value),
            thread_count=float(threads),
            historical_health=process_health_history,
            previous_action=prev_action_idx,
            action_success_rate=action_success_rate,
        )

    def encode_from_sim(
        self,
        sim_state: Any,
        prev_action_idx: Optional[int] = None,
        action_success_rate: Optional[float] = None,
    ) -> np.ndarray:
        """
        Encode from a simulated environment state (SimState).
        """
        p_act = prev_action_idx if prev_action_idx is not None else getattr(sim_state, "previous_action", 0)
        s_rate = action_success_rate if action_success_rate is not None else getattr(sim_state, "action_success_rate", 1.0)

        return self.encode(
            system_cpu_percent=getattr(sim_state, "system_cpu_percent", 0.0),
            system_ram_percent=getattr(sim_state, "system_ram_percent", 0.0),
            disk_percent=getattr(sim_state, "disk_percent", 0.0),
            net_utilization=getattr(sim_state, "net_utilization", 0.0),
            process_cpu_percent=getattr(sim_state, "process_cpu_percent", 0.0),
            process_memory_mb=getattr(sim_state, "process_memory_mb", 0.0),
            memory_growth_rate=getattr(sim_state, "memory_growth_rate", 0.0),
            anomaly_score=getattr(sim_state, "anomaly_score", 0.0),
            forecast_mins=getattr(sim_state, "forecast_mins", None),
            process_priority=float(getattr(sim_state, "process_priority", 0)),
            thread_count=float(getattr(sim_state, "thread_count", 1)),
            historical_health=getattr(sim_state, "historical_health", 1.0),
            previous_action=p_act,
            action_success_rate=s_rate,
        )
