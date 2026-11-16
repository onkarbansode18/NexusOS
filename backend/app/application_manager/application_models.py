"""
Nexus 2.0 — Application-Aware Resource Management
Application Models: Data contracts, enums, and structures for application entities,
process details, lifecycle events, and classification.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ApplicationCategory(str, enum.Enum):
    GAMING = "Gaming"
    DEVELOPMENT = "Development"
    BROWSING = "Browsing"
    COMMUNICATION = "Communication"
    EDUCATION = "Education"
    MEDIA = "Media"
    SYSTEM = "System"
    BACKGROUND_UTILITIES = "Background Utilities"
    UNKNOWN = "Unknown"


class ApplicationImportance(str, enum.Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    NORMAL = "Normal"
    LOW = "Low"
    BACKGROUND = "Background"


class ApplicationLifecycleEvent(str, enum.Enum):
    STARTED = "started"
    EXITED = "exited"
    RESTARTED = "restarted"


@dataclass
class ProcessDetail:
    """Detailed metadata for an individual OS process."""
    pid: int
    ppid: Optional[int]
    name: str
    exe: Optional[str] = None
    cmdline: Optional[List[str]] = None
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    num_threads: int = 0
    status: str = "running"
    created_at: str = ""
    create_time: float = 0.0
    priority: Optional[str] = None
    read_bytes: Optional[int] = None
    write_bytes: Optional[int] = None
    network_bytes: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "ppid": self.ppid,
            "name": self.name,
            "exe": self.exe,
            "cmdline": self.cmdline,
            "cpu_percent": round(self.cpu_percent, 2),
            "memory_mb": round(self.memory_mb, 2),
            "memory_percent": round(self.memory_percent, 3),
            "num_threads": self.num_threads,
            "status": self.status,
            "created_at": self.created_at,
            "create_time": self.create_time,
            "priority": self.priority,
            "read_bytes": self.read_bytes,
            "write_bytes": self.write_bytes,
            "network_bytes": self.network_bytes,
        }


@dataclass
class ApplicationEntity:
    """
    Logical grouping of one or more related processes forming a single application.
    Identified by a stable app_id independent of transient PIDs.
    """
    app_id: str
    name: str
    category: ApplicationCategory
    executable_path: Optional[str]
    root_pid: int
    pids: List[int] = field(default_factory=list)
    process_count: int = 1
    processes: List[ProcessDetail] = field(default_factory=list)
    total_cpu_percent: float = 0.0
    total_memory_mb: float = 0.0
    total_memory_percent: float = 0.0
    total_threads: int = 0
    is_system: bool = False
    is_protected: bool = False
    started_at: str = ""
    status: str = "active"
    user_classified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "category": self.category.value if isinstance(self.category, ApplicationCategory) else str(self.category),
            "executable_path": self.executable_path,
            "root_pid": self.root_pid,
            "pids": self.pids,
            "process_count": self.process_count,
            "processes": [p.to_dict() for p in self.processes],
            "total_cpu_percent": round(self.total_cpu_percent, 2),
            "total_memory_mb": round(self.total_memory_mb, 2),
            "total_memory_percent": round(self.total_memory_percent, 3),
            "total_threads": self.total_threads,
            "is_system": self.is_system,
            "is_protected": self.is_protected,
            "started_at": self.started_at,
            "status": self.status,
            "user_classified": self.user_classified,
        }


@dataclass
class ApplicationEvent:
    """Historical telemetry record for application lifecycle changes."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    app_id: str = ""
    app_name: str = ""
    event_type: str = "started"  # started / exited / restarted
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "app_id": self.app_id,
            "app_name": self.app_name,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "details": self.details,
        }
