"""
Nexus 2.0 — Tests for Phase 2: Application Detection Engine
Covers:
- Application discovery (live OS & simulated)
- Process grouping & parent-child trees
- Category classification & user overrides
- Stable application identity
- Application lifecycle events (started, exited, restarted)
- PID reuse handling
- Permission failure safety
"""

import os
import tempfile
from pathlib import Path
import pytest

from app.application_manager import (
    ApplicationCategory,
    ApplicationDetector,
    ApplicationEntity,
    ApplicationLifecycleEvent,
    ApplicationRegistry,
    ProcessClassifier,
    ProcessDetail,
    ProcessTreeResolver,
)


def _make_proc(
    pid: int,
    ppid: int | None,
    name: str,
    exe: str | None = None,
    cpu: float = 1.0,
    mem: float = 50.0,
    create_time: float = 1000.0,
    status: str = "running",
) -> ProcessDetail:
    return ProcessDetail(
        pid=pid,
        ppid=ppid,
        name=name,
        exe=exe,
        cmdline=[exe] if exe else [name],
        cpu_percent=cpu,
        memory_mb=mem,
        memory_percent=0.5,
        num_threads=4,
        status=status,
        created_at="2026-11-01T12:00:00Z",
        create_time=create_time,
        priority="NORMAL",
    )


# ── 1. Live OS Process Discovery ──────────────────────────────────────────────

def test_live_process_collection():
    detector = ApplicationDetector()
    procs = detector.collect_processes()
    assert len(procs) > 0, "Should detect real running OS processes"

    # Verify attributes of running processes
    first = procs[0]
    assert first.pid > 0
    assert isinstance(first.name, str)
    assert first.cpu_percent >= 0.0
    assert first.memory_mb >= 0.0

    # Run detection sweep
    apps = detector.detect_applications(procs)
    assert len(apps) > 0
    assert all(isinstance(a, ApplicationEntity) for a in apps)


# ── 2. Process Grouping & Parent-Child Tree ────────────────────────────────────

def test_process_tree_hierarchy_and_grouping():
    resolver = ProcessTreeResolver()

    # Synthetic Multi-Process Application (e.g. Chrome browser with renderers)
    chrome_root = _make_proc(
        pid=1000, ppid=500, name="chrome.exe",
        exe=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        cpu=2.5, mem=150.0, create_time=100.0
    )
    chrome_gpu = _make_proc(
        pid=1001, ppid=1000, name="chrome.exe",
        exe=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        cpu=1.0, mem=80.0, create_time=101.0
    )
    chrome_renderer = _make_proc(
        pid=1002, ppid=1000, name="chrome.exe",
        exe=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        cpu=3.0, mem=200.0, create_time=102.0
    )
    # Distinct application (Python backend)
    python_proc = _make_proc(
        pid=2000, ppid=500, name="python.exe",
        exe=r"C:\Python312\python.exe",
        cpu=0.5, mem=60.0, create_time=90.0
    )

    procs = [chrome_root, chrome_gpu, chrome_renderer, python_proc]

    # Test children / parent map
    children_map, parent_map = resolver.build_parent_child_map(procs)
    assert children_map[1000] == [1001, 1002]
    assert parent_map[1001] == 1000
    assert parent_map[1002] == 1000

    # Test descendants BFS
    descendants = resolver.get_descendants(1000, children_map)
    assert descendants == {1001, 1002}

    # Test grouping into clusters
    groups = resolver.group_processes(procs)
    assert len(groups) == 2, "Should produce exactly 2 logical application groups"

    # Check Chrome group contains all 3 processes
    chrome_group = next(g for g in groups if any(p.pid == 1000 for p in g))
    assert len(chrome_group) == 3
    assert {p.pid for p in chrome_group} == {1000, 1001, 1002}

    # Check Python group contains 1 process
    python_group = next(g for g in groups if any(p.pid == 2000 for p in g))
    assert len(python_group) == 1
    assert python_group[0].pid == 2000


# ── 3. Classification Heuristics ──────────────────────────────────────────────

