"""
Nexus Double DQN — Model Registry & Lifecycle Manager
======================================================
Manages trained checkpoints, version tagging, metadata indexing, active model selection,
and rollback capabilities for production RL deployment.
"""

from __future__ import annotations

import os
import json
import time
import shutil
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nexus.rl.model_manager")


@dataclass
class ModelMetadata:
    model_id: str
    name: str
    version: str
    filepath: str
    created_at: str
    episodes_trained: int
    best_reward: float
    success_rate: float
    is_active: bool = False
    state_dim: int = 14
    action_dim: int = 7
    notes: str = ""


class ModelManager:
    """
    Registry and storage manager for Double DQN neural weights and lifecycle metadata.
    """

    def __init__(self, checkpoints_dir: str = "app/rl/checkpoints") -> None:
        self.checkpoints_dir = os.path.abspath(checkpoints_dir)
        os.makedirs(self.checkpoints_dir, exist_ok=True)
        self.registry_file = os.path.join(self.checkpoints_dir, "models_registry.json")
        self._ensure_registry()

    def _ensure_registry(self) -> None:
        """Create empty registry JSON if absent."""
        if not os.path.exists(self.registry_file):
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump({"active_model_id": None, "models": []}, f, indent=2)

    def _read_registry(self) -> Dict[str, Any]:
        """Read registry JSON."""
        try:
            with open(self.registry_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Error reading model registry: %s", e)
            return {"active_model_id": None, "models": []}

    def _write_registry(self, data: Dict[str, Any]) -> None:
        """Write registry JSON."""
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def list_models(self) -> List[Dict[str, Any]]:
        """List all registered models with their operational status."""
        data = self._read_registry()
        active_id = data.get("active_model_id")
        models = data.get("models", [])
        for m in models:
            m["is_active"] = (m.get("model_id") == active_id)
            # Check if file exists on disk
            m["file_exists"] = os.path.exists(m.get("filepath", ""))
        return models

    def get_active_model(self) -> Optional[Dict[str, Any]]:
        """Return metadata for currently active model."""
        models = self.list_models()
        for m in models:
            if m.get("is_active"):
                return m
        # If no explicit active model, fallback to first valid model
        for m in models:
            if m.get("file_exists"):
                return m
        return None

    def register_model(
        self,
        filepath: str,
        name: str,
        version: str = "1.0.0",
        episodes_trained: int = 0,
        best_reward: float = 0.0,
        success_rate: float = 0.0,
        notes: str = "",
        set_active: bool = False,
    ) -> Dict[str, Any]:
        """Register a checkpoint file in the catalog."""
        model_id = f"nexus-ddqn-v{version}-{int(time.time())}"
        abs_path = os.path.abspath(filepath)

        record = {
            "model_id": model_id,
            "name": name,
            "version": version,
            "filepath": abs_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "episodes_trained": episodes_trained,
            "best_reward": round(best_reward, 2),
            "success_rate": round(success_rate, 2),
            "is_active": set_active,
            "state_dim": 14,
            "action_dim": 7,
            "notes": notes,
        }

        data = self._read_registry()
        # Remove any existing with same model_id
        data["models"] = [m for m in data.get("models", []) if m.get("model_id") != model_id]
        data["models"].append(record)

        if set_active or data.get("active_model_id") is None:
            data["active_model_id"] = model_id

        self._write_registry(data)
        logger.info("Registered model %s (%s)", model_id, name)
        return record

    def set_active_model(self, model_id: str) -> bool:
        """Promote a registered model to active production status."""
        data = self._read_registry()
        matching = [m for m in data.get("models", []) if m.get("model_id") == model_id]
        if not matching:
            logger.warning("Cannot set active: model_id %s not found", model_id)
            return False

        if not os.path.exists(matching[0].get("filepath", "")):
            logger.error("Checkpoint file for %s does not exist on disk", model_id)
            return False

        data["active_model_id"] = model_id
        self._write_registry(data)
        logger.info("Active RL model set to %s", model_id)
        return True

    def delete_model(self, model_id: str) -> bool:
        """Remove a model from registry and optionally delete disk checkpoint."""
        data = self._read_registry()
        models = data.get("models", [])
        target = next((m for m in models if m.get("model_id") == model_id), None)
        if not target:
            return False

        # If file is in checkpoints dir, delete file safely
        fp = target.get("filepath", "")
        if fp and os.path.exists(fp) and fp.startswith(self.checkpoints_dir):
            try:
                os.remove(fp)
            except Exception as e:
                logger.warning("Could not remove model file %s: %s", fp, e)

        data["models"] = [m for m in models if m.get("model_id") != model_id]
        if data.get("active_model_id") == model_id:
            # Set to next available model or None
            data["active_model_id"] = data["models"][0]["model_id"] if data["models"] else None

        self._write_registry(data)
        return True
