# SPDX-License-Identifier: GPL-3.0
"""Benchmark view — performance benchmarking dashboard."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox, QComboBox,
)
from PySide6.QtCore import Qt
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


# Real validated benchmark from the SplatsDB project
# Source: splatsdb/benchmark_results.json
VALIDATED_BENCHMARK = [
    {"metric": "QPS (queries/sec)",    "cpu": "10.55",   "gpu": "—",      "speedup": "—",       "notes": "100K splats, k=64, linear baseline"},
    {"metric": "QPS (M2M accelerated)", "cpu": "1012.77", "gpu": "—",      "speedup": "96.0x",   "notes": "100K splats, k=64, M2M index [VALIDATED]"},
    {"metric": "Latency p50 (ms)",      "cpu": "0.99",    "gpu": "—",      "speedup": "95.7x",   "notes": "Median query latency [VALIDATED]"},
    {"metric": "Latency p99 (ms)",      "cpu": "2.1",     "gpu": "—",      "speedup": "—",       "notes": "99th percentile [VALIDATED]"},
    {"metric": "Recall@10",             "cpu": "1.000",   "gpu": "—",      "speedup": "—",       "notes": "Exact recall, M2M [VALIDATED]"},
    {"metric": "Index build (s)",       "cpu": "0.034",   "gpu": "—",      "speedup": "—",       "notes": "100K splats indexing [VALIDATED]"},
    {"metric": "Memory (MB)",           "cpu": "412",     "gpu": "—",      "speedup": "—",       "notes": "Total RSS [VALIDATED]"},
]


class BenchmarkView(QWidget):
    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)
        title = QLabel("Benchmarks")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 20px; font-weight: 700; letter-spacing: -0.3px;")
        header.addWidget(title)

        subtitle = QLabel("Performance metrics")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px; padding-top: 4px;")
        header.addWidget(subtitle)
        header.addStretch()

        run_btn = QPushButton(" Run Benchmark")
        run_btn.setIcon(icon("zap", Colors.BG))
        run_btn.setProperty("class", "primary")
        run_btn.clicked.connect(self._run_benchmark)
        header.addWidget(run_btn)

        layout.addLayout(header)

        # Info banner
        info = QLabel("Showing validated results from benchmark_results.json (100K splats, 1K queries, k=64)")
        info.setStyleSheet(f"""
            color: {Colors.TEXT_DIM};
            font-size: 11px;
            background-color: {Colors.BG_RAISED};
            border: 1px solid {Colors.BORDER};
            border-radius: 8px;
            padding: 8px 12px;
        """)
        layout.addWidget(info)

        # Tabs
        tabs = QTabWidget()

        # Search benchmark tab (with validated data)
        t1 = QWidget()
        t1l = QVBoxLayout(t1)
        t1l.setContentsMargins(0, 0, 0, 0)
        self.search_table = QTableWidget()
        self.search_table.setColumnCount(5)
        self.search_table.setHorizontalHeaderLabels(["Metric", "CPU", "GPU", "Speedup", "Notes"])
        self.search_table.horizontalHeader().setStretchLastSection(True)
        self.search_table.setAlternatingRowColors(True)
        self.search_table.setRowCount(len(VALIDATED_BENCHMARK))
        for i, row in enumerate(VALIDATED_BENCHMARK):
            self.search_table.setItem(i, 0, QTableWidgetItem(row["metric"]))
            self.search_table.setItem(i, 1, QTableWidgetItem(row["cpu"]))
            self.search_table.setItem(i, 2, QTableWidgetItem(row["gpu"]))
            self.search_table.setItem(i, 3, QTableWidgetItem(row["speedup"]))
            self.search_table.setItem(i, 4, QTableWidgetItem(row["notes"]))
        self.search_table.resizeColumnsToContents()
        self.search_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        t1l.addWidget(self.search_table)
        tabs.addTab(t1, "Search Performance")

        # HNSW tab (placeholder with structure)
        t2 = QWidget()
        t2l = QVBoxLayout(t2)
        t2l.setContentsMargins(0, 0, 0, 0)
        self.hnsw_table = QTableWidget()
        self.hnsw_table.setColumnCount(4)
        self.hnsw_table.setHorizontalHeaderLabels(["M", "EF Construct", "Recall", "Build Time"])
        self.hnsw_table.horizontalHeader().setStretchLastSection(True)
        self.hnsw_table.setAlternatingRowColors(True)
        placeholder = QLabel("HNSW index benchmarks not yet available.\nRun a benchmark with an HNSW-configured engine to populate this table.")
        placeholder.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px; padding: 20px;")
        placeholder.setAlignment(Qt.AlignCenter)
        t2l.addWidget(self.hnsw_table)
        t2l.addWidget(placeholder)
        tabs.addTab(t2, "HNSW Index")

        # Ingestion tab
        t3 = QWidget()
        t3l = QVBoxLayout(t3)
        t3l.setContentsMargins(0, 0, 0, 0)
        self.ingest_table = QTableWidget()
        self.ingest_table.setColumnCount(4)
        self.ingest_table.setHorizontalHeaderLabels(["Batch Size", "Vectors/sec", "Total Time", "Memory"])
        self.ingest_table.horizontalHeader().setStretchLastSection(True)
        self.ingest_table.setAlternatingRowColors(True)
        t3l.addWidget(self.ingest_table)
        tabs.addTab(t3, "Ingestion")

        layout.addWidget(tabs, stretch=1)

        # Config row
        config_row = QHBoxLayout()
        config_row.setSpacing(10)

        config_row.addWidget(QLabel("Dataset"))
        self.dataset_combo = QComboBox()
        self.dataset_combo.addItems(["Random 100K [VALIDATED]", "Random 1M", "GloVe-100", "SIFT-128", "NYTimes-256"])
        config_row.addWidget(self.dataset_combo)

        config_row.addWidget(QLabel("K"))
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

    def apply_params(self, values: dict):
        if "top_k" in values:
            self.k_spin.setValue(int(values["top_k"]))
        self.signals.status_message.emit(f"Benchmark params: queries={values.get('n_queries')}, k={values.get('top_k')}")

    def _run_benchmark(self):
        """Trigger a benchmark run against the connected engine."""
        dataset = self.dataset_combo.currentText()
        k = self.k_spin.value()
        self.signals.status_message.emit(f"Benchmark queued: {dataset}, K={k}")
        # TODO: implement actual benchmark execution via API client
