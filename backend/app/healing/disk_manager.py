"""
Nexus — Disk Space & Temporary File Manager
============================================
Feature 4: Disk Space and Temporary File Management.

Responsibilities:
  1. Scan system temp directories and report their sizes.
  2. Estimate reclaimable space by category.
  3. In SIMULATION MODE: log what WOULD be deleted, return plan.
  4. In LIVE MODE: delete temp files older than a configurable age.
  5. Safety constraints:
       - Never delete directories outside the allowed temp paths.
       - Never delete files accessed in the last min_age_hours hours.
       - Never delete files matching any protected_patterns.
       - Hard-coded list of directories that can NEVER be touched.

Cross-platform:
  - Windows: %TEMP%, %TMP%, C:/Windows/Temp, C:/Windows/SoftwareDistribution/Download
  - Linux/macOS: /tmp, /var/tmp, /var/log (logs subdir), ~/Library/Caches (macOS)
"""

from __future__ import annotations

import fnmatch
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("nexus.disk")

_IS_WINDOWS = sys.platform == "win32"

# ── Safety: paths that can NEVER be modified ─────────────────────────────────
_FORBIDDEN_ROOT_PATHS: frozenset[str] = frozenset({
    "/", "/usr", "/bin", "/sbin", "/lib", "/lib64",
    "/etc", "/proc", "/sys", "/dev", "/boot",
    "C:\\Windows\\System32", "C:\\Windows\\SysWOW64",
    "C:\\Program Files", "C:\\Program Files (x86)",
    "C:\\Users",
})

# Patterns that are NEVER deleted regardless of age
_PROTECTED_PATTERNS: frozenset[str] = frozenset({
    "*.sys", "*.dll", "*.exe", "*.bat", "*.cmd",
    "*.py", "*.pyc", "*.pyw",
    "pagefile.sys", "hiberfil.sys", "swapfile.sys",
    ".gitkeep", ".keep",
})


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class DirScanResult:
    path: str
    total_files: int
    total_size_mb: float
    reclaimable_files: int
    reclaimable_size_mb: float
    oldest_file_age_hours: float
    newest_file_age_hours: float
    error: Optional[str] = None


@dataclass
class CleanupPlan:
    """What WOULD be (or was) deleted."""
    entries: List["CleanupEntry"] = field(default_factory=list)
    total_files: int = 0
    total_reclaimable_mb: float = 0.0
    simulated: bool = True
    executed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: List[str] = field(default_factory=list)


@dataclass
class CleanupEntry:
    path: str
    size_mb: float
    age_hours: float
    deleted: bool       # True = actually deleted (live mode)
    simulated: bool     # True = simulation (would have deleted)
    error: Optional[str] = None


@dataclass
class DiskReport:
    """Full disk health + cleanup opportunity report."""
    timestamp: str
    disk_path: str
    total_gb: float
    used_gb: float
    free_gb: float
    used_percent: float
    temp_dirs_scanned: List[DirScanResult]
    total_reclaimable_mb: float
    warning: bool     # True if disk > warning threshold
    critical: bool    # True if disk > critical threshold


# ── DiskManager ──────────────────────────────────────────────────────────────