def test_process_classification_heuristics():
    classifier = ProcessClassifier(persistence_file=os.path.join(tempfile.gettempdir(), "test_class.json"))

    # Gaming (Path and exe)
    cat_game = classifier.classify(
        app_id="app_cyberpunk",
        name="Cyberpunk2077.exe",
        executable_path=r"D:\SteamLibrary\steamapps\common\Cyberpunk 2077\bin\x64\Cyberpunk2077.exe"
    )
    assert cat_game == ApplicationCategory.GAMING

    # Development (Path and exe)
    cat_dev = classifier.classify(
        app_id="app_code",
        name="Code.exe",
        executable_path=r"C:\Users\User\AppData\Local\Programs\Microsoft VS Code\Code.exe"
    )
    assert cat_dev == ApplicationCategory.DEVELOPMENT

    # Browsing
    cat_browser = classifier.classify(
        app_id="app_chrome",
        name="chrome.exe",
        executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    )
    assert cat_browser == ApplicationCategory.BROWSING

    # Communication
    cat_comm = classifier.classify(
        app_id="app_zoom",
        name="zoom.exe",
        executable_path=r"C:\Users\User\AppData\Roaming\Zoom\bin\zoom.exe"
    )
    assert cat_comm == ApplicationCategory.COMMUNICATION

    # Education
    cat_edu = classifier.classify(
        app_id="app_notion",
        name="notion.exe",
        executable_path=r"C:\Users\User\AppData\Local\Programs\Notion\Notion.exe"
    )
    assert cat_edu == ApplicationCategory.EDUCATION

    # Media
    cat_media = classifier.classify(
        app_id="app_spotify",
        name="Spotify.exe",
        executable_path=r"C:\Users\User\AppData\Roaming\Spotify\Spotify.exe"
    )
    assert cat_media == ApplicationCategory.MEDIA

    # System
    cat_sys = classifier.classify(
        app_id="app_lsass",
        name="lsass.exe",
        executable_path=r"C:\Windows\System32\lsass.exe"
    )
    assert cat_sys == ApplicationCategory.SYSTEM

    # Background Utilities
    cat_util = classifier.classify(
        app_id="app_onedrive",
        name="OneDrive.exe",
        executable_path=r"C:\Program Files\Microsoft OneDrive\OneDrive.exe"
    )
    assert cat_util == ApplicationCategory.BACKGROUND_UTILITIES

    # Unknown
    cat_unk = classifier.classify(
        app_id="app_mycustomworker",
        name="worker_9921.exe",
        executable_path=r"C:\CustomTools\worker_9921.exe"
    )
    assert cat_unk == ApplicationCategory.UNKNOWN


# ── 4. User Classification Overrides & Persistence ────────────────────────────

def test_user_classification_override_and_persistence(tmp_path):
    pfile = str(tmp_path / "user_class.json")
    classifier = ProcessClassifier(persistence_file=pfile)

    app_id = "app_custom_tool_123"
    assert not classifier.is_user_classified(app_id)

    # Set user classification
    classifier.set_user_classification(app_id, ApplicationCategory.DEVELOPMENT)
    assert classifier.is_user_classified(app_id)

    # Classification should now return DEVELOPMENT
    cat = classifier.classify(app_id, name="tool.exe", executable_path=r"C:\Random\tool.exe")
    assert cat == ApplicationCategory.DEVELOPMENT

    # Reload a fresh classifier instance pointing to the same file
    classifier_reloaded = ProcessClassifier(persistence_file=pfile)
    assert classifier_reloaded.is_user_classified(app_id)
    assert classifier_reloaded.classify(app_id, "tool.exe") == ApplicationCategory.DEVELOPMENT

    # Remove override
    removed = classifier_reloaded.remove_user_classification(app_id)
    assert removed is True
    assert not classifier_reloaded.is_user_classified(app_id)


# ── 5. Stable Application Identity ────────────────────────────────────────────

def test_stable_application_identity():
    exe_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    # Same app executed with PID 1001 vs PID 9942 must yield identical app_id
    id1 = ApplicationRegistry.generate_app_id("chrome.exe", exe_path)
    id2 = ApplicationRegistry.generate_app_id("chrome.exe", exe_path)
    assert id1 == id2
    assert id1.startswith("app_chrome_")

    # Friendly name resolution
    assert ApplicationRegistry.get_friendly_name("code.exe") == "Visual Studio Code"
    assert ApplicationRegistry.get_friendly_name("chrome.exe") == "Google Chrome"
    assert ApplicationRegistry.get_friendly_name("spotify.exe") == "Spotify"


