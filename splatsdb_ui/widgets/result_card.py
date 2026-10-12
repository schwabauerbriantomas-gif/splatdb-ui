# SPDX-License-Identifier: GPL-3.0
"""Result card — styled with rounded corners, hover effects, and smooth transitions."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QEnterEvent, QFontMetrics
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


def _icon_button_style() -> str:
    """Shared stylesheet for small icon-only action buttons."""
    return f"""
        QPushButton {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 6px;
        }}
        QPushButton:hover {{
            background-color: {Colors.BG_OVERLAY};
            border-color: {Colors.BORDER};
        }}
    """


# ── Result card base stylesheet (property-driven variants via QSS) ──
_BASE_QSS = f"""
ResultCard {{
    background-color: {Colors.BG_RAISED};
    border: 1px solid {Colors.BORDER};
    border-radius: 10px;
    padding: 2px;
}}
ResultCard[hover="true"] {{
    background-color: {Colors.BG_OVERLAY};
    border: 1px solid {Colors.ACCENT_DARK};
    border-radius: 10px;
    padding: 2px;
}}
ResultCard[focused="true"] {{
    background-color: {Colors.BG_OVERLAY};
    border: 2px solid {Colors.ACCENT_BRIGHT};
    border-radius: 10px;
    padding: 2px;
}}
"""


class ResultCard(QFrame):
    store_clicked = Signal(int)
    explore_clicked = Signal(int)

    def __init__(self, index: int, score: float, metadata: str = ""):
        super().__init__()
        self.index = index
        self.score = score
        self.metadata = metadata
        self._hovered = False
        self._kb_focused = False
        self.setProperty("class", "result-card")
        self._build_ui()
        self.setStyleSheet(_BASE_QSS)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(14, 12, 14, 12)

        header = QHBoxLayout()
        header.setSpacing(8)

        # Rank badge
        idx_label = QLabel(f" #{self.index + 1} ")
        idx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_label.setStyleSheet(f"""
            QLabel {{
                background-color: {Colors.ACCENT};
                color: {Colors.BG};
                font-weight: 700;
                font-size: 11px;
                border-radius: 8px;
                padding: 2px 8px;
            }}
        """)
        header.addWidget(idx_label)

        # Score display
        score_pct = self.score * 100
        if score_pct >= 80:
            score_color = Colors.SUCCESS
        elif score_pct >= 50:
            score_color = Colors.WARNING
        else:
            score_color = Colors.TEXT_DIM

        score_label = QLabel(f"{self.score:.1%}")
        score_label.setStyleSheet(
            f"color: {score_color}; font-size: 12px; font-weight: 700;"
        )
        header.addWidget(score_label)
        header.addStretch()

        # Action buttons — using shared helper (item 35)
        store_btn = QPushButton()
        store_btn.setIcon(icon("download", Colors.TEXT_DIM, 16))
        store_btn.setFixedSize(28, 28)
        store_btn.setToolTip("Store result")
        store_btn.setStyleSheet(_icon_button_style())
        store_btn.clicked.connect(lambda: self.store_clicked.emit(self.index))
        header.addWidget(store_btn)

        explore_btn = QPushButton()
        explore_btn.setIcon(icon("link", Colors.TEXT_DIM, 16))
        explore_btn.setFixedSize(28, 28)
        explore_btn.setToolTip("Explore connections")
        explore_btn.setStyleSheet(_icon_button_style())
        explore_btn.clicked.connect(lambda: self.explore_clicked.emit(self.index))
        header.addWidget(explore_btn)

        layout.addLayout(header)

        # Score bar — max-height: 4px + explicit border: none on groove (item 36)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(self.score * 100))
        bar.setMaximumHeight(4)
        bar.setTextVisible(False)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Colors.BG_OVERLAY};
                border: none;
                border-radius: 2px;
                max-height: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {score_color};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(bar)

        # Metadata preview — QFontMetrics elide instead of raw truncation (item 37)
        if self.metadata:
            preview_text = str(self.metadata)
            preview_label = QLabel(preview_text)
            preview_label.setWordWrap(True)
            # Elide at ~200 chars visually using font metrics
            fm = QFontMetrics(preview_label.font())
            elided = fm.elidedText(preview_text, Qt.TextElideMode.ElideRight, 200 * fm.averageCharWidth())
            preview_label.setText(elided)
            preview_label.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; font-size: 12px; line-height: 1.4;"
            )
            layout.addWidget(preview_label)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── Property-based hover / focus (items 33-34) ────────────────

    def set_focused(self, focused: bool):
        """Apply or remove keyboard-focus highlight via dynamic property."""
        self._kb_focused = focused
        self.setProperty("focused", "true" if focused else "false")
        # Force QSS re-evaluation without full stylesheet replacement
        self.style().unpolish(self)
        self.style().polish(self)

    def enterEvent(self, event: QEnterEvent):
        self._hovered = True
        self.setProperty("hover", "true")
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        if not self._kb_focused:
            self.setProperty("hover", "false")
            self.style().unpolish(self)
            self.style().polish(self)
        super().leaveEvent(event)
