# SPDX-License-Identifier: GPL-3.0
"""SplatsDB UI — Main Application Window.

Layout: Engine switcher (top) | Search bar | View tabs (center) | IO Tray + Jobs (bottom) | Status
3D tab has splitter: 3D View | Node Inspector | File Preview
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QSplitter, QTabWidget, QMenu, QLabel,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QColor, QFont, QPainter, QPixmap

from splatsdb_ui.utils.signals import SignalBus
from splatsdb_ui.utils.state import AppState
from splatsdb_ui.utils.theme import load_theme, Colors
from splatsdb_ui.utils.icons import tab_label, TAB_ICONS, icon as svg_icon

from splatsdb_ui.engine_manager import EngineManager, EngineConfig, EngineStatus, PRESETS

from splatsdb_ui.widgets.engine_switcher import EngineSwitcher
from splatsdb_ui.widgets.config_editor import ConfigEditor
from splatsdb_ui.widgets.search_bar import GlobalSearchBar
from splatsdb_ui.widgets.param_panel import ParamPanel
from splatsdb_ui.widgets.io_tray import IOTray
from splatsdb_ui.widgets.job_queue import JobQueuePanel
from splatsdb_ui.widgets.status_bar import SplatsDBStatusBar
from splatsdb_ui.widgets.node_inspector import NodeInspector
from splatsdb_ui.widgets.file_preview import FilePreview
from splatsdb_ui.widgets.toast import ToastOverlay

from splatsdb_ui.views.welcome_view import WelcomeView
from splatsdb_ui.views.search_view import SearchView
from splatsdb_ui.views.collections_view import CollectionsView
from splatsdb_ui.views.graph_view import GraphView
from splatsdb_ui.views.spatial_view import SpatialView
from splatsdb_ui.views.cluster_view import ClusterView
from splatsdb_ui.views.benchmark_view import BenchmarkView
from splatsdb_ui.views.ocr_view import OCRView
from splatsdb_ui.views.splat3d_view import Splat3DView
from splatsdb_ui.views.ebm_view import EBMView

from splatsdb_ui.mixins.file_mixin import FileMixin
from splatsdb_ui.mixins.search_mixin import SearchMixin
from splatsdb_ui.mixins.settings_mixin import SettingsMixin
from splatsdb_ui.mixins.audio_mixin import AudioMixin


class MainWindow(
    FileMixin,
    SearchMixin,
    SettingsMixin,
    AudioMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SplatsDB")
        self.setMinimumSize(1200, 800)
        self.resize(1440, 900)

        # ── Splash / loading overlay ──
        self._show_splash()

        config_dir = Path.home() / ".splatsdb-ui"
        self.signals = SignalBus()
        self.state = AppState(config_dir=config_dir)
        self.engine_manager = EngineManager(config_dir)

        self._build_ui()
        self._build_menus()
        self._build_shortcuts()
        self._connect_signals()

        self.init_settings()
        self.init_audio()
        self._auto_start()
        self._load_demo_data()

        # ── Dismiss splash after everything is loaded ──
        QTimer.singleShot(800, self._hide_splash)

        # ── Health / stats polling timer (every 30 s) ──
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_backend)
        self._poll_timer.start(30_000)
        # Initial poll after a short delay to let engines start
        QTimer.singleShot(3_000, self._poll_backend)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toast notification overlay (lives on top of everything)
        self.toast_overlay = ToastOverlay(central)
        self.toast_overlay.raise_()

        # Engine switcher
        self.engine_switcher = EngineSwitcher()
        main_layout.addWidget(self.engine_switcher)

        # Search bar
        self.search_bar = GlobalSearchBar()
        main_layout.addWidget(self.search_bar)

        # Content: tabs + param panel
        content_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(content_splitter, stretch=1)

        # Left: tabs
        self.view_tabs = QTabWidget()

        self._views = {}

        # --- 3D Explorer tab (composite: 3D | Inspector | Preview) ---
        explorer_splitter = QSplitter(Qt.Horizontal)
        self.splat3d = Splat3DView(self.signals, self.state)
        explorer_splitter.addWidget(self.splat3d)

        self.node_inspector = NodeInspector()
        explorer_splitter.addWidget(self.node_inspector)

        self.file_preview = FilePreview()
        explorer_splitter.addWidget(self.file_preview)

        explorer_splitter.setSizes([700, 380, 360])

        self._views["explorer"] = explorer_splitter
        ico = svg_icon("spatial", Colors.TEXT_DIM, 16)
        self.view_tabs.addTab(explorer_splitter, ico, "3D Explorer")

        # Standard views
        view_defs = [
            ("welcome",     WelcomeView),
            ("search",      SearchView),
            ("collections", CollectionsView),
            ("graph",       GraphView),
            ("spatial",     SpatialView),
            ("cluster",     ClusterView),
            ("ebm",         EBMView),
            ("benchmark",   BenchmarkView),
            ("ocr",         OCRView),
        ]

        for view_id, view_cls in view_defs:
            view = view_cls(self.signals, self.state)
            self._views[view_id] = view
            ico = svg_icon(TAB_ICONS.get(view_id, "home"), Colors.TEXT_DIM, 16)
            self.view_tabs.addTab(view, ico, tab_label(view_id))

        # Config tab
        self.config_editor = ConfigEditor()
        self._views["config"] = self.config_editor
        self.view_tabs.addTab(self.config_editor, svg_icon("config", Colors.TEXT_DIM, 16), tab_label("config"))

        self.view_tabs.currentChanged.connect(self._on_tab_changed)
        content_splitter.addWidget(self.view_tabs)

        # Right: params
        self.param_panel = ParamPanel()
        self.param_panel.setMaximumWidth(300)
        self.param_panel.setMinimumWidth(200)
        content_splitter.addWidget(self.param_panel)
        content_splitter.setSizes([1100, 240])

        # Bottom: IO tray + jobs
        bottom_splitter = QSplitter(Qt.Horizontal)
        self.io_tray = IOTray()
        bottom_splitter.addWidget(self.io_tray)
        self.job_queue = JobQueuePanel()
        bottom_splitter.addWidget(self.job_queue)
        bottom_splitter.setSizes([800, 400])
        main_layout.addWidget(bottom_splitter)

        # Status
        self.status_bar = SplatsDBStatusBar()
        self.setStatusBar(self.status_bar)

        self._refresh_engine_list()

    def _connect_signals(self):
        self.engine_switcher.engine_selected.connect(self._on_engine_selected)
        self.engine_switcher.start_requested.connect(self._on_start_requested)
        self.engine_switcher.add_requested.connect(self._add_engine_dialog)
        self.engine_switcher.settings_requested.connect(lambda: self.switch_view("config"))

        self.engine_manager.engine_switched.connect(self._on_engine_switched)
        self.engine_manager.engine_started.connect(self._on_engine_started)
        self.engine_manager.engine_stopped.connect(self._on_engine_stopped)
        self.engine_manager.engine_error.connect(self._on_engine_error)
        self.engine_manager.status_changed.connect(self._on_engine_status)

        self.search_bar.search_requested.connect(self.execute_global_search)
        self.signals.view_changed.connect(self.switch_view)
        self.signals.status_message.connect(self.status_bar.show_message)
        self.signals.search_requested.connect(self.execute_global_search)
        self.signals.toast_requested.connect(
            lambda msg, t: self.toast_overlay.show_toast(msg, t))

        # 3D Explorer connections
        self.splat3d.node_selected.connect(self._on_node_selected)
        self.node_inspector.navigate_to_node.connect(self._on_navigate_to_node)
        self.node_inspector.preview_file_requested.connect(self.file_preview.preview_file)
        self.node_inspector.open_file_requested.connect(self._open_file_external)
        self.file_preview.open_external_requested.connect(self._open_file_external)

    def _on_node_selected(self, node_id: str):
        """When a node is selected in 3D view, load it in inspector."""
        nodes = self.splat3d._nodes
        if node_id in nodes:
            self.node_inspector.load_node(nodes[node_id])

    def _on_navigate_to_node(self, target_id: str):
        """Navigate 3D view to another node from inspector."""
        self.splat3d.select_node(target_id)

    def _open_file_external(self, file_path: str):
        """Open file with system default application."""
        if sys.platform == "win32":
            os.startfile(file_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", file_path])
        else:
            subprocess.run(["xdg-open", file_path])

    def _load_demo_data(self):
        """Load enriched demo data with structured clusters for all views."""
        import random
        rng = random.Random(42)

        # 4 clusters × 8 nodes = 32 nodes with realistic cluster structure
        cluster_defs = [
            {"category": "backend", "base": [2.0, 1.0], "labels": [
                "User authentication module", "Payment processing API",
                "Database connection pool", "Cache invalidation strategy",
                "Background job queue", "Session management",
                "Rate limiting middleware", "API versioning strategy",
            ]},
            {"category": "frontend", "base": [-1.5, 2.5], "labels": [
                "Search indexing pipeline", "File upload handler",
                "WebSocket connection manager", "Email notification service",
                "Error handling patterns", "CORS configuration",
                "Data validation layer", "Load balancer setup",
            ]},
            {"category": "infra", "base": [-2.0, -1.5], "labels": [
                "Logging infrastructure", "Health check endpoints",
                "Configuration management", "Encryption utilities",
                "DNS resolver", "TLS certificate manager",
                "Service mesh proxy", "Container orchestrator",
            ]},
            {"category": "security", "base": [1.5, -2.0], "labels": [
                "Firewall rule engine", "Audit log pipeline",
                "Secret rotation service", "RBAC policy engine",
                "Intrusion detector", "Compliance scanner",
                "Vulnerability database", "Threat intelligence",
            ]},
        ]

        demo_nodes = []
        idx = 0

        for ci, cluster in enumerate(cluster_defs):
            for li, label in enumerate(cluster["labels"]):
                # Structured vector: cluster center + noise using stdlib random.gauss
                base_vec = [0.0] * 64
                base_vec[ci * 4] = 3.0       # cluster signal in dim 0,4,8,12
                base_vec[ci * 4 + 1] = 2.0
                base_vec[ci * 4 + 2] = 1.0
                vector = [b + rng.gauss(0, 0.5) for b in base_vec]

                connections = []
                # Strong intra-cluster connections
                for j_intra in range(len(cluster["labels"])):
                    j_global = ci * 8 + j_intra
                    if idx == j_global:
                        continue
                    score = round(rng.uniform(0.6, 0.98), 4)
                    connections.append({
                        "id": f"node_{j_global:03d}",
                        "score": score,
                        "distance": round(1.0 - score, 4),
                    })
                # Weaker inter-cluster connections
                for cj in range(4):
                    if cj == ci:
                        continue
                    bridge_idx = cj * 8 + rng.randint(0, 7)
                    score = round(rng.uniform(0.15, 0.45), 4)
                    if score > 0.25:
                        connections.append({
                            "id": f"node_{bridge_idx:03d}",
                            "score": score,
                            "distance": round(1.0 - score, 4),
                        })

                files = []
                if li % 3 == 0:
                    files.append(f"/tmp/splatsdb_demo/doc_{idx:03d}.txt")
                if li % 4 == 0:
                    files.append(f"/tmp/splatsdb_demo/diagram_{idx:03d}.png")

                demo_nodes.append({
                    "id": f"node_{idx:03d}",
                    "vector": vector,
                    "metadata": {
                        "label": label,
                        "category": cluster["category"],
                        "priority": ["high", "medium", "low"][li % 3],
                        "cluster": ci,
                        "created": f"2025-0{(ci + 1)}-{(li + 1):02d}",
                        "author": f"dev_{ci}",
                    },
                    "connections": connections,
                    "files": files,
                })
                idx += 1

        # Load into all views
        self.splat3d.load_nodes(demo_nodes)

        for view_id in ("cluster", "spatial", "graph", "ebm"):
            v = self._views.get(view_id)
            if v and hasattr(v, "load_nodes"):
                v.load_nodes(demo_nodes)

    def _build_menus(self):
        menubar = self.menuBar()

        # File
        file_menu = menubar.addMenu("&File")
        self._act(file_menu, "&Open...", "Ctrl+O", self.file_open)
        self._act(file_menu, "&Save", "Ctrl+S", self.file_save)
        file_menu.addSeparator()
        self._act(file_menu, "Add &Engine...", "", self._add_engine_dialog)
        file_menu.addSeparator()
        self._act(file_menu, "&Quit", "Ctrl+Q", self.close)

        # Edit
        edit_menu = menubar.addMenu("&Edit")
        self._act(edit_menu, "&Copy", "Ctrl+C", lambda: None)
        self._act(edit_menu, "&Paste", "Ctrl+V", lambda: None)

        # View
        view_menu = menubar.addMenu("&View")
        views = [
            ("3D Explorer",  "Ctrl+0", "explorer"),
            ("Home",         "Ctrl+1", "welcome"),
            ("Search",       "Ctrl+2", "search"),
            ("Collections",  "Ctrl+3", "collections"),
            ("Graph",        "Ctrl+4", "graph"),
            ("Spatial",      "Ctrl+5", "spatial"),
            ("Cluster",      "Ctrl+6", "cluster"),
            ("Benchmark",    "Ctrl+7", "benchmark"),
            ("OCR",          "Ctrl+8", "ocr"),
            ("Config",       "Ctrl+9", "config"),
        ]
        for name, key, vid in views:
            self._act(view_menu, name, key, lambda v=vid: self.switch_view(v))

        # Engine
        engine_menu = menubar.addMenu("&Engine")
        self._act(engine_menu, "Start", "F5", self._start_active_engine)
        self._act(engine_menu, "Stop", "Shift+F5", self._stop_active_engine)
        self._act(engine_menu, "Restart", "Ctrl+F5", self._restart_active_engine)
        engine_menu.addSeparator()
        for pname in PRESETS:
            self._act(engine_menu, f"Preset: {pname.title()}", "",
                      lambda p=pname: self._apply_preset(p))

        # Help
        help_menu = menubar.addMenu("&Help")
        self._act(help_menu, "&About", "", self._show_about)

    def _act(self, menu, text, shortcut, callback):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        menu.addAction(action)

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+K"), self, self.search_bar.focus_search)

        # ── Tab navigation shortcuts ──
        # Ctrl+Tab → next tab, Ctrl+Shift+Tab → previous tab
        QShortcut(QKeySequence("Ctrl+Tab"), self, self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, self._prev_tab)

        # Ctrl+W → close current tab
        QShortcut(QKeySequence("Ctrl+W"), self, self._close_current_tab)

        # F11 → toggle fullscreen
        QShortcut(QKeySequence("F11"), self, self._toggle_fullscreen)

    def _next_tab(self):
        """Switch to the next tab (wrapping)."""
        count = self.view_tabs.count()
        if count <= 1:
            return
        idx = self.view_tabs.currentIndex()
        self.view_tabs.setCurrentIndex((idx + 1) % count)

    def _prev_tab(self):
        """Switch to the previous tab (wrapping)."""
        count = self.view_tabs.count()
        if count <= 1:
            return
        idx = self.view_tabs.currentIndex()
        self.view_tabs.setCurrentIndex((idx - 1) % count)

    def _close_current_tab(self):
        """Close the current tab (if it's not the first one)."""
        idx = self.view_tabs.currentIndex()
        if idx <= 0:
            return  # Don't close the first (explorer) tab
        widget = self.view_tabs.widget(idx)
        if widget:
            self.view_tabs.removeTab(idx)
            widget.deleteLater()

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def switch_view(self, view_id: str):
        if not hasattr(self, '_view_tab_map'):
            # Build mapping from view_id to tab index (lazily, after tabs are populated)
            self._view_tab_map: dict[str, int] = {}
            for vid, view in self._views.items():
                widget = view if isinstance(view, QWidget) else None
                if widget is not None:
                    idx = self.view_tabs.indexOf(widget)
                    if idx >= 0:
                        self._view_tab_map[vid] = idx
        idx = self._view_tab_map.get(view_id)
        if idx is not None:
            self.view_tabs.setCurrentIndex(idx)

    def _on_tab_changed(self, index: int):
        pass

    def _refresh_engine_list(self):
        engines = self.engine_manager.list_engines()
        active = self.engine_manager.active_name()
        self.engine_switcher.update_engines(engines, active)
        if active:
            self.engine_switcher.update_status(active, self.engine_manager.get_status(active))

    def _on_engine_selected(self, name: str):
        self.engine_manager.switch_engine(name)
        self.engine_switcher.update_status(name, self.engine_manager.get_status(name))

    def _on_start_requested(self, name: str):
        status = self.engine_manager.get_status(name)
        if status == EngineStatus.RUNNING:
            self.engine_manager.stop_engine(name)
        else:
            self.engine_manager.start_engine(name)

    def _on_engine_switched(self, name: str):
        self.signals.status_message.emit(f"Switched to: {name}")
        self.status_bar.set_last_action(f"Switched engine: {name}")
        config = self.engine_manager.get_engine(name)
        if config:
            self.status_bar.set_connected(
                self.engine_manager.get_status(name) == EngineStatus.RUNNING, config.preset)
            self.status_bar.set_model(config.preset)

    def _on_engine_started(self, name: str):
        self.signals.status_message.emit(f"Started: {name}")
        self.status_bar.set_last_action(f"Engine started: {name}")
        from splatsdb_ui.widgets.toast import Toast
        Toast.show(f"Engine started: {name}", type="success")
        config = self.engine_manager.get_engine(name)
        if config:
            self.status_bar.set_connected(True, config.preset)
        self.engine_switcher.update_status(name, EngineStatus.RUNNING)
        # Immediately poll for fresh stats
        self._poll_backend()

    def _on_engine_stopped(self, name: str):
        self.signals.status_message.emit(f"Stopped: {name}")
        self.status_bar.set_last_action(f"Engine stopped: {name}")
        self.status_bar.set_connected(False)
        self.status_bar.set_db_stats(0, 0)
        self.engine_switcher.update_status(name, EngineStatus.STOPPED)

    def _on_engine_error(self, name: str, error: str):
        self.signals.status_message.emit(f"Error: {error}")
        self.status_bar.set_last_action(f"Engine error: {error[:50]}")
        from splatsdb_ui.widgets.toast import Toast
        Toast.show(f"Engine error: {error[:80]}", type="error")
        self.engine_switcher.update_status(name, EngineStatus.ERROR)

    def _on_engine_status(self, name: str, status: str):
        self.engine_switcher.update_status(name, EngineStatus(status))

    def _start_active_engine(self):
        name = self.engine_manager.active_name()
        if name:
            self.engine_manager.start_engine(name)

    def _stop_active_engine(self):
        name = self.engine_manager.active_name()
        if name:
            self.engine_manager.stop_engine(name)

    def _restart_active_engine(self):
        name = self.engine_manager.active_name()
        if name:
            self.engine_manager.stop_engine(name)
            self.engine_manager.start_engine(name)

    def _apply_preset(self, preset_name: str):
        name = self.engine_manager.active_name()
        if not name:
            return
        config = self.engine_manager.get_engine(name)
        if config:
            config.preset = preset_name
            self.config_editor.load_preset(preset_name)
            self.signals.status_message.emit(f"Preset: {preset_name}")

    def _add_engine_dialog(self):
        discovered = self.engine_manager.auto_discover()
        n = len(self.engine_manager.list_engines()) + 1
        config = EngineConfig(
            name=f"Engine {n}",
            engine_type="local" if discovered else "remote",
            binary_path=discovered[0] if discovered else "",
            port=8199 + n - 1,
        )
        self.engine_manager.add_engine(config)
        self._refresh_engine_list()
        self.signals.status_message.emit(f"Added: {config.name}")
        self.status_bar.set_last_action(f"Added engine: {config.name}")

    def _auto_start(self):
        for engine in self.engine_manager.list_engines():
            if engine.auto_start:
                self.engine_manager.start_engine(engine.name)

    def _show_about(self):
        from splatsdb_ui import __version__, __app_name__
        self.signals.status_message.emit(f"{__app_name__} v{__version__}")

    # ── Backend health / stats polling ──────────────────────────

    def _poll_backend(self):
        """Poll the active engine for health + DB stats (called every 30 s)."""
        name = self.engine_manager.active_name()
        if not name:
            self.status_bar.set_connected(False)
            return

        config = self.engine_manager.get_engine(name)
        if not config:
            return

        try:
            from splatsdb_ui.utils.api_client import SplatsDBClient
            client = SplatsDBClient(base_url=config.url, api_key=config.api_key)

            # Health check
            health = client.health()
            connected = health.status == "ok"
            self.status_bar.set_connected(connected, config.preset)

            if connected:
                # Fetch DB stats
                try:
                    status = client.status()
                    doc_count = status.n_active
                    entity_count = 0
                    # Try optimization endpoint for richer stats
                    opt = client.optimization_stats()
                    if opt:
                        entity_count = opt.get("total_adds", 0)
                    self.status_bar.set_db_stats(doc_count, entity_count)
                except Exception:
                    self.status_bar.set_doc_count(0)

                # GPU info from optimization endpoint
                try:
                    opt = client.optimization_stats()
                    gpu_cfg = opt.get("gpu_config", {})
                    if gpu_cfg and gpu_cfg.get("device_name"):
                        self.status_bar.set_gpu(gpu_cfg["device_name"])
                    elif opt.get("gpu_queries", 0) > 0:
                        self.status_bar.set_gpu("GPU")
                    else:
                        self.status_bar.set_gpu("CPU")
                except Exception:
                    pass
            else:
                self.status_bar.set_db_stats(0, 0)

            client.close()

        except Exception:
            self.status_bar.set_connected(False)
            self.status_bar.set_db_stats(0, 0)

    # ── Splash screen / loading overlay ──────────────────────────

    def _show_splash(self):
        """Show a simple splash overlay while the app initializes."""
        self._splash_label = QLabel(self)
        self._splash_label.setAlignment(Qt.AlignCenter)
        self._splash_label.setStyleSheet(f"""
            background-color: #0f1117;
            color: #f59e0b;
            font-size: 24px;
            font-weight: 700;
        """)

        # Build a simple branded pixmap
        px = QPixmap(480, 200)
        px.fill(QColor("#0f1117"))
        painter = QPainter(px)
        painter.setPen(QColor("#f59e0b"))
        font = QFont("Inter", 22, QFont.Bold)
        painter.setFont(font)
        painter.drawText(px.rect(), Qt.AlignCenter, "SplatsDB")
        painter.setPen(QColor("#6b7280"))
        font.setPointSize(11)
        font.setBold(False)
        painter.setFont(font)
        sub_rect = px.rect().adjusted(0, 30, 0, 0)
        painter.drawText(sub_rect, Qt.AlignCenter, "Loading...")
        painter.end()

        self._splash_label.setPixmap(px)
        self._splash_label.setGeometry(0, 0, self.width(), self.height())
        self._splash_label.raise_()
        self._splash_label.show()

    def _hide_splash(self):
        """Fade out / remove the splash overlay."""
        if hasattr(self, "_splash_label") and self._splash_label:
            self._splash_label.close()
            self._splash_label.deleteLater()
            self._splash_label = None

    def closeEvent(self, event):
        self.engine_manager.shutdown()
        self.save_config()
        super().closeEvent(event)
