"""
Nexus 2.0 — Application-Aware Resource Management
Optimization Planner: Formulates structured, transparent resource optimization plans
before any action is taken. Validates every target against Nexus safety policies.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class OptimizationPlanItem:
    """A concrete proposed priority action targeting a specific process."""
    plan_item_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    app_id: str = ""
    app_name: str = ""
    pid: int = 0
    process_name: str = ""
    current_priority: str = "NORMAL"
    proposed_action: str = "renice"  # renice / throttle / restore_priority / observe_only
    reason: str = ""
    expected_effect: str = ""
    risk_level: str = "low"  # low / medium / high
    safety_validation: str = "PASSED"
    is_safe: bool = True
    current_cpu: float = 0.0
    current_mem_mb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_item_id": self.plan_item_id,
            "app_id": self.app_id,
            "app_name": self.app_name,
            "pid": self.pid,
            "process_name": self.process_name,
            "current_priority": self.current_priority,
            "proposed_action": self.proposed_action,
            "reason": self.reason,
            "expected_effect": self.expected_effect,
            "risk_level": self.risk_level,
            "safety_validation": self.safety_validation,
            "is_safe": self.is_safe,
            "current_cpu": round(self.current_cpu, 2),
            "current_mem_mb": round(self.current_mem_mb, 2),
        }


@dataclass
class OptimizationPlan:
    """A collection of evaluated candidate actions generated for the system."""
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    active_mode: Optional[str] = None
    system_cpu_percent: float = 0.0
    system_ram_percent: float = 0.0
    recommendations: List[OptimizationPlanItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "timestamp": self.timestamp,
            "active_mode": self.active_mode,
            "system_cpu_percent": round(self.system_cpu_percent, 2),
            "system_ram_percent": round(self.system_ram_percent, 2),
            "recommendations": [item.to_dict() for item in self.recommendations],
            "total_items": len(self.recommendations),
            "actionable_items": len([i for i in self.recommendations if i.is_safe and i.proposed_action != "observe_only"]),
        }