class DiskManager:
    """
    Scans and optionally cleans temp/cache directories.

    Parameters
    ----------
    simulation_mode : bool
        If True, no files are deleted — only reports what would happen.
    min_age_hours : float
        Only files older than this are eligible for deletion.
    max_size_mb_per_dir : float
        Cap on how much to delete per directory per run (safety valve).
    extra_temp_dirs : list[str]
        User-specified additional directories to scan.
    protected_patterns : list[str]
        Additional glob patterns to exclude from cleanup.
    disk_warning_pct : float
        Disk % at which warning flag is set in reports.
    disk_critical_pct : float
        Disk % at which critical flag is set in reports.
    """

    def __init__(
        self,
        simulation_mode: bool = True,
        min_age_hours: float = 24.0,
        max_size_mb_per_dir: float = 1024.0,
        extra_temp_dirs: Optional[List[str]] = None,
        protected_patterns: Optional[List[str]] = None,
        disk_warning_pct: float = 85.0,
        disk_critical_pct: float = 95.0,
    ) -> None:
        self.simulation_mode = simulation_mode
        self.min_age_hours = min_age_hours
        self.max_size_mb_per_dir = max_size_mb_per_dir
        self.disk_warning_pct = disk_warning_pct
        self.disk_critical_pct = disk_critical_pct

        # Build temp-dir list for this OS
        self._temp_dirs: List[Path] = self._default_temp_dirs()
        for d in (extra_temp_dirs or []):
            p = Path(d)
            if p.exists() and p.is_dir() and self._is_safe_path(p):
                self._temp_dirs.append(p)

        # Protected glob patterns
        self._protected: frozenset[str] = _PROTECTED_PATTERNS | frozenset(
            protected_patterns or []
        )

    # ── Public API ──────────────────────────────────────────────────────────────

    def scan(self) -> List[DirScanResult]:
        """Scan all configured temp directories and return size info."""
        results: List[DirScanResult] = []
        for d in self._temp_dirs:
            results.append(self._scan_dir(d))
        return results

    def build_cleanup_plan(self) -> CleanupPlan:
        """Build (but don't execute) a cleanup plan — always safe to call."""
        return self._run_cleanup(execute=False)

    def execute_cleanup(self) -> CleanupPlan:
        """
        Execute cleanup (LIVE MODE) or simulate it (SIMULATION MODE).
        In simulation mode, behaves identically to build_cleanup_plan().
        """
        return self._run_cleanup(execute=not self.simulation_mode)

    def disk_report(self, disk_path: Optional[str] = None) -> DiskReport:
        """Return a combined disk health + cleanup opportunity report."""
        import psutil

        path = disk_path or self._default_disk_root()
        try:
            usage = psutil.disk_usage(path)
        except Exception:
            # Fallback
            try:
                drive = os.path.splitdrive(os.getcwd())[0] + "\\"
                usage = psutil.disk_usage(drive)
                path = drive
            except Exception as exc:
                logger.error("Failed to get disk usage: %s", exc)
                return DiskReport(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    disk_path=path, total_gb=0, used_gb=0, free_gb=0,
                    used_percent=0, temp_dirs_scanned=[], total_reclaimable_mb=0,
                    warning=False, critical=False,
                )

        to_gb = 1 / (1024 ** 3)
        total_gb  = round(usage.total * to_gb, 2)
        used_gb   = round(usage.used  * to_gb, 2)
        free_gb   = round(usage.free  * to_gb, 2)
        used_pct  = usage.percent

        scans = self.scan()
        total_reclaimable = sum(s.reclaimable_size_mb for s in scans)

        return DiskReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            disk_path=path,
            total_gb=total_gb,
            used_gb=used_gb,
            free_gb=free_gb,
            used_percent=used_pct,
            temp_dirs_scanned=scans,
            total_reclaimable_mb=round(total_reclaimable, 2),
            warning=used_pct >= self.disk_warning_pct,
            critical=used_pct >= self.disk_critical_pct,
        )

    # ── Private ─────────────────────────────────────────────────────────────────

    def _run_cleanup(self, execute: bool) -> CleanupPlan:
        plan = CleanupPlan(simulated=not execute)
        min_age_secs = self.min_age_hours * 3600.0
        now = time.time()

        for dir_path in self._temp_dirs:
            if not dir_path.exists() or not dir_path.is_dir():
                continue
            if not self._is_safe_path(dir_path):
                logger.warning("Skipping potentially unsafe path: %s", dir_path)
                continue

            dir_budget_mb = 0.0
            try:
                for fpath in dir_path.rglob("*"):
                    if not fpath.is_file():
                        continue
                    if not self._is_safe_path(fpath):
                        continue
                    if self._is_protected(fpath):
                        continue

                    try:
                        stat = fpath.stat()
                        age_secs = now - max(stat.st_mtime, stat.st_atime)
                        if age_secs < min_age_secs:
                            continue

                        size_mb = stat.st_size / (1024 ** 2)
                        if dir_budget_mb + size_mb > self.max_size_mb_per_dir:
                            break

                        deleted = False
                        error = None

                        if execute:
                            try:
                                fpath.unlink(missing_ok=True)
                                deleted = True
                                logger.info("Deleted temp file: %s (%.2f MB)", fpath, size_mb)
                            except Exception as exc:
                                error = str(exc)
                                logger.warning("Failed to delete %s: %s", fpath, exc)
                        else:
                            logger.debug(
                                "[SIM] Would delete: %s (%.2f MB, age=%.1fh)",
                                fpath, size_mb, age_secs / 3600
                            )

                        entry = CleanupEntry(
                            path=str(fpath),
                            size_mb=round(size_mb, 3),
                            age_hours=round(age_secs / 3600, 1),
                            deleted=deleted,
                            simulated=not execute,
                            error=error,
                        )
                        plan.entries.append(entry)
                        plan.total_files += 1
                        plan.total_reclaimable_mb += size_mb
                        if deleted:
                            dir_budget_mb += size_mb

                    except (PermissionError, OSError):
                        continue  # skip inaccessible files silently

            except Exception as exc:
                msg = f"Error scanning {dir_path}: {exc}"
                logger.warning(msg)
                plan.errors.append(msg)

        plan.total_reclaimable_mb = round(plan.total_reclaimable_mb, 2)
        return plan

    def _scan_dir(self, dir_path: Path) -> DirScanResult:
        """Scan a single directory and return its stats."""
        if not dir_path.exists() or not dir_path.is_dir():
            return DirScanResult(
                path=str(dir_path), total_files=0, total_size_mb=0.0,
                reclaimable_files=0, reclaimable_size_mb=0.0,
                oldest_file_age_hours=0.0, newest_file_age_hours=0.0,
                error="Directory does not exist",
            )

        total_files = reclaimable_files = 0
        total_size = reclaimable_size = 0.0
        ages: List[float] = []
        now = time.time()
        min_age_secs = self.min_age_hours * 3600.0

        try:
            for fpath in dir_path.rglob("*"):
                if not fpath.is_file():
                    continue
                try:
                    stat = fpath.stat()
                    size_mb = stat.st_size / (1024 ** 2)
                    age_secs = now - max(stat.st_mtime, stat.st_atime)
                    ages.append(age_secs)
                    total_files += 1
                    total_size += size_mb
                    if (age_secs >= min_age_secs
                            and not self._is_protected(fpath)
                            and self._is_safe_path(fpath)):
                        reclaimable_files += 1
                        reclaimable_size += size_mb
                except (PermissionError, OSError):
                    continue
        except Exception as exc:
            return DirScanResult(
                path=str(dir_path), total_files=total_files,
                total_size_mb=round(total_size, 2),
                reclaimable_files=reclaimable_files,
                reclaimable_size_mb=round(reclaimable_size, 2),
                oldest_file_age_hours=0.0, newest_file_age_hours=0.0,
                error=str(exc),
            )

        oldest = max(ages) / 3600 if ages else 0.0
        newest = min(ages) / 3600 if ages else 0.0

        return DirScanResult(
            path=str(dir_path),
            total_files=total_files,
            total_size_mb=round(total_size, 2),
            reclaimable_files=reclaimable_files,
            reclaimable_size_mb=round(reclaimable_size, 2),
            oldest_file_age_hours=round(oldest, 1),
            newest_file_age_hours=round(newest, 1),
        )

    def _is_safe_path(self, path: Path) -> bool:
        """Return True only if the path is under a safe temp directory."""
        abs_str = str(path.resolve()).lower()
        for forbidden in _FORBIDDEN_ROOT_PATHS:
            if abs_str.startswith(forbidden.lower()):
                return False
        # Must be under one of our known temp roots
        safe_roots = [str(d.resolve()).lower() for d in self._temp_dirs]
        return any(abs_str.startswith(r) for r in safe_roots)

    def _is_protected(self, path: Path) -> bool:
        """Return True if the filename matches any protected pattern."""
        name = path.name
        for pattern in self._protected:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    @staticmethod
    def _default_temp_dirs() -> List[Path]:
        """Return the platform-appropriate temp directory list."""
        dirs: List[Path] = []
        if _IS_WINDOWS:
            for env_var in ("TEMP", "TMP"):
                val = os.environ.get(env_var)
                if val:
                    dirs.append(Path(val))
            dirs.append(Path("C:/Windows/Temp"))
        else:
            dirs.extend([Path("/tmp"), Path("/var/tmp")])
            # macOS caches
            home = Path.home()
            mac_cache = home / "Library" / "Caches"
            if mac_cache.exists():
                dirs.append(mac_cache)
        return [d for d in dirs if d.exists()]

    @staticmethod
    def _default_disk_root() -> str:
        if _IS_WINDOWS:
            drive = os.path.splitdrive(os.getcwd())[0]
            return drive + "\\" if drive else "C:\\"
        return "/"
