# SPDX-License-Identifier: GPL-3.0
"""Collections view — manage vector collections with live data."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QHeaderView, QInputDialog, QMessageBox,
)
from PySide6.QtCore import QTimer
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon
from splatsdb_ui.widgets.param_panel import EmptyState


class CollectionsView(QWidget):
    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._api = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)
        title = QLabel("Collections")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 20px; font-weight: 700; letter-spacing: -0.3px;")
        header.addWidget(title)

        subtitle = QLabel("Manage data collections")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px; padding-top: 4px;")
        header.addWidget(subtitle)
        header.addStretch()

        import_btn = QPushButton(" Import")
        import_btn.setIcon(icon("upload", Colors.TEXT))
        import_btn.clicked.connect(self._import)
        header.addWidget(import_btn)

        self.refresh_btn = QPushButton(" Refresh")
        self.refresh_btn.setIcon(icon("refresh", Colors.TEXT_DIM))
        self.refresh_btn.clicked.connect(self._refresh)
        header.addWidget(self.refresh_btn)

        self.add_btn = QPushButton(" Add")
        self.add_btn.setIcon(icon("plus", Colors.BG))
        self.add_btn.setProperty("class", "primary")
        self.add_btn.clicked.connect(self._add_collection)
        header.addWidget(self.add_btn)

        self.del_btn = QPushButton(" Delete")
        self.del_btn.setIcon(icon("trash", "#fca5a5"))
        self.del_btn.setProperty("danger", "true")
        self.del_btn.clicked.connect(self._delete_collection)
        header.addWidget(self.del_btn)

        layout.addLayout(header)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Vectors", "Dimension", "Size", "Modified"])
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree, stretch=1)

        # Empty state placeholder
        self.empty_state = EmptyState(
            "No collections yet",
            "Create a new collection or connect to a SplatDB server to see existing collections."
        )
        layout.addWidget(self.empty_state)
        self.empty_state.hide()

        # Status
        self.status = QLabel("Ready")
        self.status.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.status)

        # Auto-refresh on show
        QTimer.singleShot(500, self._refresh)

    def _get_api(self):
        """Get API client from state."""
        if self._api is None:
            try:
                from splatsdb_ui.utils.api_client import ApiClient
                base_url = getattr(self.state, "api_url", "http://localhost:8199")
                self._api = ApiClient(base_url)
            except Exception:
                self._api = None
        return self._api

    def _refresh(self):
        """Refresh collection list from the backend."""
        self.signals.status_message.emit("Refreshing collections...")

        api = self._get_api()
        if api is None:
            self.status.setText("Backend not connected")
            return

        try:
            status = api.get_status()
            collections = status.get("collections", []) if isinstance(status, dict) else []

            self.tree.clear()
            if not collections:
                self.tree.hide()
                self.empty_state.show()
                self.status.setText("No collections found")
                return

            self.tree.show()
            self.empty_state.hide()

            for col in collections:
                if isinstance(col, dict):
                    from PySide6.QtWidgets import QTreeWidgetItem
                    name = col.get("name", "unknown")
                    vectors = str(col.get("vectors", col.get("count", "-")))
                    dim = str(col.get("dimension", col.get("dim", "-")))
                    size = col.get("size", "-")
                    modified = col.get("modified", "-")
                    item = QTreeWidgetItem([name, vectors, dim, str(size), str(modified)])
                    self.tree.addTopLevelItem(item)

            self.status.setText(f"{len(collections)} collections loaded")
        except Exception as e:
            self.status.setText(f"Error: {e}")
            self.signals.status_message.emit(f"Refresh failed: {e}")

    def _import(self):
        """Import vectors from file."""
        from PySide6.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import Vectors", "",
            "Vectors (*.bin *.fvecs *.bvecs);;All Files (*)",
        )
        if files:
            self.signals.status_message.emit(f"Importing {len(files)} files...")

    def _add_collection(self):
        """Add a new collection via dialog."""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Collection", "Collection name:")
        if ok and name:
            self.signals.status_message.emit(f"Creating collection: {name}")
            # TODO: call API to create collection
            self._refresh()

    def _delete_collection(self):
        """Delete the selected collection."""
        item = self.tree.currentItem()
        if not item:
            self.signals.status_message.emit("No collection selected")
            return

        name = item.text(0)
        reply = QMessageBox.question(
            self, "Delete Collection",
            f"Delete collection \"{name}\"? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.signals.status_message.emit(f"Deleting collection: {name}")
            self._refresh()

    def get_params(self) -> list:
        return [
            {"name": "dimension", "label": "Dimension", "type": "spin", "min": 1, "max": 8192, "default": 1024},
            {"name": "distance", "label": "Distance", "type": "combo", "options": ["cosine", "l2", "ip"], "default": "cosine"},
        ]

    def apply_params(self, values: dict):
        """Apply parameter changes from the ParamPanel."""
        self.signals.status_message.emit(f"Collection params: dim={values.get('dimension')}, distance={values.get('distance')}")
