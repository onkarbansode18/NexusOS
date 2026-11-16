"""
Nexus 2.0 — Application-Aware Resource Management
Profile Manager: Manages application profiles, importance hierarchies,
protected status, user-defined optimization preferences, and policy precedence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_manager.application_models import (
    ApplicationCategory,
    ApplicationImportance,
)
from app.db.models import ApplicationProfileRecord
from app.decision.engine import SYSTEM_PIDS, SYSTEM_PROCESS_BLACKLIST

logger = logging.getLogger("nexus.profile_manager")


class ProfilePrecedenceLevel:
    OS_PROTECTION = 100
    NEXUS_BLACKLIST = 90
    USER_PROTECTED = 80
    ACTIVE_MODE_PROTECTED = 70
    IMPORTANCE_CRITICAL = 60
    IMPORTANCE_HIGH = 50
    IMPORTANCE_NORMAL = 40
    IMPORTANCE_LOW = 30
    IMPORTANCE_BACKGROUND = 20


class ProfileManager:
    """
    Manages persistent Application Profiles and evaluates precedence rules.
    Maintains an in-memory mirror for low-latency pipeline evaluation.
    """

    def __init__(self) -> None:
        # In-memory cached profiles indexed by app_id
        self._profiles: Dict[str, ApplicationProfileRecord] = {}

    def get_cached_profile(self, app_id: str) -> Optional[ApplicationProfileRecord]:
        """Returns the in-memory cached profile if present."""
        return self._profiles.get(app_id)

    def get_all_cached_profiles(self) -> List[ApplicationProfileRecord]:
        """Returns all cached profiles."""
        return list(self._profiles.values())

    async def load_profiles_from_db(self, db: AsyncSession) -> List[ApplicationProfileRecord]:
        """Loads all profiles from the database into the memory cache."""
        stmt = select(ApplicationProfileRecord).order_by(ApplicationProfileRecord.name.asc())
        result = await db.execute(stmt)
        profiles = list(result.scalars().all())
        self._profiles = {p.app_id: p for p in profiles}
        logger.info("Loaded %d application profiles from database.", len(self._profiles))
        return profiles

    async def get_or_create_profile(
        self,
        db: AsyncSession,
        app_id: str,
        name: str,
        executable_path: Optional[str] = None,
        category: str = "Unknown",
        importance: str = "Normal",
        is_protected: bool = False,
    ) -> ApplicationProfileRecord:
        """Finds existing profile or creates a sensible default."""
        stmt = select(ApplicationProfileRecord).where(ApplicationProfileRecord.app_id == app_id)
        res = await db.execute(stmt)
        profile = res.scalar_one_or_none()

        if profile is None:
            profile = ApplicationProfileRecord(
                app_id=app_id,
                name=name,
                executable_path=executable_path,
                category=category,
                importance=importance,
                preferred_priority="NORMAL",
                is_protected=is_protected,
                is_enabled=True,
                allowed_actions=["renice", "restore_priority"],
                associated_modes=[],
            )
            db.add(profile)
            await db.commit()
            await db.refresh(profile)

        self._profiles[app_id] = profile
        return profile

    async def update_profile(
        self,
        db: AsyncSession,
        app_id: str,
        importance: Optional[str] = None,
        is_protected: Optional[bool] = None,
        category: Optional[str] = None,
        preferred_priority: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        allowed_actions: Optional[List[str]] = None,
        associated_modes: Optional[List[str]] = None,
        user_notes: Optional[str] = None,
        max_cpu_percent: Optional[float] = None,
        max_memory_mb: Optional[float] = None,
    ) -> Optional[ApplicationProfileRecord]:
        """Updates an application profile persistently."""
        stmt = select(ApplicationProfileRecord).where(ApplicationProfileRecord.app_id == app_id)
        res = await db.execute(stmt)
        profile = res.scalar_one_or_none()

        if not profile:
            return None

        if importance is not None:
            profile.importance = importance
        if is_protected is not None:
            profile.is_protected = is_protected
        if category is not None:
            profile.category = category
        if preferred_priority is not None:
            profile.preferred_priority = preferred_priority
        if is_enabled is not None:
            profile.is_enabled = is_enabled
        if allowed_actions is not None:
            profile.allowed_actions = allowed_actions
        if associated_modes is not None:
            profile.associated_modes = associated_modes
        if user_notes is not None:
            profile.user_notes = user_notes
        if max_cpu_percent is not None:
            profile.max_cpu_percent = max_cpu_percent
        if max_memory_mb is not None:
            profile.max_memory_mb = max_memory_mb

        profile.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(profile)
        self._profiles[app_id] = profile
        return profile

    async def delete_profile(self, db: AsyncSession, app_id: str) -> bool:
        """Deletes an application profile."""
        stmt = delete(ApplicationProfileRecord).where(ApplicationProfileRecord.app_id == app_id)
        res = await db.execute(stmt)
        await db.commit()
        self._profiles.pop(app_id, None)
        return res.rowcount > 0

    # ── Precedence Evaluation ─────────────────────────────────────────────────

    def evaluate_precedence(
        self,
        pid: int,
        process_name: str,
        app_id: Optional[str],
        active_mode_protected_apps: Optional[List[str]] = None,
        user_blacklist: Optional[List[str]] = None,
    ) -> tuple[int, bool, str]:
        """
        Evaluates safety and priority precedence:
        Returns: (precedence_level, is_optimizable, reason)

        Hierarchy:
        1. Critical OS protection (SYSTEM_PIDS, SYSTEM_PROCESS_BLACKLIST) -> Never optimizable
        2. Nexus Blacklist -> Never optimizable
        3. Explicit User Protection (Profile.is_protected) -> Protected
        4. Active Operating Mode Protection -> Protected
        5. Critical Importance -> Protected
        6. High Importance -> Optimizable only with high threshold
        7. Normal / Low / Background -> Optimizable according to policy
        """
        clean_name = process_name.lower().removesuffix(".exe")

        # 1. Critical OS protection
        if pid in SYSTEM_PIDS or process_name.lower() in SYSTEM_PROCESS_BLACKLIST or clean_name in SYSTEM_PROCESS_BLACKLIST:
            return (
                ProfilePrecedenceLevel.OS_PROTECTION,
                False,
                f"Critical OS system process '{process_name}' (PID {pid}) is permanently protected.",
            )

        # 2. Nexus Blacklist
        if user_blacklist:
            bl_set = {n.lower().removesuffix(".exe") for n in user_blacklist}
            if clean_name in bl_set or process_name.lower() in bl_set:
                return (
                    ProfilePrecedenceLevel.NEXUS_BLACKLIST,
                    False,
                    f"Process '{process_name}' is explicitly blacklisted in Nexus policies.",
                )

        profile = self._profiles.get(app_id) if app_id else None

        # 3. Explicit User Protection
        if profile and profile.is_protected:
            return (
                ProfilePrecedenceLevel.USER_PROTECTED,
                False,
                f"Application '{profile.name}' is explicitly protected by user configuration.",
            )

        # 4. Active Mode Protection
        if active_mode_protected_apps and app_id:
            if app_id in active_mode_protected_apps or (profile and profile.name in active_mode_protected_apps):
                return (
                    ProfilePrecedenceLevel.ACTIVE_MODE_PROTECTED,
                    False,
                    f"Application is protected by the active operating mode.",
                )

        # 5. Application Importance
        if profile:
            imp = profile.importance.lower()
            if imp == "critical":
                return (
                    ProfilePrecedenceLevel.IMPORTANCE_CRITICAL,
                    False,
                    f"Application '{profile.name}' is marked with Critical importance.",
                )
            elif imp == "high":
                return (
                    ProfilePrecedenceLevel.IMPORTANCE_HIGH,
                    True,
                    f"Application '{profile.name}' has High importance (requires conservative thresholds).",
                )
            elif imp == "low":
                return (
                    ProfilePrecedenceLevel.IMPORTANCE_LOW,
                    True,
                    f"Application '{profile.name}' has Low importance and is eligible for priority reduction.",
                )
            elif imp == "background":
                return (
                    ProfilePrecedenceLevel.IMPORTANCE_BACKGROUND,
                    True,
                    f"Application '{profile.name}' is designated as Background workload.",
                )

        # Default: Normal Importance
        return (
            ProfilePrecedenceLevel.IMPORTANCE_NORMAL,
            True,
            f"Process '{process_name}' has normal importance.",
        )


profile_manager = ProfileManager()
