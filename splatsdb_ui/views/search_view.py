# SPDX-License-Identifier: GPL-3.0
"""Search view — query input, results list, empty states."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QComboBox, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon
from splatsdb_ui.widgets.result_card import ResultCard
from splatsdb_ui.widgets.param_panel import EmptyState


class SearchView(QWidget):
    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._results = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)
        title = QLabel("Search")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 20px; font-weight: 700; letter-spacing: -0.3px;")
        header.addWidget(title)

        subtitle = QLabel("Query your vector store")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px; padding-top: 4px;")
        header.addWidget(subtitle)
        header.addStretch()
        layout.addLayout(header)

        # Controls bar
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter search query...")
        self.query_input.setMinimumHeight(40)
        self.query_input.returnPressed.connect(self._on_search)
        controls.addWidget(self.query_input, stretch=1)

        k_label = QLabel("Top K")
        k_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px; font-weight: 600; padding-right: 2px;")
        controls.addWidget(k_label)

        self.top_k = QSpinBox()
        self.top_k.setRange(1, 1000)
        self.top_k.setValue(10)
        self.top_k.setFixedWidth(80)
        controls.addWidget(self.top_k)

        self.collection_combo = QComboBox()
        self.collection_combo.setMinimumWidth(180)
        self.collection_combo.addItem("All collections")
        controls.addWidget(self.collection_combo)

        search_btn = QPushButton(" Search")
        search_btn.setIcon(icon("search", Colors.BG))
        search_btn.setProperty("class", "primary")
        search_btn.setMinimumHeight(40)
        search_btn.clicked.connect(self._on_search)
        controls.addWidget(search_btn)

        layout.addLayout(controls)

        # Results scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.results_widget = QWidget()
        self.results_widget.setStyleSheet("background: transparent;")
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setAlignment(Qt.AlignTop)
        self.results_layout.setSpacing(8)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.results_widget)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {Colors.BG};
                border: 1px solid {Colors.BORDER};
                border-radius: 12px;
            }}
        """)
        layout.addWidget(self.scroll, stretch=1)

        # Empty state (shown initially)
        self._empty = EmptyState(
            "Start your search",
            "Enter a query above to search your vector store."
        )
        self.results_layout.addWidget(self._empty)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.status_label)

    def _on_search(self):
        query = self.query_input.text().strip()
        if not query:
            self.status_label.setText("Please enter a search query")
            return
        self.status_label.setText(f"Searching for \"{query}\"...")
        self.signals.search_requested.emit(query)

    def set_loading(self, loading: bool):
        """Toggle loading state."""
        if loading:
            self.status_label.setText("Searching...")

    def show_results(self, results: list):
        """Display search results."""
        # Clear previous results safely
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not results:
            empty = EmptyState(
                "No results found",
                "Try a different query or adjust your search parameters."
            )
            self.results_layout.addWidget(empty)
            self.status_label.setText("No results")
            return

        for i, r in enumerate(results):
            if hasattr(r, "score"):
                score = r.score
                text = getattr(r, "text", "") or getattr(r, "metadata", "") or ""
            else:
                score = r.get("score", 0.0)
                text = r.get("text", "") or r.get("metadata", "")
            card = ResultCard(index=i, score=score, metadata=text)
            self.results_layout.addWidget(card)

        self.status_label.setText(f"{len(results)} results found")

    def get_params(self) -> list:
        return [
            {"name": "top_k", "label": "Top K", "type": "spin", "min": 1, "max": 1000, "default": 10},
            {"name": "threshold", "label": "Min Score", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.0},
        ]

    def apply_params(self, values: dict):
        """Apply parameter changes from the ParamPanel."""
        if "top_k" in values:
            self.top_k.setValue(int(values["top_k"]))
        self.signals.status_message.emit(f"Search params applied: top_k={values.get('top_k')}")
