"""
Nexus 2.0 — Application-Aware Resource Management
Application Registry: Generates stable, persistent application identities
independent of transient PIDs. Provides friendly name resolution,
alias management, and persistent application records.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Dict, Optional


class ApplicationRegistry:
    """
    Manages stable application identities.
    Ensures that when an application exits, restarts, or spawns child processes,
    its logical identity (app_id) remains identical across process lifetimes.
    """

    KNOWN_FRIENDLY_NAMES: Dict[str, str] = {
        "code.exe": "Visual Studio Code",
        "devenv.exe": "Visual Studio",
        "idea64.exe": "IntelliJ IDEA",
        "pycharm64.exe": "PyCharm",
        "clion64.exe": "CLion",
        "webstorm64.exe": "WebStorm",
        "chrome.exe": "Google Chrome",
        "msedge.exe": "Microsoft Edge",
        "firefox.exe": "Mozilla Firefox",
        "brave.exe": "Brave Browser",
        "opera.exe": "Opera",
        "opera_gx.exe": "Opera GX",
        "slack.exe": "Slack",
        "teams.exe": "Microsoft Teams",
        "ms-teams.exe": "Microsoft Teams",
        "zoom.exe": "Zoom Workplace",
        "discord.exe": "Discord",
        "telegram.exe": "Telegram",
        "whatsapp.exe": "WhatsApp",
        "skype.exe": "Skype",
        "spotify.exe": "Spotify",
        "vlc.exe": "VLC Media Player",
        "obs64.exe": "OBS Studio",
        "obs.exe": "OBS Studio",
        "steam.exe": "Steam",
        "epicgameslauncher.exe": "Epic Games Launcher",
        "riotclientservices.exe": "Riot Client",
        "notion.exe": "Notion",
        "obsidian.exe": "Obsidian",
        "anki.exe": "Anki",
        "windowsterminal.exe": "Windows Terminal",
        "powershell.exe": "PowerShell",
        "pwsh.exe": "PowerShell Core",
        "explorer.exe": "Windows Explorer",
        "onedrive.exe": "Microsoft OneDrive",
        "dropbox.exe": "Dropbox",
    }

    @staticmethod
    def normalize_executable_path(exe_path: Optional[str]) -> str:
        """Normalizes executable path across case and separator differences."""
        if not exe_path:
            return ""
        try:
            return os.path.normcase(os.path.abspath(exe_path))
        except Exception:
            return exe_path.lower().replace("/", "\\")

    @classmethod
    def generate_app_id(cls, process_name: str, executable_path: Optional[str] = None) -> str:
        """
        Generates a deterministic, stable identifier for an application.
        Uses the normalized executable path if available, or process name as fallback.
        Format: app_<clean_name>_<hash8>
        """
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", process_name.lower().removesuffix(".exe"))
        if not clean_name:
            clean_name = "unknown"

        if executable_path:
            norm_path = cls.normalize_executable_path(executable_path)
            path_hash = hashlib.sha256(norm_path.encode("utf-8")).hexdigest()[:8]
            return f"app_{clean_name}_{path_hash}"
        else:
            # Fallback for protected OS processes where exe path is restricted
            name_hash = hashlib.sha256(process_name.lower().encode("utf-8")).hexdigest()[:8]
            return f"app_{clean_name}_{name_hash}"

    @classmethod
    def get_friendly_name(cls, process_name: str, executable_path: Optional[str] = None) -> str:
        """Resolves a human-readable, polished display name for the application."""
        name_lower = process_name.lower()
        if name_lower in cls.KNOWN_FRIENDLY_NAMES:
            return cls.KNOWN_FRIENDLY_NAMES[name_lower]

        # Extract title from executable name (e.g. "my_custom_app.exe" -> "My Custom App")
        base = name_lower.removesuffix(".exe").replace("_", " ").replace("-", " ")
        words = [w.capitalize() for w in base.split() if w]
        if words:
            return " ".join(words)
        return process_name
