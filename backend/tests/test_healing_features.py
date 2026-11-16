"""
Nexus — Automated Test Suite for 5 Master Features
===================================================
1. Autonomous Self-Healing Engine (sustained tracker, cooldown, emergency stop, verification)
2. Memory Leak and Memory Pressure Detection
3. Intelligent Resource Optimization (priority restoration)
4. Disk Space and Temporary File Management
5. Root-Cause Diagnosis and Recovery History
"""

import asyncio
import time
from pathlib import Path

from app.healing.sustained_tracker import SustainedPressureTracker
from app.healing.memory_analyser import MemoryLeakAnalyser, MemoryFindingKind
from app.healing.cooldown import ActionCooldownManager
from app.healing.recovery_verifier import RecoveryVerifier, VerificationState
from app.healing.disk_manager import DiskManager, _FORBIDDEN_ROOT_PATHS, _PROTECTED_PATTERNS
from app.healing.rca_engine import RootCauseDiagnosisEngine, RootCause
from app.decision.engine import ActionType
from app.executor.actions import ActionExecutor
from app.monitoring.agent import ProcessSnapshot, SystemMetrics, DiskUsage, NetworkIO
from app.ml.anomaly import AnomalyResult


# ── Feature 1: Sustained Pressure Tracker ─────────────────────────────────────

def test_sustained_pressure_tracker_ignores_transient_spikes():
    tracker = SustainedPressureTracker(
        cpu_threshold=80.0,
        sustained_seconds=10.0,
        sample_interval=2.0,
    )
    # Single spike
    res1 = tracker.update(pid=101, name="worker.exe", creation_key="101_1", cpu_percent=95.0, memory_mb=200.0)
    assert not res1.is_sustained_cpu
    assert res1.consecutive_elevated == 1

    # Returns to normal
    res2 = tracker.update(pid=101, name="worker.exe", creation_key="101_1", cpu_percent=40.0, memory_mb=200.0)
    assert not res2.is_sustained_cpu
    assert res2.consecutive_elevated == 0


def test_sustained_pressure_tracker_detects_sustained_elevation():
    tracker = SustainedPressureTracker(
        cpu_threshold=80.0,
        sustained_seconds=6.0,
        sample_interval=2.0,
    )
    # Feed multiple elevated samples
    for i in range(5):
        res = tracker.update(pid=202, name="compute.exe", creation_key="202_1", cpu_percent=88.0, memory_mb=300.0)
    
    assert res.is_sustained_cpu
    assert res.consecutive_elevated >= 3


# ── Feature 1: Action Cooldown & Emergency Stop ───────────────────────────────

def test_action_cooldown_and_emergency_stop():
    mgr = ActionCooldownManager(
        per_process_cooldown_seconds=60.0,
        max_actions_per_window=3,
        window_seconds=120.0,
    )

    # First action allowed
    chk1 = mgr.check(pid=301)
    assert chk1.allowed
    mgr.record(pid=301)

    # Immediate second action on same PID blocked by cooldown
    chk2 = mgr.check(pid=301)
    assert not chk2.allowed
    assert "cooldown active" in chk2.reason.lower()

    # Different PID allowed
    chk3 = mgr.check(pid=302)
    assert chk3.allowed
    mgr.record(pid=302)

    # Emergency stop blocks all
    mgr.trigger_emergency_stop("Manual safety halt")
    assert mgr.emergency_stop_active
    chk_blocked = mgr.check(pid=303)
    assert not chk_blocked.allowed
    assert "emergency stop active" in chk_blocked.reason.lower()

    # Clear emergency stop
    mgr.clear_emergency_stop()
    assert not mgr.emergency_stop_active


# ── Feature 1: Recovery Verification ──────────────────────────────────────────

async def test_recovery_verifier_simulated():
    verifier = RecoveryVerifier(default_observation_seconds=0.1)
    result = await verifier.verify(
        incident_id="inc-test",
        action_type="renice",
        pid=999999,
        process_name="test.exe",
        before_cpu=90.0,
        before_memory_mb=500.0,
        simulated=True,
    )
    assert result.state == VerificationState.SIMULATED
    assert result.simulated is True


# ── Feature 2: Memory Leak & Trend Analyser ───────────────────────────────────

def test_memory_leak_analyser_detects_growth_trend():
    analyser = MemoryLeakAnalyser(
        min_samples=5,
        growth_rate_mb_per_min=5.0,
        leak_rate_mb_per_min=15.0,
    )
    # Feed steady increasing memory (leak)
    for i in range(10):
        analyser.record_sample(
            pid=401,
            name="leak_app.exe",
            creation_key="401_1",
            rss_mb=100.0 + (i * 20.0),  # Rapid growth
            system_ram_percent=50.0,
        )
    finding = analyser.analyse(pid=401)
    assert finding.kind in (MemoryFindingKind.GROWTH, MemoryFindingKind.POSSIBLE_LEAK)
    assert finding.growth_rate_mb_per_min > 5.0
    assert finding.is_actionable


