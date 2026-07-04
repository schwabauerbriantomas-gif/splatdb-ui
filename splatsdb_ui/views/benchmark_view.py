# SPDX-License-Identifier: GPL-3.0
"""Benchmark view."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox, QComboBox,
)
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class BenchmarkView(QWidget):
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
        title = QLabel("Benchmarks")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 18px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        run_btn = QPushButton("Run Benchmark")
        run_btn.setIcon(icon("zap", Colors.BG))
        run_btn.setProperty("class", "primary")
        run_btn.clicked.connect(self._run_benchmark)
        header.addWidget(run_btn)
        layout.addLayout(header)

        tabs = QTabWidget()

        # Search tab
        t1 = QWidget()
        t1l = QVBoxLayout(t1)
        self.search_table = QTableWidget()
        self.search_table.setColumnCount(5)
        self.search_table.setHorizontalHeaderLabels(["Metric", "CPU", "GPU", "Speedup", "Notes"])
        self.search_table.horizontalHeader().setStretchLastSection(True)
        self.search_table.setRowCount(4)
        for i, m in enumerate(["QPS", "Latency p50", "Latency p99", "Recall@10"]):
            self.search_table.setItem(i, 0, QTableWidgetItem(m))
        t1l.addWidget(self.search_table)
        tabs.addTab(t1, "Search")

        # HNSW tab
        t2 = QWidget()
        t2l = QVBoxLayout(t2)
        self.hnsw_table = QTableWidget()
        self.hnsw_table.setColumnCount(4)
        self.hnsw_table.setHorizontalHeaderLabels(["M", "EF Construct", "Recall", "Build Time"])
        self.hnsw_table.horizontalHeader().setStretchLastSection(True)
        t2l.addWidget(self.hnsw_table)
        tabs.addTab(t2, "HNSW")

        # Ingestion tab
        t3 = QWidget()
        t3l = QVBoxLayout(t3)
        self.ingest_table = QTableWidget()
        self.ingest_table.setColumnCount(4)
        self.ingest_table.setHorizontalHeaderLabels(["Batch Size", "Vectors/sec", "Total Time", "Memory"])
        self.ingest_table.horizontalHeader().setStretchLastSection(True)
        t3l.addWidget(self.ingest_table)
        tabs.addTab(t3, "Ingestion")

        layout.addWidget(tabs, stretch=1)

        config_row = QHBoxLayout()
        config_row.addWidget(QLabel("Dataset:"))
        self.dataset_combo = QComboBox()
        self.dataset_combo.addItems(["Random 100K", "Random 1M", "GloVe-100", "SIFT-128", "NYTimes-256"])
        config_row.addWidget(self.dataset_combo)
        config_row.addWidget(QLabel("K:"))
        self.k_spin = QSpinBox()
        self.k_spin.setRange(1, 1024)
        self.k_spin.setValue(64)
        config_row.addWidget(self.k_spin)
        config_row.addStretch()
        layout.addLayout(config_row)

    def get_params(self) -> list:
        return [
            {"name": "n_queries", "label": "Queries", "type": "spin", "min": 100, "max": 100000, "default": 1000},
            {"name": "top_k", "label": "Top K", "type": "spin", "min": 1, "max": 1024, "default": 64},
        ]

    def _run_benchmark(self):
        """Trigger a benchmark run."""
        dataset = self.dataset_combo.currentText()
        k = self.k_spin.value()
        self.signals.status_message.emit(f"Benchmark: {dataset}, K={k} (not yet implemented)")
