# SPDX-License-Identifier: GPL-3.0
"""Welcome view — dashboard home with action cards and drop zone."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QGridLayout,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class ActionCard(QFrame):
    """A clickable card with icon, title, and description."""
    clicked = Signal(str)

    def __init__(self, action_id: str, title: str, description: str, icon_name: str):
        super().__init__()
        self.action_id = action_id
        self.setCursor(Qt.PointingHandCursor)
        self._build_ui(title, description, icon_name)

    def _build_ui(self, title: str, desc: str, icon_name: str):
        self.setMinimumSize(220, 110)
        self.setMaximumHeight(130)
        self.setStyleSheet(f"""
            ActionCard {{
                background-color: {Colors.BG_RAISED};
                border: 1px solid {Colors.BORDER};
                border-radius: 14px;
            }}
            ActionCard:hover {{
                border-color: {Colors.ACCENT};
                background-color: {Colors.BG_OVERLAY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(icon(icon_name, Colors.ACCENT, 20).pixmap(20, 20))
        header.addWidget(icon_lbl)

        t = QLabel(title)
        t.setStyleSheet(f"color: {Colors.TEXT}; font-weight: 600; font-size: 14px;")
        header.addWidget(t)
        header.addStretch()
        layout.addLayout(header)

        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px;")
        layout.addWidget(d)

    def mousePressEvent(self, event):
        self.clicked.emit(self.action_id)
        super().mousePressEvent(event)


class DropZone(QFrame):
    """Drag-and-drop file upload zone."""
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(140)
        self._build_ui()
        self._apply_idle_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        upload_lbl = QLabel()
        upload_lbl.setPixmap(icon("upload", Colors.ACCENT, 36).pixmap(36, 36))
        upload_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(upload_lbl)

        lbl = QLabel("Drop files here")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color: {Colors.TEXT}; font-size: 15px; font-weight: 600;")
        layout.addWidget(lbl)

        sub = QLabel("Vectors, documents, images, or PDFs")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px;")
        layout.addWidget(sub)

    def _apply_idle_style(self):
        self.setStyleSheet(f"""
            DropZone {{
                border: 2px dashed {Colors.BORDER_LITE};
                border-radius: 14px;
                background-color: {Colors.BG_RAISED};
            }}
        """)

    def _apply_hover_style(self):
        self.setStyleSheet(f"""
            DropZone {{
                border: 2px dashed {Colors.ACCENT};
                border-radius: 14px;
                background-color: rgba(16, 185, 129, 0.05);
            }}
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._apply_hover_style()

    def dragLeaveEvent(self, event):
        self._apply_idle_style()

    def dropEvent(self, event: QDropEvent):
        self._apply_idle_style()
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        if files:
            self.files_dropped.emit(files)


class WelcomeView(QWidget):
    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 32, 40, 24)
        layout.setSpacing(24)

        # Header
        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("SplatDB")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 30px; font-weight: 700; letter-spacing: -0.8px;")
        header.addWidget(title)
        subtitle = QLabel("Vector search engine with semantic memory")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 14px;")
        header.addWidget(subtitle)
        layout.addLayout(header)

        # Drop zone
        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._on_files_dropped)
        layout.addWidget(self.drop_zone)

        # Action grid
        section_label = QLabel("QUICK ACTIONS")
        section_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px; padding-top: 4px;")
        layout.addWidget(section_label)

        grid = QGridLayout()
        grid.setSpacing(12)

        actions = [
            ("search",      "Search",        "Query your vector store",       "search"),
            ("collections", "Collections",   "Manage data collections",       "database"),
            ("graph",       "Graph",         "Knowledge graph explorer",      "graph"),
            ("spatial",     "Spatial",       "Memory spaces navigator",       "spatial"),
            ("ocr",         "OCR Pipeline",  "Image/PDF to searchable text",  "ocr"),
            ("config",      "Config",        "Engine configuration",          "config"),
        ]

        for i, (aid, title, desc, ico) in enumerate(actions):
            card = ActionCard(aid, title, desc, ico)
            card.clicked.connect(self._on_action)
            grid.addWidget(card, i // 3, i % 3)
        layout.addLayout(grid)
        layout.addStretch()

        # Bottom: embedding model selector
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addWidget(QLabel("Embedding model"))
        bottom.addWidget(QLabel("·"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(320)
        self.model_combo.addItem("Loading models...")
        bottom.addWidget(self.model_combo, stretch=1)
        bottom.addStretch()
        layout.addLayout(bottom)

    def _on_action(self, action_id: str):
        self.signals.view_changed.emit(action_id)

    def _on_files_dropped(self, files: list):
        self.signals.status_message.emit(f"Received {len(files)} files for import")

    def update_connection_status(self, connected: bool):
        """Update welcome view based on connection status."""
        pass