def test_memory_leak_analyser_identifies_normal_usage():
    analyser = MemoryLeakAnalyser(min_samples=5)
    # Feed stable memory
    for i in range(8):
        analyser.record_sample(
            pid=402,
            name="stable_app.exe",
            creation_key="402_1",
            rss_mb=250.0 + (i % 2),
            system_ram_percent=45.0,
        )
    finding = analyser.analyse(pid=402)
    assert finding.kind == MemoryFindingKind.NORMAL
    assert not finding.is_actionable


# ── Feature 3: Intelligent Resource Optimization (Priority Reversal) ──────────

def test_action_executor_restore_priority_simulation():
    executor = ActionExecutor(simulation_mode=True)
    res = executor.restore_priority(pid=501, process_name="worker.exe")
    assert res.success is True
    assert res.simulated is True
    assert res.action_type == ActionType.RESTORE_PRIORITY


def test_action_executor_safety_blacklist_protection():
    executor = ActionExecutor(simulation_mode=False)
    # explorer.exe is in permanent blacklist
    res = executor.kill(pid=1000, process_name="explorer.exe")
    assert res.success is False
    assert "safety guardrail" in res.reason.lower()


# ── Feature 4: Disk Space and Temporary File Management ───────────────────────

def test_disk_manager_safe_path_constraints(tmp_path: Path = None):
    manager = DiskManager(simulation_mode=True)

    # Forbidden root paths cannot be targeted
    for forbidden in _FORBIDDEN_ROOT_PATHS:
        assert not manager._is_safe_path(Path(forbidden))

    # Protected file patterns are recognized
    assert any("pagefile.sys" in p for p in _PROTECTED_PATTERNS)
    assert any("*.dll" in p for p in _PROTECTED_PATTERNS)

    # Report structure
    rep = manager.disk_report()
    assert rep.total_gb >= 0.0
    assert rep.used_percent >= 0.0


# ── Feature 5: Root-Cause Diagnosis Engine ────────────────────────────────────

def test_rca_engine_diagnoses_cpu_runaway():
    engine = RootCauseDiagnosisEngine()
    proc = ProcessSnapshot(
        pid=601,
        name="crypto_miner.exe",
        cpu_percent=98.5,
        memory_mb=120.0,
        memory_percent=2.0,
        status="running",
        username="user",
        num_threads=8,
        created_at=str(time.time()),
    )
    anomaly_results = [
        AnomalyResult(
            pid=601,
            process_name="crypto_miner.exe",
            metric="cpu_percent",
            score=-0.85,
            is_anomalous=True,
            explanation="CPU elevated 98.5%",
        )
    ]
    diag = engine.diagnose(
        incident_id="inc-rca-1",
        proc=proc,
        anomaly_results=anomaly_results,
    )
    assert diag.root_cause == RootCause.CPU_RUNAWAY
    assert diag.confidence > 0.5
    assert len(diag.causal_chain) > 0
    assert len(diag.remediation_steps) > 0
    assert any(step.action in ("renice", "throttle", "suspend") for step in diag.remediation_steps)


if __name__ == "__main__":
    print("Running Nexus Self-Healing Test Suite...")
    test_sustained_pressure_tracker_ignores_transient_spikes()
    print("  [PASS] 1. Sustained Pressure Tracker: Transient Spikes Ignored")
    test_sustained_pressure_tracker_detects_sustained_elevation()
    print("  [PASS] 2. Sustained Pressure Tracker: Sustained Elevation Detected")
    test_action_cooldown_and_emergency_stop()
    print("  [PASS] 3. Cooldown & Emergency Stop Enforced")
    asyncio.run(test_recovery_verifier_simulated())
    print("  [PASS] 4. Post-Action Recovery Verification")
    test_memory_leak_analyser_detects_growth_trend()
    print("  [PASS] 5. Memory Leak Trend Analyser: Growth & Leak Detection")
    test_memory_leak_analyser_identifies_normal_usage()
    print("  [PASS] 6. Memory Leak Trend Analyser: Stable Usage Recognition")
    test_action_executor_restore_priority_simulation()
    print("  [PASS] 7. Reversible Action: Priority Class Restoration")
    test_action_executor_safety_blacklist_protection()
    print("  [PASS] 8. Safety Guardrails: Permanent Blacklist Protection")
    test_disk_manager_safe_path_constraints()
    print("  [PASS] 9. Disk Space & Temp File Management: Safety Constraints & Audit")
    test_rca_engine_diagnoses_cpu_runaway()
    print("  [PASS] 10. Root-Cause Diagnosis Engine: Causal Chain & Remediation")
    print("\n>>> ALL 10 NEXUS SELF-HEALING ENGINE TESTS PASSED! <<<")


