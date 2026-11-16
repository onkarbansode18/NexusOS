"""
Nexus 2.0 — Application-Aware Resource Management
Process Classifier: Categorizes applications into Gaming, Development, Browsing,
Communication, Education, Media, System, Background Utilities, or Unknown using
executable paths, system signatures, rule tables, and persistent user corrections.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from app.application_manager.application_models import ApplicationCategory
from app.decision.engine import SYSTEM_PROCESS_BLACKLIST

logger = logging.getLogger("nexus.app_classifier")


class ProcessClassifier:
    """
    Intelligently determines the category of an application using:
    1. Persistent User Classification Overrides (Highest priority)
    2. Path & Directory Heuristics (Steam, Epic, Windows/System32, Program Files)
    3. Executable Metadata & Signatures
    4. Safe System Fallbacks
    """

    def __init__(self, persistence_file: Optional[str] = None) -> None:
        if persistence_file:
            self._persistence_file = Path(persistence_file)
        else:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self._persistence_file = base_dir / "user_classifications.json"

        self._user_overrides: Dict[str, str] = {}
        self._load_user_overrides()

        # Compiled keyword patterns for directory / path matching
        self._gaming_path_patterns = [
            r"\\steamapps\\", r"\\steam\\", r"\\epic games\\", r"\\riot games\\",
            r"\\ubisoft\\", r"\\gog games\\", r"\\xboxgames\\", r"\\origin games\\",
            r"\\ea games\\", r"\\battlenet\\", r"\\battle\.net\\"
        ]
        self._gaming_exe_patterns = [
            "steam.exe", "epicgameslauncher.exe", "riotclientservices.exe",
            "valorant.exe", "cs2.exe", "dota2.exe", "leagueclient.exe",
            "gta5.exe", "cyberpunk2077.exe", "minecraft.exe", "overwatch.exe"
        ]

        self._dev_path_patterns = [
            r"\\microsoft vs code\\", r"\\jetbrains\\", r"\\pycharm", r"\\intellij",
            r"\\visual studio\\", r"\\git\\", r"\\docker\\", r"\\node_modules\\",
            r"\\python[0-9]*\\", r"\\rust\\", r"\\go\\bin\\", r"\\.cargo\\bin"
        ]
        self._dev_exe_patterns = [
            "code.exe", "devenv.exe", "idea64.exe", "pycharm64.exe", "clion64.exe",
            "webstorm64.exe", "git.exe", "docker.exe", "node.exe", "python.exe",
            "pythonw.exe", "uvicorn.exe", "windowsterminal.exe", "wt.exe",
            "powershell.exe", "pwsh.exe", "cargo.exe", "rustc.exe", "postman.exe"
        ]

        self._browser_exe_patterns = [
            "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
            "opera.exe", "opera_gx.exe", "vivaldi.exe", "safari.exe"
        ]

        self._communication_exe_patterns = [
            "slack.exe", "teams.exe", "ms-teams.exe", "zoom.exe",
            "discord.exe", "telegram.exe", "whatsapp.exe", "skype.exe",
            "signal.exe", "webex.exe", "thunderbird.exe"
        ]

        self._education_exe_patterns = [
            "anki.exe", "notion.exe", "obsidian.exe", "acrord32.exe",
            "acrobat.exe", "sumatrapdf.exe", "calibre.exe", "zotero.exe"
        ]

        self._media_exe_patterns = [
            "vlc.exe", "spotify.exe", "obs64.exe", "obs.exe", "foobar2000.exe",
            "audacity.exe", "premiere.exe", "afterfx.exe", "blender.exe",
            "mpv.exe", "itunes.exe", "handbrake.exe"
        ]

        self._background_utility_exe_patterns = [
            "onedrive.exe", "dropbox.exe", "googledrivefs.exe", "everything.exe",
            "utorrent.exe", "qbittorrent.exe", "ccleaner.exe", "update.exe",
            "telemetry.exe", "crashpad_handler.exe"
        ]

    def _load_user_overrides(self) -> None:
        """Loads persistent user classification overrides from JSON storage."""
        if self._persistence_file.exists():
            try:
                with open(self._persistence_file, "r", encoding="utf-8") as f:
                    self._user_overrides = json.load(f)
                logger.info("Loaded %d user classification overrides", len(self._user_overrides))
            except Exception as e:
                logger.warning("Failed to load user classifications from %s: %s", self._persistence_file, e)
                self._user_overrides = {}

    def _save_user_overrides(self) -> None:
        """Persists user classification overrides to JSON storage."""
        try:
            self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._persistence_file, "w", encoding="utf-8") as f:
                json.dump(self._user_overrides, f, indent=2)
            logger.info("Saved %d user classification overrides", len(self._user_overrides))
        except Exception as e:
            logger.error("Failed to save user classifications to %s: %s", self._persistence_file, e)

    def set_user_classification(self, app_id: str, category: ApplicationCategory) -> None:
        """Allows users to manually correct an application category."""
        val = category.value if isinstance(category, ApplicationCategory) else str(category)
        self._user_overrides[app_id] = val
        self._save_user_overrides()

    def remove_user_classification(self, app_id: str) -> bool:
        """Removes a user classification override."""
        if app_id in self._user_overrides:
            del self._user_overrides[app_id]
            self._save_user_overrides()
            return True
        return False

    def is_user_classified(self, app_id: str) -> bool:
        """Checks if the application category was manually set by the user."""
        return app_id in self._user_overrides

    def classify(
        self,
        app_id: str,
        name: str,
        executable_path: Optional[str] = None,
        is_system_flag: bool = False,
    ) -> ApplicationCategory:
        """
        Classifies an application into an ApplicationCategory.
        Evaluates user override -> system protection -> path heuristics -> exe rules.
        """
        # 1. User manual correction (absolute priority)
        if app_id in self._user_overrides:
            try:
                return ApplicationCategory(self._user_overrides[app_id])
            except ValueError:
                pass

        name_lower = (name or "").lower().strip()
        clean_name = name_lower.removesuffix(".exe")
        exe_path_lower = (executable_path or "").lower()

        # 2. Operating System / Core Services
        if is_system_flag or name_lower in SYSTEM_PROCESS_BLACKLIST or clean_name in SYSTEM_PROCESS_BLACKLIST:
            return ApplicationCategory.SYSTEM

        if "\\windows\\system32\\" in exe_path_lower or "\\windows\\syswow64\\" in exe_path_lower:
            # If inside Windows System32 and not an explicit dev tool like powershell
            if clean_name not in ["powershell", "cmd", "wt"]:
                return ApplicationCategory.SYSTEM

        # 3. Path heuristic checks
        for pat in self._gaming_path_patterns:
            if re.search(pat, exe_path_lower):
                return ApplicationCategory.GAMING

        for pat in self._dev_path_patterns:
            if re.search(pat, exe_path_lower):
                return ApplicationCategory.DEVELOPMENT

        # 4. Executable signature checks
        if any(name_lower == p or clean_name == p.removesuffix(".exe") for p in self._browser_exe_patterns):
            return ApplicationCategory.BROWSING

        if any(name_lower == p or clean_name == p.removesuffix(".exe") for p in self._communication_exe_patterns):
            return ApplicationCategory.COMMUNICATION

        if any(name_lower == p or clean_name == p.removesuffix(".exe") for p in self._dev_exe_patterns):
            return ApplicationCategory.DEVELOPMENT

        if any(name_lower == p or clean_name == p.removesuffix(".exe") for p in self._gaming_exe_patterns):
            return ApplicationCategory.GAMING

        if any(name_lower == p or clean_name == p.removesuffix(".exe") for p in self._media_exe_patterns):
            return ApplicationCategory.MEDIA

        if any(name_lower == p or clean_name == p.removesuffix(".exe") for p in self._education_exe_patterns):
            return ApplicationCategory.EDUCATION

        if any(name_lower == p or clean_name == p.removesuffix(".exe") for p in self._background_utility_exe_patterns):
            return ApplicationCategory.BACKGROUND_UTILITIES

        return ApplicationCategory.UNKNOWN
