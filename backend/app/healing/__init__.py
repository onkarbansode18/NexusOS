"""
Nexus — Healing package initializer.
Exports the main healing components for use from other modules.
"""

from .sustained_tracker import SustainedPressureTracker, SustainedCheckResult
from .memory_analyser import MemoryLeakAnalyser, MemoryFinding, MemoryFindingKind
from .cooldown import ActionCooldownManager, CooldownCheckResult
from .recovery_verifier import RecoveryVerifier, VerificationResult, VerificationState
from .disk_manager import DiskManager, DiskReport, CleanupPlan, DirScanResult
from .rca_engine import RootCauseDiagnosisEngine, RootCauseDiagnosis, RootCause

# Shared runtime singletons
sustained_tracker = SustainedPressureTracker()
memory_analyser   = MemoryLeakAnalyser()
cooldown_manager  = ActionCooldownManager()
recovery_verifier = RecoveryVerifier()
disk_manager      = DiskManager()
rca_engine        = RootCauseDiagnosisEngine()

__all__ = [
    "SustainedPressureTracker", "SustainedCheckResult",
    "MemoryLeakAnalyser", "MemoryFinding", "MemoryFindingKind",
    "ActionCooldownManager", "CooldownCheckResult",
    "RecoveryVerifier", "VerificationResult", "VerificationState",
    "DiskManager", "DiskReport", "CleanupPlan", "DirScanResult",
    "RootCauseDiagnosisEngine", "RootCauseDiagnosis", "RootCause",
    "sustained_tracker", "memory_analyser", "cooldown_manager",
    "recovery_verifier", "disk_manager", "rca_engine",
]