# ── 6. Application Lifecycle Events (Start, Exit, Restart) ────────────────────

def test_application_lifecycle_events(tmp_path):
    pfile = str(tmp_path / "user_class.json")
    classifier = ProcessClassifier(persistence_file=pfile)
    detector = ApplicationDetector(classifier=classifier)

    # --- Sweep 1: App A (VS Code) and App B (Spotify) start ---
    app_a = _make_proc(pid=100, ppid=1, name="Code.exe", exe=r"C:\VSCode\Code.exe", create_time=10.0)
    app_b = _make_proc(pid=200, ppid=1, name="Spotify.exe", exe=r"C:\Spotify\Spotify.exe", create_time=12.0)

    apps1 = detector.detect_applications([app_a, app_b])
    assert len(apps1) == 2

    events1 = detector.get_events()
    start_events = [e for e in events1 if e.event_type == ApplicationLifecycleEvent.STARTED.value]
    assert len(start_events) == 2

    # --- Sweep 2: App B (Spotify) exits, App A remains running ---
    apps2 = detector.detect_applications([app_a])
    assert len(apps2) == 1

    events2 = detector.get_events()
    exit_events = [e for e in events2 if e.event_type == ApplicationLifecycleEvent.EXITED.value]
    assert len(exit_events) == 1
    assert exit_events[0].app_name == "Spotify"

    # --- Sweep 3: App A restarts with a new PID and newer create_time ---
    app_a_restarted = _make_proc(pid=300, ppid=1, name="Code.exe", exe=r"C:\VSCode\Code.exe", create_time=50.0)
    apps3 = detector.detect_applications([app_a_restarted])
    assert len(apps3) == 1

    events3 = detector.get_events()
    restart_events = [e for e in events3 if e.event_type == ApplicationLifecycleEvent.RESTARTED.value]
    assert len(restart_events) == 1
    assert restart_events[0].app_name == "Visual Studio Code"


# ── 7. PID Reuse Handling ─────────────────────────────────────────────────────

def test_pid_reuse_handling(tmp_path):
    pfile = str(tmp_path / "user_class.json")
    detector = ApplicationDetector(classifier=ProcessClassifier(persistence_file=pfile))

    # Sweep 1: PID 5000 is Chrome
    proc1 = _make_proc(pid=5000, ppid=1, name="chrome.exe", exe=r"C:\Chrome\chrome.exe", create_time=100.0)
    detector.detect_applications([proc1])

    # Sweep 2: PID 5000 is now completely different process (PID recycled by OS)
    proc2 = _make_proc(pid=5000, ppid=1, name="game.exe", exe=r"C:\Games\game.exe", create_time=500.0)
    apps = detector.detect_applications([proc2])

    assert len(apps) == 1
    assert apps[0].name == "Game"
    assert apps[0].app_id.startswith("app_game_")


# ── 8. Permission Barriers & Graceful Handling ────────────────────────────────

def test_permission_barriers_and_safe_fallbacks(tmp_path):
    pfile = str(tmp_path / "user_class.json")
    detector = ApplicationDetector(classifier=ProcessClassifier(persistence_file=pfile))

    # Inaccessible system process where exe, cmdline, priority, etc. are None
    restricted_proc = ProcessDetail(
        pid=999,
        ppid=None,
        name="SecureService.exe",
        exe=None,
        cmdline=None,
        cpu_percent=0.0,
        memory_mb=12.0,
        memory_percent=0.1,
        num_threads=2,
        status="running",
        created_at="",
        create_time=0.0,
        priority=None,
    )

    apps = detector.detect_applications([restricted_proc])
    assert len(apps) == 1
    app = apps[0]
    assert app.app_id.startswith("app_secureservice_")
    assert app.executable_path is None
    assert app.process_count == 1
    assert app.total_memory_mb == 12.0
