"""
Nexus 2.0 — Application-Aware Resource Management
Resource Optimizer: Analyzes system resource contention, operating mode directives,
and application importance to safely optimize scheduling priorities.
Implements anti-flapping cooldowns, safety gating, and rollback capabilities.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import psutil
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_manager.application_detector import ApplicationDetector
from app.application_manager.application_models import ApplicationEntity, ApplicationImportance
from app.application_manager.mode_manager import mode_manager, OperatingModeType
from app.application_manager.optimization_planner import OptimizationPlan, OptimizationPlanItem
from app.application_manager.profile_manager import profile_manager, ProfilePrecedenceLevel
from app.db.models import ApplicationOptimizationRecord
from app.decision.engine import ActionType
from app.executor.actions import ActionExecutor, ActionResult

logger = logging.getLogger("nexus.optimizer")


class OptimizationStrategy:
    RECOMMENDATION_ONLY = "recommendation_only"
    MANUAL_APPROVAL = "manual_approval"
    AUTONOMOUS = "autonomous"


class ResourceOptimizer:
    """
    Intelligent optimization engine.
    Identifies non-essential background workloads during resource contention or
    active operating modes, formulating safe priority reduction plans.
    """

    def __init__(
        self,
        strategy: str = OptimizationStrategy.RECOMMENDATION_ONLY,
        action_cooldown_seconds: float = 60.0,
    ) -> None:
        self.is_enabled: bool = True
        self.strategy: str = strategy
        self.action_cooldown_seconds: float = action_cooldown_seconds

        # Anti-flapping: {pid: last_action_timestamp}
        self._action_cooldowns: Dict[int, float] = {}

        # Pending unapproved recommendations waiting for user approval
        self._pending_recommendations: Dict[str, OptimizationPlanItem] = {}

        # Latest generated plan
        self._latest_plan: Optional[OptimizationPlan] = None

    # ── Control & Configuration ───────────────────────────────────────────────

    def enable(self) -> None:
        self.is_enabled = True
        logger.info("Application Resource Optimizer ENABLED.")

    def disable(self) -> None:
        self.is_enabled = False
        logger.info("Application Resource Optimizer DISABLED.")

    def set_strategy(self, strategy: str) -> None:
        if strategy not in [
            OptimizationStrategy.RECOMMENDATION_ONLY,
            OptimizationStrategy.MANUAL_APPROVAL,
            OptimizationStrategy.AUTONOMOUS,
        ]:
            raise ValueError(f"Invalid strategy: '{strategy}'")
        self.strategy = strategy
        logger.info("Optimizer strategy updated to: %s", strategy)

    async def emergency_disable(self, executor: ActionExecutor, db: Optional[AsyncSession] = None) -> int:
        """
        Emergency stop: disables optimization immediately and restores
        normal priority for all modified processes.
        """
        self.is_enabled = False
        self._pending_recommendations.clear()
        restored = await mode_manager.restore_modified_priorities(executor)
        logger.warning("EMERGENCY DISABLE TRIGGERED: Optimizer halted, %d priorities restored.", restored)
        return restored

    # ── Plan Formulation & Analysis ───────────────────────────────────────────

    def analyze_and_plan(
        self,
        applications: List[ApplicationEntity],
        system_cpu_percent: float,
        system_ram_percent: float,
        user_whitelist: Optional[List[str]] = None,
        user_blacklist: Optional[List[str]] = None,
    ) -> OptimizationPlan:
        """
        Analyzes current running applications against active mode directives and
        resource pressure, generating an OptimizationPlan.
        """
        active_mode = mode_manager.active_mode_id
        plan = OptimizationPlan(
            active_mode=active_mode,
            system_cpu_percent=system_cpu_percent,
            system_ram_percent=system_ram_percent,
        )

        if not self.is_enabled:
            return plan

        now_mono = time.monotonic()
        mode_info = mode_manager.get_active_mode_info()
        active_config = mode_info.get("configuration", {})
        protected_apps = set(active_config.get("protected_apps", []))
        protected_cats = set(active_config.get("protected_categories", []))

        # Check each application
        for app in applications:
            # Skip if whole application is classified as a protected category in active mode
            if app.category.value in protected_cats:
                continue

            for proc in app.processes:
                # Anti-flapping: check cooldown
                last_act = self._action_cooldowns.get(proc.pid, 0.0)
                if now_mono - last_act < self.action_cooldown_seconds:
                    continue

                # Safety & Precedence Evaluation
                prec_level, is_opt, prec_reason = profile_manager.evaluate_precedence(
                    pid=proc.pid,
                    process_name=proc.name,
                    app_id=app.app_id,
                    active_mode_protected_apps=list(protected_apps),
                    user_blacklist=user_blacklist,
                )

                if not is_opt:
                    continue

                # Decision Logic according to active mode and resource footprint
                proposed_action: Optional[str] = None
                reason: str = ""
                risk_level: str = "low"
                expected: str = ""

                # Meeting Mode Logic
                if active_mode == OperatingModeType.MEETING:
                    if proc.cpu_percent >= 10.0 or proc.memory_percent >= 15.0:
                        proposed_action = ActionType.RENICE
                        reason = (
                            f"Meeting Mode active: non-essential background task '{proc.name}' "
                            f"(PID {proc.pid}, {proc.cpu_percent}% CPU) is competing with conference media streams."
                        )
                        expected = "Lower scheduling priority to Below Normal class to prevent audio/video stutter."

                # Gaming Mode Logic
                elif active_mode == OperatingModeType.GAMING:
                    if proc.cpu_percent >= 8.0:
                        proposed_action = ActionType.RENICE
                        reason = (
                            f"Gaming Mode active: background task '{proc.name}' ({proc.cpu_percent}% CPU) "
                            f"is stealing frame rendering cycles."
                        )
                        expected = "De-prioritize to Below Normal class to preserve GPU/CPU frame-times."

                # Battery Saver Mode Logic
                elif active_mode == OperatingModeType.BATTERY_SAVER:
                    if proc.cpu_percent >= 12.0:
                        proposed_action = ActionType.THROTTLE
                        reason = (
                            f"Battery Saver Mode active: background process '{proc.name}' is maintaining "
                            f"elevated CPU load ({proc.cpu_percent}%), causing battery drain."
                        )
                        expected = "Throttle scheduling to Idle class to minimize power consumption."

                # Standard Mode Resource Contention Logic
                else:
                    if system_cpu_percent >= 80.0 and proc.cpu_percent >= 20.0:
                        proposed_action = ActionType.RENICE
                        reason = (
                            f"System CPU contention ({system_cpu_percent}%): background task '{proc.name}' "
                            f"consuming {proc.cpu_percent}% CPU."
                        )
                        expected = "Lower process priority to relieve interactive CPU pressure."

                if proposed_action:
                    item = OptimizationPlanItem(
                        app_id=app.app_id,
                        app_name=app.name,
                        pid=proc.pid,
                        process_name=proc.name,
                        current_priority=proc.priority or "NORMAL",
                        proposed_action=proposed_action,
                        reason=reason,
                        expected_effect=expected,
                        risk_level=risk_level,
                        safety_validation="PASSED",
                        is_safe=True,
                        current_cpu=proc.cpu_percent,
                        current_mem_mb=proc.memory_mb,
                    )
                    plan.recommendations.append(item)
                    self._pending_recommendations[item.plan_item_id] = item

        self._latest_plan = plan
        return plan

    # ── Action Execution ──────────────────────────────────────────────────────

    async def execute_plan_item(
        self,
        item: OptimizationPlanItem,
        executor: ActionExecutor,
        db: Optional[AsyncSession] = None,
    ) -> ActionResult:
        """
        Executes a planned optimization item strictly through the existing ActionExecutor.
        Enforces PID reuse validation, records before/after state, and persists audit logs.
        """
        if not self.is_enabled:
            return ActionResult(
                action_type=item.proposed_action,
                pid=item.pid,
                process_name=item.process_name,
                simulated=executor.simulation_mode,
                success=False,
                reason="Optimization engine is currently disabled.",
                error="OptimizerDisabled",
            )

        # PID validation (Prevent acting on recycled PIDs)
        if not psutil.pid_exists(item.pid):
            return ActionResult(
                action_type=item.proposed_action,
                pid=item.pid,
                process_name=item.process_name,
                simulated=executor.simulation_mode,
                success=False,
                reason="Process exited before action could be dispatched.",
                error="NoSuchProcess",
            )

        try:
            current_proc = psutil.Process(item.pid)
            if current_proc.name().lower() != item.process_name.lower():
                return ActionResult(
                    action_type=item.proposed_action,
                    pid=item.pid,
                    process_name=item.process_name,
                    simulated=executor.simulation_mode,
                    success=False,
                    reason="PID reuse detected: process identity changed.",
                    error="PIDReuseDetected",
                )
        except Exception as e:
            return ActionResult(
                action_type=item.proposed_action,
                pid=item.pid,
                process_name=item.process_name,
                simulated=executor.simulation_mode,
                success=False,
                reason=f"Failed to verify process: {e}",
                error=str(e),
            )

        # Remember original priority for clean restoration on mode exit
        mode_manager.record_priority_modification(item.pid, item.current_priority)

        # Dispatch action through ActionExecutor
        action_type = item.proposed_action
        if action_type == ActionType.RENICE:
            result = executor.renice(item.pid, item.process_name)
        elif action_type == ActionType.THROTTLE:
            result = executor.throttle(item.pid, item.process_name)
        elif action_type == ActionType.RESTORE_PRIORITY:
            result = executor.restore_priority(item.pid, item.process_name)
        else:
            result = ActionResult(
                action_type=action_type,
                pid=item.pid,
                process_name=item.process_name,
                simulated=executor.simulation_mode,
                success=True,
                reason=item.reason,
            )

        # Record cooldown to prevent flapping
        self._action_cooldowns[item.pid] = time.monotonic()
        self._pending_recommendations.pop(item.plan_item_id, None)

        # Persist audit record to database
        if db:
            opt_rec = ApplicationOptimizationRecord(
                app_id=item.app_id,
                app_name=item.app_name,
                pid=item.pid,
                action_type=action_type,
                operating_mode=mode_manager.active_mode_id,
                status="executed" if result.success else "failed",
                risk_level=item.risk_level,
                reason=item.reason,
                before_priority=item.current_priority,
                after_priority="BELOW_NORMAL" if action_type == ActionType.RENICE else ("IDLE" if action_type == ActionType.THROTTLE else "NORMAL"),
                before_cpu=result.before_cpu,
                before_memory_mb=result.before_memory_mb,
                after_cpu=result.after_cpu,
                after_memory_mb=result.after_memory_mb,
                executed_at=datetime.now(timezone.utc),
            )
            db.add(opt_rec)
            await db.commit()

        return result

    def get_pending_recommendations(self) -> List[OptimizationPlanItem]:
        """Returns all unapproved optimization recommendations."""
        return list(self._pending_recommendations.values())

    def get_recommendation(self, plan_item_id: str) -> Optional[OptimizationPlanItem]:
        return self._pending_recommendations.get(plan_item_id)

    def reject_recommendation(self, plan_item_id: str) -> bool:
        if plan_item_id in self._pending_recommendations:
            del self._pending_recommendations[plan_item_id]
            return True
        return False


resource_optimizer = ResourceOptimizer()
