"""
Nexus DB — SQLAlchemy models.
Designed so swapping the DATABASE_URL from sqlite+aiosqlite to
postgresql+asyncpg requires only changing the .env file — no model changes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ── SystemMetricsRecord ───────────────────────────────────────────────────────

class SystemMetricsRecord(Base):
    """One row per polling interval — rolling window, pruned by a background task."""

    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    # CPU
    cpu_percent       = Column(Float, nullable=False)
    cpu_freq_mhz      = Column(Float, nullable=True)
    cpu_count_logical = Column(Integer, nullable=True)

    # RAM
    ram_total_mb     = Column(Float, nullable=False)
    ram_used_mb      = Column(Float, nullable=False)
    ram_percent      = Column(Float, nullable=False)

    # Swap
    swap_total_mb = Column(Float, nullable=True)
    swap_used_mb  = Column(Float, nullable=True)
    swap_percent  = Column(Float, nullable=True)

    # Disk (primary)
    disk_path       = Column(String(255), nullable=True)
    disk_total_gb   = Column(Float, nullable=True)
    disk_used_gb    = Column(Float, nullable=True)
    disk_percent    = Column(Float, nullable=True)

    # Network (deltas since last sample)
    net_bytes_sent  = Column(Integer, nullable=True)
    net_bytes_recv  = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_sys_metrics_ts", "timestamp"),
    )


# ── ProcessMetricsRecord ──────────────────────────────────────────────────────

class ProcessMetricsRecord(Base):
    """Per-process snapshot, linked to a SystemMetricsRecord."""

    __tablename__ = "process_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    system_metrics_id = Column(
        Integer, ForeignKey("system_metrics.id", ondelete="CASCADE"), nullable=False
    )
    timestamp  = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    pid            = Column(Integer,  nullable=False)
    name           = Column(String(255), nullable=False)
    status         = Column(String(64),  nullable=True)
    username       = Column(String(128), nullable=True)
    cpu_percent    = Column(Float,    nullable=False, default=0.0)
    memory_mb      = Column(Float,    nullable=False, default=0.0)
    memory_percent = Column(Float,    nullable=True)
    num_threads    = Column(Integer,  nullable=True)

    # ML outputs (populated by Phase 3)
    anomaly_score  = Column(Float,   nullable=True)   # Isolation Forest score
    is_anomalous   = Column(Boolean, nullable=True)   # True if flagged

    system_metrics = relationship("SystemMetricsRecord", backref="processes", lazy="select")

    __table_args__ = (
        Index("ix_proc_metrics_ts", "timestamp"),
        Index("ix_proc_metrics_pid", "pid"),
        Index("ix_proc_metrics_name", "name"),
    )


# ── Incident ──────────────────────────────────────────────────────────────────

class IncidentRecord(Base):
    """An anomaly / predicted failure event."""

    __tablename__ = "incidents"

    id          = Column(String(36), primary_key=True, default=_uuid)
    pid         = Column(Integer,    nullable=False)
    process_name = Column(String(255), nullable=False)

    severity    = Column(String(16),  nullable=False)   # info / warning / critical
    status      = Column(String(16),  nullable=False, default="open")  # open/healing/resolved/dismissed

    description  = Column(Text,   nullable=False)        # plain-English explanation
    prediction   = Column(Text,   nullable=True)         # "RAM exhausted in ~6 min"
    anomaly_score = Column(Float, nullable=True)
    nl_summary    = Column(Text,   nullable=True)         # AI plain-English summary
    nl_slack_message = Column(Text, nullable=True)      # Ready-to-copy Slack notification snippet

    detected_at  = Column(DateTime(timezone=True), nullable=False, default=_now)
    resolved_at  = Column(DateTime(timezone=True), nullable=True)

    actions = relationship("HealingActionRecord", back_populates="incident", lazy="selectin")

    __table_args__ = (
        Index("ix_incidents_detected_at", "detected_at"),
        Index("ix_incidents_status", "status"),
        Index("ix_incidents_pid", "pid"),
    )


# ── HealingActionRecord ───────────────────────────────────────────────────────

class HealingActionRecord(Base):
    """Each automated (or simulated) corrective action taken."""

    __tablename__ = "healing_actions"

    id          = Column(String(36), primary_key=True, default=_uuid)
    incident_id = Column(String(36), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)

    action_type = Column(String(32), nullable=False)   # renice/throttle/suspend/restart/kill/alert_only
    pid         = Column(Integer,    nullable=False)
    process_name = Column(String(255), nullable=False)
    simulated   = Column(Boolean,    nullable=False, default=True)

    before_cpu       = Column(Float, nullable=True)
    before_memory_mb = Column(Float, nullable=True)
    after_cpu        = Column(Float, nullable=True)
    after_memory_mb  = Column(Float, nullable=True)

    reason      = Column(Text,  nullable=False)
    executed_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    # Recovery verification outcome (populated asynchronously after action)
    verification_state   = Column(String(64), nullable=True)   # see VerificationState constants
    verification_summary = Column(Text, nullable=True)
    verified_at          = Column(DateTime(timezone=True), nullable=True)

    incident = relationship("IncidentRecord", back_populates="actions")

    __table_args__ = (
        Index("ix_actions_incident", "incident_id"),
        Index("ix_actions_executed_at", "executed_at"),
    )


# ── PolicyRecord ──────────────────────────────────────────────────────────────

class PolicyRecord(Base):
    """Single-row table holding the active policy configuration."""

    __tablename__ = "policy"

    id = Column(Integer, primary_key=True, default=1)  # always 1

    simulation_mode   = Column(Boolean, nullable=False, default=True)

    cpu_warning_pct   = Column(Float, nullable=False, default=85.0)
    cpu_critical_pct  = Column(Float, nullable=False, default=95.0)
    ram_warning_pct   = Column(Float, nullable=False, default=80.0)
    ram_critical_pct  = Column(Float, nullable=False, default=92.0)
    disk_warning_pct  = Column(Float, nullable=False, default=85.0)
    disk_critical_pct = Column(Float, nullable=False, default=95.0)

    # JSON arrays of process name strings
    process_whitelist = Column(JSON, nullable=False, default=list)
    process_blacklist = Column(JSON, nullable=False, default=list)

    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


# ── FeedbackRecord ─────────────────────────────────────────────────────────────

class FeedbackRecord(Base):
    """User feedback on incidents for false-positive learning loop."""

    __tablename__ = "feedback_labels"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(36), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    label       = Column(String(32), nullable=False)  # "correct" | "false_positive" | "too_aggressive"
    user_note   = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_feedback_incident", "incident_id"),
        Index("ix_feedback_created_at", "created_at"),
    )


# ── MaintenanceWindowRecord ───────────────────────────────────────────────────

class MaintenanceWindowRecord(Base):
    """Scheduled windows during which autonomous healing is permitted/configured."""

    __tablename__ = "maintenance_windows"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    name            = Column(String(128), nullable=False)
    process_pattern = Column(String(128), nullable=False, default="*")  # e.g. "ffmpeg", "*", "python*"
    allowed_actions = Column(JSON, nullable=False, default=list)  # ["renice", "restart", "kill"]
    schedule_type   = Column(String(16), nullable=False, default="daily")  # "daily" | "weekly" | "always"
    start_hour      = Column(Integer, nullable=False, default=0)   # 0-23
    end_hour        = Column(Integer, nullable=False, default=23)  # 0-23
    days_of_week    = Column(JSON, nullable=False, default=list)  # [0,1,2,3,4,5,6] (0=Mon)
    active          = Column(Boolean, nullable=False, default=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_maint_active", "active"),
    )



# ── RootCauseDiagnosisRecord ──────────────────────────────────────────────────

class RootCauseDiagnosisRecord(Base):
    """Structured root-cause diagnosis linked to an incident."""

    __tablename__ = "rca_diagnoses"

    id          = Column(String(36), primary_key=True, default=_uuid)
    incident_id = Column(String(36), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)

    root_cause  = Column(String(64),  nullable=False)   # RootCause constant
    confidence  = Column(Float,       nullable=False, default=0.0)

    # Serialised JSON causal chain and remediation steps
    causal_chain       = Column(JSON, nullable=True)  # list of {factor, evidence, weight}
    remediation_steps  = Column(JSON, nullable=True)  # list of {priority, action, description}

    # Snapshot metrics at time of diagnosis
    cpu_at_diagnosis        = Column(Float, nullable=True)
    memory_mb_at_diagnosis  = Column(Float, nullable=True)
    system_ram_pct          = Column(Float, nullable=True)
    disk_pct                = Column(Float, nullable=True)

    summary      = Column(Text, nullable=True)
    diagnosed_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_rca_incident", "incident_id"),
        Index("ix_rca_diagnosed_at", "diagnosed_at"),
    )


# ── DiskCleanupRecord ─────────────────────────────────────────────────────────

class DiskCleanupRecord(Base):
    """Audit trail for disk scan and cleanup runs."""

    __tablename__ = "disk_cleanup_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ran_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    simulated            = Column(Boolean, nullable=False, default=True)
    disk_path            = Column(String(255), nullable=True)
    disk_used_pct_before = Column(Float, nullable=True)
    disk_used_pct_after  = Column(Float, nullable=True)

    total_files_scanned    = Column(Integer, nullable=True)
    total_reclaimable_mb   = Column(Float,   nullable=True)
    files_deleted          = Column(Integer, nullable=True, default=0)
    space_recovered_mb     = Column(Float,   nullable=True, default=0.0)

    errors    = Column(JSON, nullable=True)  # list of error strings
    triggered_by = Column(String(32), nullable=True, default="manual")  # "manual" | "auto"

    __table_args__ = (
        Index("ix_disk_cleanup_ran_at", "ran_at"),
    )


# ── RecoveryVerificationRecord ────────────────────────────────────────────────

class RecoveryVerificationRecord(Base):
    """Stores post-action recovery verification outcomes."""

    __tablename__ = "recovery_verifications"

    id        = Column(String(36), primary_key=True, default=_uuid)
    action_id = Column(String(36), ForeignKey("healing_actions.id", ondelete="CASCADE"), nullable=False)

    state            = Column(String(64), nullable=False)  # VerificationState constant
    before_cpu       = Column(Float, nullable=True)
    before_memory_mb = Column(Float, nullable=True)
    after_cpu        = Column(Float, nullable=True)
    after_memory_mb  = Column(Float, nullable=True)
    cpu_delta        = Column(Float, nullable=True)
    memory_delta_mb  = Column(Float, nullable=True)
    description      = Column(Text,  nullable=True)
    verified_at      = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_recovery_action", "action_id"),
        Index("ix_recovery_verified_at", "verified_at"),
    )


# ── Double DQN RL Models ──────────────────────────────────────────────────────

class RLAgentConfigRecord(Base):
    """Configuration hyperparameters for Double DQN RL Agent."""

    __tablename__ = "rl_agent_config"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    learning_rate      = Column(Float, nullable=False, default=1e-3)
    gamma              = Column(Float, nullable=False, default=0.99)
    batch_size         = Column(Integer, nullable=False, default=64)
    epsilon            = Column(Float, nullable=False, default=1.0)
    epsilon_min        = Column(Float, nullable=False, default=0.05)
    epsilon_decay      = Column(Float, nullable=False, default=0.995)
    target_update_freq = Column(Integer, nullable=False, default=10)
    episodes           = Column(Integer, nullable=False, default=50)
    hidden_dims        = Column(JSON, nullable=False, default=lambda: [128, 128])
    observe_only       = Column(Boolean, nullable=False, default=True)  # safety: observe vs autonomous
    updated_at         = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class RLTrainingEpisodeRecord(Base):
    """Historical telemetry for every simulated RL training episode."""

    __tablename__ = "rl_training_episodes"

    id           = Column(String(36), primary_key=True, default=_uuid)
    episode_num  = Column(Integer, nullable=False)
    scenario     = Column(String(64), nullable=False)
    total_reward = Column(Float, nullable=False)
    steps        = Column(Integer, nullable=False)
    epsilon      = Column(Float, nullable=False)
    loss         = Column(Float, nullable=False, default=0.0)
    success      = Column(Boolean, nullable=False, default=False)
    duration_sec = Column(Float, nullable=False, default=0.0)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_rl_episodes_num", "episode_num"),
        Index("ix_rl_episodes_created_at", "created_at"),
    )


class RLDecisionRecord(Base):
    """Inference telemetry and explainability log for every decision made by the RL agent."""

    __tablename__ = "rl_decisions"

    id               = Column(String(36), primary_key=True, default=_uuid)
    pid              = Column(Integer, nullable=False)
    process_name     = Column(String(255), nullable=False)
    selected_action  = Column(String(32), nullable=False)
    action_index     = Column(Integer, nullable=False)
    confidence       = Column(Float, nullable=False, default=0.0)
    is_exploration   = Column(Boolean, nullable=False, default=False)
    q_values         = Column(JSON, nullable=True)          # map of action -> Q-value
    probabilities    = Column(JSON, nullable=True)          # softmax action probabilities
    state_vector     = Column(JSON, nullable=True)          # 14-dim normalized array
    state_summary    = Column(JSON, nullable=True)          # high-level human-readable features
    was_blocked      = Column(Boolean, nullable=False, default=False)
    block_reason     = Column(String(255), nullable=True)
    reward_received  = Column(Float, nullable=True)
    created_at       = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_rl_decision_pid", "pid"),
        Index("ix_rl_decision_created_at", "created_at"),
    )


class RLModelMetadataRecord(Base):
    """Version registry of saved Double DQN weights."""

    __tablename__ = "rl_model_metadata"

    id               = Column(String(64), primary_key=True)  # model_id
    name             = Column(String(255), nullable=False)
    version          = Column(String(32), nullable=False, default="1.0.0")
    filepath         = Column(String(512), nullable=False)
    episodes_trained = Column(Integer, nullable=False, default=0)
    best_reward      = Column(Float, nullable=False, default=0.0)
    success_rate     = Column(Float, nullable=False, default=0.0)
    is_active        = Column(Boolean, nullable=False, default=False)
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        Index("ix_rl_model_active", "is_active"),
    )


# ── Application-Aware Resource Management Models ──────────────────────────────

class ApplicationProfileRecord(Base):
    """Configurable profile and importance tier for a logical application."""

    __tablename__ = "application_profiles"

    id                 = Column(String(36), primary_key=True, default=_uuid)
    app_id             = Column(String(128), nullable=False, unique=True, index=True)
    name               = Column(String(255), nullable=False)
    executable_path    = Column(String(512), nullable=True)
    category           = Column(String(64), nullable=False, default="Unknown")
    importance         = Column(String(32), nullable=False, default="Normal")  # Critical, High, Normal, Low, Background
    preferred_priority = Column(String(32), nullable=False, default="NORMAL")
    is_protected       = Column(Boolean, nullable=False, default=False)
    is_enabled         = Column(Boolean, nullable=False, default=True)
    allowed_actions    = Column(JSON, nullable=False, default=lambda: ["renice", "restore_priority"])
    max_cpu_percent    = Column(Float, nullable=True)
    max_memory_mb      = Column(Float, nullable=True)
    associated_modes   = Column(JSON, nullable=False, default=list)  # ["gaming", "study", "meeting", "battery_saver"]
    user_notes         = Column(Text, nullable=True)
    created_at         = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at         = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_app_profile_importance", "importance"),
        Index("ix_app_profile_protected", "is_protected"),
    )


class ApplicationModeRecord(Base):
    """Operating modes: Gaming, Study, Meeting, Battery Saver."""

    __tablename__ = "application_modes"

    id             = Column(String(32), primary_key=True)  # "gaming", "study", "meeting", "battery_saver"
    name           = Column(String(128), nullable=False)
    description    = Column(Text, nullable=False)
    is_active      = Column(Boolean, nullable=False, default=False)
    activated_at   = Column(DateTime(timezone=True), nullable=True)
    target_app_id  = Column(String(128), nullable=True)
    configuration  = Column(JSON, nullable=False, default=dict)
    updated_at     = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class ApplicationOptimizationRecord(Base):
    """History and active audit trail of intelligent resource optimization recommendations and actions."""

    __tablename__ = "application_optimizations"

    id               = Column(String(36), primary_key=True, default=_uuid)
    app_id           = Column(String(128), nullable=True, index=True)
    app_name         = Column(String(255), nullable=False)
    pid              = Column(Integer, nullable=False, index=True)
    action_type      = Column(String(32), nullable=False)  # renice, throttle, restore_priority, observe_only
    operating_mode   = Column(String(32), nullable=True)
    status           = Column(String(32), nullable=False, default="recommended")  # recommended, approved, rejected, executed, rolled_back
    risk_level       = Column(String(32), nullable=False, default="low")  # low, medium, high
    reason           = Column(Text, nullable=False)
    before_priority  = Column(String(32), nullable=True)
    after_priority   = Column(String(32), nullable=True)
    before_cpu       = Column(Float, nullable=True)
    before_memory_mb = Column(Float, nullable=True)
    after_cpu        = Column(Float, nullable=True)
    after_memory_mb  = Column(Float, nullable=True)
    executed_at      = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    __table_args__ = (
        Index("ix_app_opt_status", "status"),
        Index("ix_app_opt_mode", "operating_mode"),
    )


class ApplicationModeHistoryRecord(Base):
    """Audit log of operating mode activations, deactivations, and transitions."""

    __tablename__ = "application_mode_history"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    mode_id    = Column(String(32), nullable=False, index=True)
    action     = Column(String(32), nullable=False)  # activated, deactivated, switched
    timestamp  = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    details    = Column(JSON, nullable=True)


