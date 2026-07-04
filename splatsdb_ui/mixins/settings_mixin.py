# SPDX-License-Identifier: GPL-3.0
"""Settings mixin — config persistence, preferences dialog."""

import json
from pathlib import Path

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTabWidget, QPushButton


class SettingsMixin:
    """Settings management mixin for MainWindow."""

    def init_settings(self):
        """Load settings from disk."""
        config_dir = self.state.config_dir
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.json"

        if config_file.exists():
            try:
                with open(config_file) as f:
                    cfg = json.load(f)
                self._apply_config(cfg)
            except Exception:
                pass

    def _apply_config(self, cfg: dict):
        """Apply loaded config to state."""
        if "backend" in cfg:
            for k, v in cfg["backend"].items():
                if hasattr(self.state.connection, k):
                    setattr(self.state.connection, k, v)
        if "embedding" in cfg:
            for k, v in cfg["embedding"].items():
                if hasattr(self.state.embedding, k):
                    setattr(self.state.embedding, k, v)
        if "ocr" in cfg:
            for k, v in cfg["ocr"].items():
                if hasattr(self.state.ocr, k):
                    setattr(self.state.ocr, k, v)

    def save_config(self):
        """Persist current state to disk."""
        config_file = self.state.config_dir / "config.json"
        try:
            cfg = {
                "backend": {
                    "url": self.state.connection.url,
                    "api_key": self.state.connection.api_key,
                },
                "embedding": {
                    "active_model": self.state.embedding.active_model,
                    "device": self.state.embedding.device,
                },
                "ocr": {
                    "engine": self.state.ocr.engine,
                    "language": self.state.ocr.language,
                },
                "ui": {
                    "theme": self.state.ui.theme,
                    "sounds_enabled": self.state.ui.sounds_enabled,
                    "font_size": self.state.ui.font_size,
                },
            }
            with open(config_file, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            # Don't crash the app on close if config save fails
            import sys
            print(f"[splatsdb-ui] Warning: failed to save config: {e}", file=sys.stderr)

    def open_settings(self):
        """Open the settings dialog."""
        self.switch_view("welcome")  # Placeholder — settings dialog not built yet
        self.signals.status_message.emit("Settings opened")
