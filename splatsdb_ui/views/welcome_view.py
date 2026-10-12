# SPDX-License-Identifier: GPL-3.0
"""Welcome view — polished with animated gradient, fade-in, keyboard hints."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QGridLayout, QGraphicsOpacityEffect,
    QSizeGrip,
)
from PySide6.QtCore import (
    Signal, Qt, QSize, QPropertyAnimation, QEasingCurve, QTimer, Property,
)
from PySide6.QtGui import (
    QDragEnterEvent, QDropEvent, QColor, QPainter, QLinearGradient,
)

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon
import splatsdb_ui


class ActionCard(QFrame):
    clicked = Signal(str)

    def __init__(self, action_id: str, title: str, description: str, icon_name: str):
        super().__init__()
        self.action_id = action_id
        self.setCursor(Qt.PointingHandCursor)
        self._hover_progress = 0.0
        self._build_ui(title, description, icon_name)

    def _build_ui(self, title: str, desc: str, icon_name: str):
        self.setMinimumSize(180, 100)
        self.setMaximumHeight(130)
        self.setStyleSheet(self._base_style())

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(icon(icon_name, Colors.ACCENT, 18).pixmap(18, 18))
        header.addWidget(icon_lbl)

        t = QLabel(title)
        t.setStyleSheet(
            f"color: {Colors.TEXT}; font-weight: 600; font-size: 14px;"
            f"letter-spacing: 0.2px;"
        )
        header.addWidget(t)
        header.addStretch()
        layout.addLayout(header)

        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px; line-height: 1.4;")
        layout.addWidget(d)
        layout.addStretch()

    def sizeHint(self) -> QSize:
        return QSize(220, 110)

    def minimumSizeHint(self) -> QSize:
        return QSize(180, 100)

    # ── Dynamic stylesheet builders ──────────────────────────

    @staticmethod
    def _base_style() -> str:
        return f"""
            ActionCard {{
                background-color: {Colors.BG_RAISED};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
                padding: 14px;
            }}
        """

    def _hover_style(self) -> str:
        return f"""
            ActionCard {{
                background-color: {Colors.BG_OVERLAY};
                border: 1.5px solid {Colors.ACCENT};
                border-radius: 10px;
                padding: 14px;
            }}
        """

    # ── Hover animation via enter/leave ─────────────────────

    def enterEvent(self, event):
        self.setStyleSheet(self._hover_style())
        self._animate_raise()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(self._base_style())
        self._animate_lower()
        super().leaveEvent(event)

    def _animate_raise(self):
        """Subtle scale-up feel via geometry nudge."""
        geo = self.geometry()
        self._raise_anim = QPropertyAnimation(self, b"geometry")
        self._raise_anim.setDuration(120)
        self._raise_anim.setStartValue(geo)
        self._raise_anim.setEndValue(geo.adjusted(-2, -2, 2, 2))
        self._raise_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._raise_anim.start()

    def _animate_lower(self):
        geo = self.geometry()
        self._lower_anim = QPropertyAnimation(self, b"geometry")
        self._lower_anim.setDuration(120)
        self._lower_anim.setStartValue(geo)
        self._lower_anim.setEndValue(geo.adjusted(2, 2, -2, -2))
        self._lower_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._lower_anim.start()

    def mousePressEvent(self, event):
        self.clicked.emit(self.action_id)
        super().mousePressEvent(event)


class DropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(180)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        upload_lbl = QLabel()
        upload_lbl.setPixmap(icon("upload", Colors.TEXT_MUTED, 32).pixmap(32, 32))
        upload_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(upload_lbl)

        lbl = QLabel("Drop files here")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 15px; font-weight: 600;"
        )
        layout.addWidget(lbl)

        sub = QLabel("Vectors, documents, images, PDFs")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(sub)

        self.setStyleSheet(f"""
            DropZone {{
                border: 2px dashed {Colors.BORDER};
                border-radius: 12px;
                background-color: {Colors.BG};
            }}
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(f"""
                DropZone {{
                    border: 2px dashed {Colors.ACCENT};
                    border-radius: 12px;
                    background-color: rgba(245, 158, 11, 0.04);
                }}
            """)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(f"""
            DropZone {{
                border: 2px dashed {Colors.BORDER};
                border-radius: 12px;
                background-color: {Colors.BG};
            }}
        """)

    def dropEvent(self, event: QDropEvent):
        self.dragLeaveEvent(event)
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        if files:
            self.files_dropped.emit(files)


