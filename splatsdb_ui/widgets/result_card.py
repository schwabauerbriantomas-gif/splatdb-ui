# SPDX-License-Identifier: GPL-3.0
"""Result card — individual search result display."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
from PySide6.QtCore import Signal
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class ResultCard(QFrame):
    """A single search result card with score bar and preview text."""
    store_clicked = Signal(int)
    explore_clicked = Signal(int)

    def __init__(self, index: int, score: float, metadata: str = ""):
        super().__init__()
        self.index = index
        self.score = max(0.0, min(1.0, float(score or 0.0)))
        self.metadata = metadata
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"""
            ResultCard {{
                background-color: {Colors.BG_RAISED};
                border: 1px solid {Colors.BORDER};
                border-radius: 10px;
            }}
            ResultCard:hover {{
                border-color: {Colors.ACCENT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 14, 16, 14)

        # Header row: index, score, actions
        header = QHBoxLayout()
        header.setSpacing(8)

        idx_label = QLabel(f"#{self.index + 1}")
        idx_label.setStyleSheet(f"color: {Colors.ACCENT}; font-weight: 700; font-size: 12px;")
        header.addWidget(idx_label)

        # Score badge
        score_pct = self.score * 100
        score_color = Colors.SUCCESS if score_pct >= 70 else (Colors.WARNING if score_pct >= 40 else Colors.ERROR)
        score_label = QLabel(f"{self.score:.1%}")
        score_label.setStyleSheet(f"color: {score_color}; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; background-color: {Colors.BG};")
        header.addWidget(score_label)

        header.addStretch()

        # Action buttons
        store_btn = QPushButton()
        store_btn.setIcon(icon("download", Colors.TEXT_DIM, 16))
        store_btn.setFixedSize(28, 28)
        store_btn.setToolTip("Store this result")
        store_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_OVERLAY};
            }}
        """)
        store_btn.clicked.connect(lambda: self.store_clicked.emit(self.index))
        header.addWidget(store_btn)

        explore_btn = QPushButton()
        explore_btn.setIcon(icon("link", Colors.TEXT_DIM, 16))
        explore_btn.setFixedSize(28, 28)
        explore_btn.setToolTip("Explore connections")
        explore_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {Colors.BG_OVERLAY};
            }}
        """)
        explore_btn.clicked.connect(lambda: self.explore_clicked.emit(self.index))
        header.addWidget(explore_btn)

        layout.addLayout(header)

        # Score bar
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(self.score * 100))
        bar.setFixedHeight(4)
        bar.setTextVisible(False)
        bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Colors.BG};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {score_color};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(bar)

        # Preview text
        if self.metadata:
            preview = QLabel(str(self.metadata)[:240])
            preview.setWordWrap(True)
            preview.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px; line-height: 1.4;")
            layout.addWidget(preview)
