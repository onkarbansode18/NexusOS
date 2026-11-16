"""
Nexus 2.0 — Application-Aware Resource Management Package
"""

from app.application_manager.application_models import (
    ApplicationCategory,
    ApplicationImportance,
    ApplicationLifecycleEvent,
    ProcessDetail,
    ApplicationEntity,
    ApplicationEvent,
)
from app.application_manager.process_tree import ProcessTreeResolver
from app.application_manager.process_classifier import ProcessClassifier
from app.application_manager.application_registry import ApplicationRegistry
from app.application_manager.application_detector import ApplicationDetector
from app.application_manager.profile_manager import (
    ProfileManager,
    ProfilePrecedenceLevel,
    profile_manager,
)
from app.application_manager.mode_manager import (
    ModeManager,
    OperatingModeType,
    DEFAULT_MODE_CONFIGS,
    mode_manager,
)
from app.application_manager.optimization_planner import (
    OptimizationPlan,
    OptimizationPlanItem,
)
from app.application_manager.resource_optimizer import (
    ResourceOptimizer,
    OptimizationStrategy,
    resource_optimizer,
)

__all__ = [
    "ApplicationCategory",
    "ApplicationImportance",
    "ApplicationLifecycleEvent",
    "ProcessDetail",
    "ApplicationEntity",
    "ApplicationEvent",
    "ProcessTreeResolver",
    "ProcessClassifier",
    "ApplicationRegistry",
    "ApplicationDetector",
    "ProfileManager",
    "ProfilePrecedenceLevel",
    "profile_manager",
    "ModeManager",
    "OperatingModeType",
    "DEFAULT_MODE_CONFIGS",
    "mode_manager",
    "OptimizationPlan",
    "OptimizationPlanItem",
    "ResourceOptimizer",
    "OptimizationStrategy",
    "resource_optimizer",
]