class WelcomeView(QWidget):
    """Welcome / home view with animated gradient background and fade-in."""

    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._recent_actions = []
        self._gradient_hue = 0.0
        self._build_ui()
        self._setup_gradient_animation()
        self._setup_fade_in()

    # ── Animated gradient background ─────────────────────────

    def _setup_gradient_animation(self):
        """QTimer-driven gradient that slowly shifts hue."""
        self._grad_timer = QTimer(self)
        self._grad_timer.timeout.connect(self._advance_gradient)
        self._grad_timer.start(50)  # ~20fps, low CPU

    def _advance_gradient(self):
        self._gradient_hue = (self._gradient_hue + 0.15) % 360
        self.update()

    def paintEvent(self, event):
        """Draw subtle shifting gradient background via QPainter."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w, h = self.width(), self.height()
        # Two slowly-rotating gradient points create a gentle color shift
        angle = self._gradient_hue * 0.01745329  # deg → rad

        # Base dark gradient with a whisper of accent color
        base = QColor(Colors.BG)
        tint = QColor(Colors.ACCENT)
        tint.setAlpha(8)  # very subtle

        grad = QLinearGradient(
            w * 0.5 + w * 0.4 * (angle / 3.14159), 0,
            w * 0.5 - w * 0.4 * (angle / 3.14159), h,
        )
        grad.setColorAt(0.0, base)
        grad.setColorAt(0.4, tint)
        grad.setColorAt(1.0, base)

        painter.fillRect(self.rect(), grad)

        # Subtle radial glow in top-right
        from PySide6.QtGui import QRadialGradient
        glow = QRadialGradient(w * 0.85, h * 0.15, max(w, h) * 0.4)
        glow_color = QColor(Colors.ACCENT)
        glow_color.setAlpha(int(6 + 4 * ((self._gradient_hue % 120) / 120.0)))
        glow.setColorAt(0.0, glow_color)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(self.rect(), glow)

        painter.end()

    # ── Fade-in animation ────────────────────────────────────

    def _setup_fade_in(self):
        """Smooth fade-in for all content on startup."""
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self._content_widget.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(600)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        # Start after a tiny delay so the window is visible
        QTimer.singleShot(100, self._fade_anim.start)

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Wrap all content in a single widget so we can fade it as a unit
        self._content_widget = QWidget()
        layout = QVBoxLayout(self._content_widget)
        layout.setContentsMargins(40, 30, 40, 20)
        layout.setSpacing(24)

        # ── Header with version ─────────────────────────────
        header = QVBoxLayout()
        header.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel("SplatsDB")
        title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: 30px; font-weight: 700;"
            f"letter-spacing: -0.5px;"
        )
        title_row.addWidget(title)

        version_badge = QLabel(f"v{splatsdb_ui.__version__}")
        version_badge.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        version_badge.setStyleSheet(f"""
            color: {Colors.ACCENT}; font-size: 11px; font-weight: 600;
            background-color: rgba(245, 158, 11, 0.10);
            border: 1px solid rgba(245, 158, 11, 0.25);
            border-radius: 4px; padding: 2px 8px;
        """)
        title_row.addWidget(version_badge)
        title_row.addStretch()
        header.addLayout(title_row)

        subtitle = QLabel("Vector search engine with semantic memory")
        subtitle.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 15px; letter-spacing: 0.1px;"
        )
        header.addWidget(subtitle)
        layout.addLayout(header)

        # ── Quick stats row ────────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)

        self._stat_collections = self._stat_card("Collections", "0", "database")
        stats_row.addWidget(self._stat_collections)
        self._stat_docs = self._stat_card("Documents", "0", "file-text")
        stats_row.addWidget(self._stat_docs)
        self._stat_searches = self._stat_card("Searches", "0", "search")
        stats_row.addWidget(self._stat_searches)

        layout.addLayout(stats_row)

        # ── Drop zone ───────────────────────────────────────
        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._on_files_dropped)
        layout.addWidget(self.drop_zone)

        # ── Action cards grid (responsive) ──────────────────
        grid = QGridLayout()
        grid.setSpacing(12)

        self._action_shortcuts = [
            ("search",      "Search",        "Query your vector store",       "search",  "Ctrl+S"),
            ("collections", "Collections",   "Manage data collections",       "database", "Ctrl+D"),
            ("graph",       "Graph",         "Knowledge graph explorer",      "graph",    "Ctrl+G"),
            ("spatial",     "Spatial",       "Memory spaces navigator",       "spatial",  "Ctrl+P"),
            ("ocr",         "OCR Pipeline",  "Image/PDF to searchable text",  "ocr",      "Ctrl+O"),
            ("config",      "Config",        "Engine configuration",          "config",   "Ctrl+,"),
        ]

        for i, (aid, title, desc, ico, shortcut) in enumerate(self._action_shortcuts):
            card = ActionCard(aid, title, desc, ico)
            card.clicked.connect(self._on_action)
            card.setToolTip(f"{shortcut}")
            row, col = divmod(i, 3)
            grid.addWidget(card, row, col)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)

        # ── Keyboard shortcut hints ─────────────────────────
        hint_frame = QFrame()
        hint_frame.setStyleSheet(
            f"background: {Colors.BG_RAISED}; border: 1px solid {Colors.BORDER};"
            f"border-radius: 8px; padding: 6px 12px;"
        )
        hint_layout = QHBoxLayout(hint_frame)
        hint_layout.setContentsMargins(12, 8, 12, 8)
        hint_layout.setSpacing(16)

        hint_title = QLabel("⌨ Shortcuts")
        hint_title.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 11px; font-weight: 600;"
            f"letter-spacing: 0.5px; background: transparent;"
        )
        hint_layout.addWidget(hint_title)

        shortcuts = [
            ("Ctrl+S", "Search"), ("Ctrl+D", "Data"), ("Ctrl+G", "Graph"),
            ("Ctrl+P", "Spatial"), ("Ctrl+O", "OCR"), ("Ctrl+,", "Config"),
        ]
        for key, label in shortcuts:
            pair = QHBoxLayout()
            pair.setSpacing(4)
            key_lbl = QLabel(key)
            key_lbl.setStyleSheet(
                f"color: {Colors.ACCENT}; font-size: 10px; font-weight: 600;"
                f"background: rgba(245, 158, 11, 0.08);"
                f"border: 1px solid rgba(245, 158, 11, 0.18);"
                f"border-radius: 3px; padding: 1px 5px;"
            )
            pair.addWidget(key_lbl)
            desc_lbl = QLabel(label)
            desc_lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent;"
            )
            pair.addWidget(desc_lbl)
            hint_layout.addLayout(pair)

        hint_layout.addStretch()
        layout.addWidget(hint_frame)

        # ── Recent activity ────────────────────────────────
        activity_label = QLabel("RECENT ACTIVITY")
        activity_label.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1.5px; margin-top: 8px;"
        )
        layout.addWidget(activity_label)

        self._activity_frame = QFrame()
        self._activity_frame.setStyleSheet(
            f"background: {Colors.BG_RAISED}; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 8px; padding: 8px;"
        )
        self._activity_layout = QVBoxLayout(self._activity_frame)
        self._activity_layout.setSpacing(4)
        self._activity_layout.setContentsMargins(10, 6, 10, 6)
        self._empty_activity = QLabel("No recent activity")
        self._empty_activity.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px;"
        )
        self._activity_layout.addWidget(self._empty_activity)
        layout.addWidget(self._activity_frame)

        layout.addStretch()

        # ── Bottom bar: embedding model ─────────────────────
        bottom = QHBoxLayout()
        model_label = QLabel("Embedding model:")
        model_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px;")
        bottom.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(280)
        bottom.addWidget(self.model_combo, stretch=1)
        layout.addLayout(bottom)

        outer_layout.addWidget(self._content_widget)

    def _stat_card(self, label: str, value: str, icon_name: str) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            f"background: {Colors.BG_RAISED}; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 8px; padding: 8px 14px;"
        )
        row = QHBoxLayout(card)
        row.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(icon(icon_name, Colors.ACCENT, 16).pixmap(16, 16))
        row.addWidget(ico)

        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: 20px; font-weight: 700;"
        )
        val_lbl.setObjectName("value")
        row.addWidget(val_lbl)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 12px; font-weight: 500;"
        )
        row.addWidget(name_lbl)
        row.addStretch()

        return card

    def add_activity(self, action: str, detail: str = ""):
        """Add a recent activity entry."""
        from datetime import datetime
        time_str = datetime.now().strftime("%H:%M")
        self._recent_actions.insert(0, (time_str, action, detail))
        self._recent_actions = self._recent_actions[:5]
        self._refresh_activity()

    def _refresh_activity(self):
        # Clear old
        while self._activity_layout.count():
            item = self._activity_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._recent_actions:
            lbl = QLabel("No recent activity")
            lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
            self._activity_layout.addWidget(lbl)
            return

        for time_str, action, detail in self._recent_actions:
            row = QHBoxLayout()
            row.setSpacing(8)

            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 10px; font-family: monospace;"
            )
            time_lbl.setFixedWidth(36)
            row.addWidget(time_lbl)

            action_dot = QLabel("●")
            action_dot.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 8px;")
            row.addWidget(action_dot)

            action_lbl = QLabel(action)
            action_lbl.setStyleSheet(
                f"color: {Colors.TEXT}; font-size: 12px; font-weight: 500;"
            )
            row.addWidget(action_lbl)

            if detail:
                det_lbl = QLabel(detail)
                det_lbl.setStyleSheet(
                    f"color: {Colors.TEXT_DIM}; font-size: 11px;"
                )
                row.addWidget(det_lbl)
            row.addStretch()
            self._activity_layout.addLayout(row)

    def update_stats(self, collections: int = 0, docs: int = 0, searches: int = 0):
        """Update quick stats display."""
        for frame, val in [
            (self._stat_collections, collections),
            (self._stat_docs, docs),
            (self._stat_searches, searches),
        ]:
            val_lbl = frame.findChild(QLabel, "value")
            if val_lbl:
                val_lbl.setText(str(val))

    def _on_action(self, action_id: str):
        self.signals.view_changed.emit(action_id)

    def _on_files_dropped(self, files: list):
        self.signals.status_message.emit(f"Received {len(files)} files")

    def update_connection_status(self, connected: bool):
        pass
