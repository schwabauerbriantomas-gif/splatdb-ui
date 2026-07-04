# SPDX-License-Identifier: GPL-3.0
"""Collections view."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QHeaderView,
)
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class CollectionsView(QWidget):
    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Collections")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 18px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        import_btn = QPushButton("Import")
        import_btn.setIcon(icon("upload", Colors.TEXT))
        import_btn.clicked.connect(self._import)
        header.addWidget(import_btn)

        self.refresh_btn = QPushButton()
        self.refresh_btn.setIcon(icon("refresh", Colors.TEXT_DIM))
        self.refresh_btn.setFixedSize(32, 32)
        self.refresh_btn.clicked.connect(self._refresh)
        header.addWidget(self.refresh_btn)

        self.add_btn = QPushButton()
        self.add_btn.setIcon(icon("plus", Colors.BG))
        self.add_btn.setFixedSize(32, 32)
        self.add_btn.setProperty("class", "primary")
        self.add_btn.clicked.connect(self._add_collection)
        header.addWidget(self.add_btn)

        self.del_btn = QPushButton()
        self.del_btn.setIcon(icon("trash", "#fca5a5"))
        self.del_btn.setFixedSize(32, 32)
        self.del_btn.setProperty("danger", "true")
        self.del_btn.clicked.connect(self._delete_collection)
        header.addWidget(self.del_btn)

        layout.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Vectors", "Dimension", "Size", "Modified"])
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.tree, stretch=1)

        self.status = QLabel("No collections loaded")
        self.status.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        layout.addWidget(self.status)

    def _import(self):
        """Import vectors from file."""
        from PySide6.QtWidgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import Vectors", "",
            "Vectors (*.bin *.fvecs *.bvecs);;All Files (*)",
        )
        if files:
            self.signals.status_message.emit(f"Importing {len(files)} files...")

    def _refresh(self):
        """Refresh collection list."""
        self.signals.status_message.emit("Refreshing collections...")

    def _add_collection(self):
        """Add a new collection."""
        self.signals.status_message.emit("Add collection (not yet implemented)")

    def _delete_collection(self):
        """Delete the selected collection."""
        item = self.tree.currentItem()
        if item:
            name = item.text(0)
            self.signals.status_message.emit(f"Delete collection: {name}")
        else:
            self.signals.status_message.emit("No collection selected")

    def get_params(self) -> list:
        return [
            {"name": "dimension", "label": "Dimension", "type": "spin", "min": 1, "max": 8192, "default": 1024},
            {"name": "distance", "label": "Distance", "type": "combo", "options": ["cosine", "l2", "ip"]},
        ]
