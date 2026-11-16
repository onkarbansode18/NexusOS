"""
Nexus — Root-Cause Diagnosis Engine
=====================================
Feature 5: Root-Cause Diagnosis and Recovery History.

Aggregates all available signals — ML anomaly scores, memory trend, sustained
pressure, system-wide metrics — and produces a structured RootCauseDiagnosis.

Design:
  - Pure function: no IO, no async, fully testable.
  - Returns a structured diagnosis with confidence, causal chain, and
    recommended remediation steps.
  - Feeds into the LLM summarizer to enhance incident descriptions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from app.ml.anomaly import AnomalyResult
from app.ml.forecasting import ForecastResult
from app.monitoring.agent import ProcessSnapshot, SystemMetrics
from app.healing.memory_analyser import MemoryFinding, MemoryFindingKind
from app.healing.sustained_tracker import SustainedCheckResult

logger = logging.getLogger("nexus.healing.rca")


# ── Root-cause categories ─────────────────────────────────────────────────────

class RootCause:
    CPU_RUNAWAY          = "cpu_runaway"
    MEMORY_LEAK          = "memory_leak"
    MEMORY_PRESSURE      = "memory_pressure"
    DISK_PRESSURE        = "disk_pressure"
    THRASH               = "cpu_memory_thrash"
    ANOMALOUS_SPIKE      = "anomalous_spike"
    FORECAST_BREACH      = "forecast_breach"
    SYSTEM_WIDE_PRESSURE = "system_wide_pressure"
    UNKNOWN              = "unknown"


@dataclass
class CausalFactor:
    """One link in the causal chain."""
    factor: str          # short name
    evidence: str        # plain-English evidence
    weight: float        # 0.0–1.0, contribution to confidence


@dataclass
class RemediationStep:
    """One recommended action."""
    priority: int        # 1 = highest
    action: str          # action_type string (e.g. "renice", "kill")
    description: str


@dataclass
class RootCauseDiagnosis:
    """Structured root-cause diagnosis for one incident."""
    incident_id: str
    pid: int
    process_name: str

    root_cause: str                     # RootCause constant
    confidence: float                   # 0.0–1.0

    causal_chain: List[CausalFactor] = field(default_factory=list)
    remediation_steps: List[RemediationStep] = field(default_factory=list)

    # Snapshot of key metrics at diagnosis time
    cpu_at_diagnosis: Optional[float] = None
    memory_mb_at_diagnosis: Optional[float] = None
    system_ram_pct_at_diagnosis: Optional[float] = None
    disk_pct_at_diagnosis: Optional[float] = None

    summary: str = ""                   # plain-English paragraph
    diagnosed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── Diagnosis Engine ─────────────────────────────────────────────────────────

class RootCauseDiagnosisEngine:
    """
    Synthesizes all available signals into a structured RootCauseDiagnosis.

    Usage:
        engine = RootCauseDiagnosisEngine()
        diagnosis = engine.diagnose(
            incident_id="inc-abc",
            proc=proc_snapshot,
            system_metrics=metrics,
            anomaly_results=anomaly_results,
            forecast=forecast_result,
            memory_finding=memory_finding,
            sustained_result=sustained_result,
        )
    """

    def diagnose(
        self,
        incident_id: str,
        proc: ProcessSnapshot,
        system_metrics: Optional[SystemMetrics] = None,
        anomaly_results: Optional[List[AnomalyResult]] = None,
        forecast: Optional[ForecastResult] = None,
        memory_finding: Optional[MemoryFinding] = None,
        sustained_result: Optional[SustainedCheckResult] = None,
    ) -> RootCauseDiagnosis:

        causal_chain: List[CausalFactor] = []
        remediation: List[RemediationStep] = []

        anomaly_results = anomaly_results or []
        cpu_anomaly  = next((r for r in anomaly_results if r.metric == "cpu_percent" and r.is_anomalous), None)
        mem_anomaly  = next((r for r in anomaly_results if r.metric == "memory_mb"   and r.is_anomalous), None)

        # ── Signal 1: Memory finding ──────────────────────────────────────────
        if memory_finding and memory_finding.kind == MemoryFindingKind.POSSIBLE_LEAK:
            causal_chain.append(CausalFactor(
                factor="memory_leak_pattern",
                evidence=memory_finding.description,
                weight=0.9,
            ))

        if memory_finding and memory_finding.kind == MemoryFindingKind.GROWTH:
            causal_chain.append(CausalFactor(
                factor="memory_growth",
                evidence=memory_finding.description,
                weight=0.6,
            ))

        if memory_finding and memory_finding.kind == MemoryFindingKind.SYSTEM_PRESSURE:
            causal_chain.append(CausalFactor(
                factor="system_memory_pressure",
                evidence=memory_finding.description,
                weight=0.7,
            ))

        # ── Signal 2: Anomaly detection ────────────────────────────────────────
        if cpu_anomaly:
            causal_chain.append(CausalFactor(
                factor="cpu_anomaly",
                evidence=cpu_anomaly.explanation,
                weight=0.7 + abs(cpu_anomaly.score) * 0.3,
            ))

        if mem_anomaly:
            causal_chain.append(CausalFactor(
                factor="memory_anomaly",
                evidence=mem_anomaly.explanation,
                weight=0.7 + abs(mem_anomaly.score) * 0.3,
            ))

        # ── Signal 3: Sustained pressure ───────────────────────────────────────
        if sustained_result and sustained_result.is_sustained:
            elapsed = sustained_result.elapsed_elevated_seconds
            causal_chain.append(CausalFactor(
                factor="sustained_pressure",
                evidence=(
                    f"Process sustained elevated resource usage for {elapsed:.0f}s "
                    f"({sustained_result.elevated_samples_in_window}/"
                    f"{sustained_result.total_samples_in_window} samples above threshold)."
                ),
                weight=0.5 + min(0.4, elapsed / 300.0),
            ))

        # ── Signal 4: Forecast ─────────────────────────────────────────────────
        if forecast and forecast.minutes_until_breach is not None:
            mins = forecast.minutes_until_breach
            weight = 0.9 if mins <= 2 else (0.7 if mins <= 5 else 0.5)
            causal_chain.append(CausalFactor(
                factor="forecast_breach",
                evidence=forecast.explanation,
                weight=weight,
            ))

        # ── Signal 5: Absolute thresholds ──────────────────────────────────────
        if proc.cpu_percent >= 95.0:
            causal_chain.append(CausalFactor(
                factor="cpu_critical_threshold",
                evidence=f"CPU at {proc.cpu_percent:.1f}% — exceeds critical 95% threshold.",
                weight=0.8,
            ))
        elif proc.cpu_percent >= 85.0:
            causal_chain.append(CausalFactor(
                factor="cpu_warning_threshold",
                evidence=f"CPU at {proc.cpu_percent:.1f}% — exceeds warning 85% threshold.",
                weight=0.5,
            ))

        if system_metrics:
            if system_metrics.ram_percent >= 92.0:
                causal_chain.append(CausalFactor(
                    factor="system_ram_critical",
                    evidence=f"System RAM at {system_metrics.ram_percent:.1f}%.",
                    weight=0.8,
                ))
            if system_metrics.disk.percent >= 90.0:
                causal_chain.append(CausalFactor(
                    factor="disk_pressure",
                    evidence=f"Disk at {system_metrics.disk.percent:.1f}% — nearly full.",
                    weight=0.7,
                ))

        # ── Determine root cause ──────────────────────────────────────────────
        root_cause, confidence = self._determine_root_cause(
            causal_chain=causal_chain,
            cpu_anomaly=cpu_anomaly,
            mem_anomaly=mem_anomaly,
            memory_finding=memory_finding,
            forecast=forecast,
            proc=proc,
            system_metrics=system_metrics,
        )

        # ── Build remediation steps ───────────────────────────────────────────
        remediation = self._recommend_remediation(
            root_cause=root_cause,
            confidence=confidence,
            proc=proc,
            forecast=forecast,
        )

        # ── Build summary ────────────────────────────────────────────────────
        summary = self._build_summary(
            proc=proc,
            root_cause=root_cause,
            confidence=confidence,
            causal_chain=causal_chain,
            remediation=remediation,
        )

        return RootCauseDiagnosis(
            incident_id=incident_id,
            pid=proc.pid,
            process_name=proc.name,
            root_cause=root_cause,
            confidence=round(min(1.0, confidence), 3),
            causal_chain=causal_chain,
            remediation_steps=remediation,
            cpu_at_diagnosis=proc.cpu_percent,
            memory_mb_at_diagnosis=proc.memory_mb,
            system_ram_pct_at_diagnosis=system_metrics.ram_percent if system_metrics else None,
            disk_pct_at_diagnosis=system_metrics.disk.percent if system_metrics else None,
            summary=summary,
        )

    # ── Private ─────────────────────────────────────────────────────────────────

    def _determine_root_cause(
        self,
        causal_chain: List[CausalFactor],
        cpu_anomaly: Optional[AnomalyResult],
        mem_anomaly: Optional[AnomalyResult],
        memory_finding: Optional[MemoryFinding],
        forecast: Optional[ForecastResult],
        proc: ProcessSnapshot,
        system_metrics: Optional[SystemMetrics],
    ) -> tuple[str, float]:

        # Find highest-weight factor
        if not causal_chain:
            return RootCause.UNKNOWN, 0.1

        weights_by_factor = {f.factor: f.weight for f in causal_chain}
        max_factor = max(weights_by_factor, key=lambda k: weights_by_factor[k])
        max_weight = weights_by_factor[max_factor]

        # Aggregate confidence = weighted average
        total_w = sum(f.weight for f in causal_chain)
        n = len(causal_chain)
        avg_weight = total_w / n if n else 0.0

        confidence = min(1.0, avg_weight * (1 + 0.1 * min(n, 5)))

        # Map leading factor to root cause
        if max_factor == "memory_leak_pattern":
            return RootCause.MEMORY_LEAK, confidence
        if max_factor == "system_memory_pressure":
            return RootCause.SYSTEM_WIDE_PRESSURE, confidence
        if max_factor == "memory_growth" and cpu_anomaly:
            return RootCause.THRASH, confidence
        if max_factor == "forecast_breach":
            return RootCause.FORECAST_BREACH, confidence
        if max_factor == "cpu_critical_threshold" or max_factor == "cpu_anomaly":
            if mem_anomaly:
                return RootCause.THRASH, confidence
            return RootCause.CPU_RUNAWAY, confidence
        if max_factor in ("memory_anomaly", "memory_growth"):
            return RootCause.MEMORY_PRESSURE, confidence
        if max_factor == "disk_pressure" or max_factor == "system_disk_pressure":
            return RootCause.DISK_PRESSURE, confidence
        if max_factor in ("cpu_warning_threshold", "memory_leak_pattern"):
            return RootCause.ANOMALOUS_SPIKE, confidence

        return RootCause.UNKNOWN, confidence

    @staticmethod
    def _recommend_remediation(
        root_cause: str,
        confidence: float,
        proc: ProcessSnapshot,
        forecast: Optional[ForecastResult],
    ) -> List[RemediationStep]:
        steps: List[RemediationStep] = []

        urgency_high = (
            forecast is not None
            and forecast.minutes_until_breach is not None
            and forecast.minutes_until_breach <= 5
        )

        if root_cause == RootCause.CPU_RUNAWAY:
            steps.append(RemediationStep(1, "renice", "Lower CPU scheduling priority."))
            if urgency_high or proc.cpu_percent >= 95.0:
                steps.append(RemediationStep(2, "restart", "Restart process if CPU does not drop within 2 minutes."))

        elif root_cause == RootCause.MEMORY_LEAK:
            steps.append(RemediationStep(1, "alert_only", "Flag for operator review — possible memory leak."))
            steps.append(RemediationStep(2, "restart", "Restart process to reclaim leaked memory."))

        elif root_cause == RootCause.MEMORY_PRESSURE:
            steps.append(RemediationStep(1, "renice", "Reduce memory pressure via lower scheduling priority."))
            steps.append(RemediationStep(2, "restart", "Restart if memory usage does not decline after 2 minutes."))

        elif root_cause == RootCause.THRASH:
            steps.append(RemediationStep(1, "throttle", "Throttle process to reduce both CPU and memory pressure."))
            steps.append(RemediationStep(2, "restart", "Restart if throttle does not resolve within 5 minutes."))

        elif root_cause == RootCause.FORECAST_BREACH:
            if forecast and forecast.minutes_until_breach is not None and forecast.minutes_until_breach <= 2:
                steps.append(RemediationStep(1, "restart", "Imminent breach — restart immediately."))
            else:
                steps.append(RemediationStep(1, "renice", "Lower priority to slow resource growth."))
                steps.append(RemediationStep(2, "restart", "Restart if breach trajectory does not improve."))

        elif root_cause == RootCause.DISK_PRESSURE:
            steps.append(RemediationStep(1, "alert_only", "Alert operator — disk nearly full."))
            steps.append(RemediationStep(2, "observe", "Run disk cleanup to reclaim temp file space."))

        elif root_cause == RootCause.SYSTEM_WIDE_PRESSURE:
            steps.append(RemediationStep(1, "alert_only", "System-wide RAM pressure — operator intervention recommended."))

        else:  # ANOMALOUS_SPIKE, UNKNOWN
            steps.append(RemediationStep(1, "alert_only", "Investigate further — cause uncertain."))

        return steps

    @staticmethod
    def _build_summary(
        proc: ProcessSnapshot,
        root_cause: str,
        confidence: float,
        causal_chain: List[CausalFactor],
        remediation: List[RemediationStep],
    ) -> str:
        factors_str = "; ".join(f.factor for f in causal_chain[:3])
        remed_str = "; ".join(s.description for s in remediation[:2])
        return (
            f"Root-cause diagnosis for '{proc.name}' (PID {proc.pid}): "
            f"{root_cause.replace('_', ' ').title()} "
            f"(confidence {confidence:.0%}). "
            f"Key factors: {factors_str}. "
            f"Recommended actions: {remed_str}."
        )
