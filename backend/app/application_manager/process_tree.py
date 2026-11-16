"""
Nexus 2.0 — Application-Aware Resource Management
Process Tree: Analyzes process parent-child relationships, builds hierarchical
process graphs, and groups multi-process applications logically.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Dict, List, Optional, Set

from app.application_manager.application_models import ProcessDetail


class ProcessTreeResolver:
    """
    Constructs process relationship hierarchies and clusters child processes
    belonging to the same logical application.
    """

    @staticmethod
    def normalize_path(path: Optional[str]) -> str:
        if not path:
            return ""
        return path.lower().replace("/", "\\").strip()

    @staticmethod
    def get_app_dir(path: Optional[str]) -> str:
        norm = ProcessTreeResolver.normalize_path(path)
        if not norm or "\\" not in norm:
            return ""
        return norm.rsplit("\\", 1)[0]

    def build_parent_child_map(
        self, processes: List[ProcessDetail]
    ) -> tuple[Dict[int, List[int]], Dict[int, int]]:
        """
        Builds children map: {parent_pid: [child_pid, ...]}
        and parent map: {child_pid: parent_pid}
        """
        children_map: Dict[int, List[int]] = defaultdict(list)
        parent_map: Dict[int, int] = {}
        pid_set = {p.pid for p in processes}

        for proc in processes:
            if proc.ppid is not None and proc.ppid in pid_set and proc.ppid != proc.pid:
                children_map[proc.ppid].append(proc.pid)
                parent_map[proc.pid] = proc.ppid

        return dict(children_map), parent_map

    def get_descendants(self, root_pid: int, children_map: Dict[int, List[int]]) -> Set[int]:
        """Returns all descendant PIDs of a given root PID (BFS) with cycle safety."""
        descendants: Set[int] = set()
        queue = list(children_map.get(root_pid, []))
        visited: Set[int] = {root_pid}

        while queue:
            child = queue.pop(0)
            if child not in visited:
                visited.add(child)
                descendants.add(child)
                queue.extend(children_map.get(child, []))
        return descendants

    def group_processes(
        self, processes: List[ProcessDetail]
    ) -> List[List[ProcessDetail]]:
        """
        Groups processes into logical application clusters.
        Cycle-safe and optimized.
        """
        if not processes:
            return []

        proc_map: Dict[int, ProcessDetail] = {p.pid: p for p in processes}
        children_map, parent_map = self.build_parent_child_map(processes)

        # Precompute normalized path and dir for each process for O(1) lookups
        norm_exe_map: Dict[int, str] = {p.pid: self.normalize_path(p.exe) for p in processes}
        norm_dir_map: Dict[int, str] = {p.pid: self.get_app_dir(p.exe) for p in processes}

        assigned: Set[int] = set()
        groups: List[List[ProcessDetail]] = []

        # Sort processes by create_time ascending (oldest root processes first)
        sorted_procs = sorted(processes, key=lambda p: (p.create_time, p.pid))

        for candidate_root in sorted_procs:
            if candidate_root.pid in assigned:
                continue

            # Check if this candidate is actually a child belonging to an ancestor that shares directory/exe
            curr_parent_pid = parent_map.get(candidate_root.pid)
            has_assigned_ancestor = False
            visited_ancestors: Set[int] = {candidate_root.pid}

            while curr_parent_pid is not None and curr_parent_pid not in visited_ancestors:
                visited_ancestors.add(curr_parent_pid)
                parent_proc = proc_map.get(curr_parent_pid)
                if parent_proc:
                    root_dir = norm_dir_map.get(parent_proc.pid, "")
                    cand_dir = norm_dir_map.get(candidate_root.pid, "")
                    root_exe = norm_exe_map.get(parent_proc.pid, "")
                    cand_exe = norm_exe_map.get(candidate_root.pid, "")

                    if (root_exe and cand_exe and root_exe == cand_exe) or \
                       (root_dir and cand_dir and root_dir == cand_dir):
                        has_assigned_ancestor = True
                        break
                curr_parent_pid = parent_map.get(curr_parent_pid)

            if has_assigned_ancestor:
                continue

            # Candidate is a cluster root
            cluster: List[ProcessDetail] = [candidate_root]
            assigned.add(candidate_root.pid)

            root_dir = norm_dir_map.get(candidate_root.pid, "")
            root_exe_norm = norm_exe_map.get(candidate_root.pid, "")

            # Discover all related descendants
            all_descendants = self.get_descendants(candidate_root.pid, children_map)
            direct_children = set(children_map.get(candidate_root.pid, []))

            for desc_pid in all_descendants:
                if desc_pid in assigned:
                    continue
                desc_proc = proc_map.get(desc_pid)
                if not desc_proc:
                    continue

                desc_exe_norm = norm_exe_map.get(desc_pid, "")
                desc_dir = norm_dir_map.get(desc_pid, "")

                # Same executable, or same application folder, or direct child
                is_same_exe = bool(root_exe_norm and desc_exe_norm and root_exe_norm == desc_exe_norm)
                is_same_dir = bool(root_dir and desc_dir and root_dir == desc_dir)
                is_direct_child = desc_pid in direct_children

                if is_same_exe or is_same_dir or is_direct_child:
                    cluster.append(desc_proc)
                    assigned.add(desc_pid)

            # Check for any remaining processes that share the exact executable path
            if root_exe_norm:
                for proc in sorted_procs:
                    if proc.pid not in assigned and norm_exe_map.get(proc.pid) == root_exe_norm:
                        cluster.append(proc)
                        assigned.add(proc.pid)

            groups.append(cluster)

        # Catch any stray processes not yet assigned
        for proc in processes:
            if proc.pid not in assigned:
                groups.append([proc])
                assigned.add(proc.pid)

        return groups
