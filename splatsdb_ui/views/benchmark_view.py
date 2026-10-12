# SPDX-License-Identifier: GPL-3.0
"""Benchmark Dashboard — QPainter-based performance visualization.

Loads actual benchmark JSON results from SplatsDB benchmarks/ directory.
Charts rendered with QPainter — no matplotlib/pyqtgraph dependency.

Visualizations:
  1. QPS vs Recall scatter plot — Pareto frontier
  2. Build time comparison — horizontal bar chart
  3. Latency histogram — distribution of query times
  4. Dataset comparison table — styled metrics grid

Visual style: "Mission Control" — dark panels with amber/green/red status indicators.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSizePolicy, QFrame, QFileDialog,
)
from PySide6.QtCore import Signal, Qt, QTimer, QPointF, QRectF, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QRadialGradient, QLinearGradient, QPainterPath, QPolygonF,
)

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon
from splatsdb_ui.utils.widgets import build_toolbar, build_info_bar, make_button


# ---------------------------------------------------------------------------
# Benchmark data loader
# ---------------------------------------------------------------------------

class BenchmarkResult:
    """Single benchmark configuration result."""

    def __init__(self, name: str, qps: float, recall: float, build_s: float,
                 method: str, params: dict = None):
        self.name = name
        self.qps = qps
        self.recall = recall
        self.build_s = build_s
        self.method = method  # "hnsw" or "ivf"
        self.params = params or {}

    @property
    def latency_ms(self) -> float:
        return 1000.0 / self.qps if self.qps > 0 else 0

    @property
    def color(self) -> QColor:
        if self.method == "hnsw":
            return QColor(Colors.ACCENT)     # amber
        elif self.method == "ivf":
            return QColor(Colors.INFO)        # blue
        return QColor(Colors.SUCCESS)         # green


class DatasetResults:
    """Results for a single dataset."""

    def __init__(self, name: str, n_train: int, n_test: int, dim: int):
        self.name = name
        self.n_train = n_train
        self.n_test = n_test
        self.dim = dim
        self.results: list[BenchmarkResult] = []

    def pareto_frontier(self) -> list[BenchmarkResult]:
        """Return results on the QPS-Recall Pareto frontier."""
        if not self.results:
            return []
        sorted_r = sorted(self.results, key=lambda r: r.recall)
        frontier = [sorted_r[0]]
        for r in sorted_r[1:]:
            if r.qps > frontier[-1].qps:
                frontier.append(r)
        return frontier


def load_benchmark_data(bench_dir: str) -> list[DatasetResults]:
    """Load all benchmark result JSONs from directory."""
    datasets = []
    bench_path = Path(bench_dir)

    for json_file in sorted(bench_path.glob("results_*.json")):
        try:
            with open(json_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        name = data.get("dataset", json_file.stem.replace("results_", ""))
        n_train = data.get("n_train", 0)
        n_test = data.get("n_test", 0)
        dim = data.get("dim", 0)

        ds = DatasetResults(name, n_train, n_test, dim)

        for key, val in data.items():
            if isinstance(val, dict) and "qps" in val and "recall" in val:
                method = "hnsw" if "hnsw" in key else ("ivf" if "ivf" in key else "other")
                params = {}
                if method == "hnsw":
                    parts = key.replace("hnsw_", "").split("_")
                    for p in parts:
                        if p.startswith("M"):
                            params["M"] = int(p[1:])
                        elif p.startswith("ef"):
                            params["ef"] = int(p[2:])
                elif method == "ivf":
                    parts = key.replace("ivf_", "").split("_")
                    for p in parts:
                        if p.startswith("nprobe"):
                            params["nprobe"] = int(p[6:])

                ds.results.append(BenchmarkResult(
                    name=key,
                    qps=val.get("qps", 0),
                    recall=val.get("recall", 0),
                    build_s=val.get("build_s", 0),
                    method=method,
                    params=params,
                ))

        if ds.results:
            datasets.append(ds)

    return datasets


# ---------------------------------------------------------------------------
# Chart rendering utilities
# ---------------------------------------------------------------------------

class ChartArea:
    """Manages coordinate mapping for a chart area."""

    def __init__(self, x: int, y: int, w: int, h: int,
                 data_x: tuple, data_y: tuple,
                 x_label: str = "", y_label: str = "",
                 x_fmt: str = ".2f", y_fmt: str = ".0f"):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.data_x = data_x  # (min, max)
        self.data_y = data_y
        self.x_label = x_label
        self.y_label = y_label
        self.x_fmt = x_fmt
        self.y_fmt = y_fmt
        self.pad_left = 65
        self.pad_right = 20
        self.pad_top = 25
        self.pad_bottom = 40

    @property
    def plot_x(self) -> int:
        return self.x + self.pad_left

    @property
    def plot_y(self) -> int:
        return self.y + self.pad_top

    @property
    def plot_w(self) -> int:
        return self.w - self.pad_left - self.pad_right

    @property
    def plot_h(self) -> int:
        return self.h - self.pad_top - self.pad_bottom

    def to_screen(self, dx: float, dy: float) -> QPointF:
        x_range = self.data_x[1] - self.data_x[0]
        y_range = self.data_y[1] - self.data_y[0]
        sx = self.plot_x + (dx - self.data_x[0]) / x_range * self.plot_w if x_range > 0 else self.plot_x
        sy = self.plot_y + self.plot_h - (dy - self.data_y[0]) / y_range * self.plot_h if y_range > 0 else self.plot_y + self.plot_h
        return QPointF(sx, sy)

    def draw_grid(self, painter: QPainter, n_x: int = 5, n_y: int = 5):
        """Draw grid lines and labels with improved formatting."""
        # Background — subtle top-to-bottom gradient
        grad = Colors.linear_gradient(
            0, self.plot_y, 0, self.plot_y + self.plot_h,
            (0.0, "#0f1117"), (1.0, "#131720"),
        )
        painter.fillRect(self.plot_x, self.plot_y, self.plot_w, self.plot_h,
                         QBrush(grad))

        # Grid lines — subtle dashed style
        pen_grid = QPen(Colors.with_alpha(QColor(Colors.TEXT), 18), 0.5, Qt.PenStyle.DotLine)
        painter.setPen(pen_grid)

        for i in range(n_x + 1):
            t = i / n_x
            x = self.plot_x + t * self.plot_w
            painter.drawLine(int(x), self.plot_y, int(x), self.plot_y + self.plot_h)
            val = self.data_x[0] + t * (self.data_x[1] - self.data_x[0])
            painter.setPen(QColor(Colors.TEXT_DIM))
            painter.setFont(QFont("monospace", 7))
            formatted = self._format_axis_value(val, self.x_fmt)
            painter.drawText(int(x - 20), self.plot_y + self.plot_h + 14, formatted)
            painter.setPen(pen_grid)

        for i in range(n_y + 1):
            t = i / n_y
            y = self.plot_y + t * self.plot_h
            painter.drawLine(self.plot_x, int(y), self.plot_x + self.plot_w, int(y))
            val = self.data_y[1] - t * (self.data_y[1] - self.data_y[0])
            painter.setPen(QColor(Colors.TEXT_DIM))
            painter.setFont(QFont("monospace", 7))
            formatted = self._format_axis_value(val, self.y_fmt)
            painter.drawText(self.plot_x - 58, int(y + 4), formatted)
            painter.setPen(pen_grid)

        # Axes
        painter.setPen(QPen(QColor(Colors.BORDER), 1))
        painter.drawRect(self.plot_x, self.plot_y, self.plot_w, self.plot_h)

        # Labels
        painter.setPen(QColor(Colors.TEXT_DIM))
        painter.setFont(QFont("sans-serif", 8))
        # X label
        painter.drawText(self.plot_x + self.plot_w // 2 - 30,
                         self.plot_y + self.plot_h + 32, self.x_label)
        # Y label
        painter.save()
        painter.translate(self.x + 10, self.plot_y + self.plot_h // 2)
        painter.rotate(-90)
        painter.drawText(-30, 0, self.y_label)
        painter.restore()

    @staticmethod
    def _format_axis_value(val: float, fmt: str) -> str:
        """Format axis values with K/M suffixes for large numbers."""
        if fmt == ".0f" and abs(val) >= 1_000_000:
            return f"{val / 1_000_000:.1f}M"
        elif fmt == ".0f" and abs(val) >= 1_000:
            return f"{val / 1_000:.1f}K"
        return f"{val:{fmt}}"


# ---------------------------------------------------------------------------
# Benchmark Canvas
# ---------------------------------------------------------------------------

class BenchmarkCanvas(QWidget):
    """Benchmark dashboard canvas with multiple chart panels."""

    # Palette for overlay comparison mode — one colour per dataset
    _OVERLAY_PALETTE = [
        QColor(Colors.ACCENT),     # amber
        QColor(Colors.INFO),       # blue
        QColor(Colors.SUCCESS),    # green
        QColor(Colors.ERROR),      # red
        QColor(168, 85, 247),      # purple
        QColor(236, 72, 153),      # pink
        QColor(20, 184, 166),      # teal
        QColor(251, 191, 36),      # yellow
    ]

    def __init__(self):
        super().__init__()
        self.setMinimumSize(800, 600)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._datasets: list[DatasetResults] = []
        self._current_idx = 0
        self._hovered_result: Optional[BenchmarkResult] = None
        self._hover_pos = QPointF(0, 0)

        # Comparison overlay mode
        self._comparison_mode = False

        # Animation progress (0.0 → 1.0) for bar growth
        self._anim_progress = 0.0
        self._anim = QPropertyAnimation(self, b"anim_progress")
        self._anim.setDuration(500)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self.setMouseTracking(True)

        # Resize debounce timer
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)

    # ── QProperty for animation ──

    def _get_anim_progress(self) -> float:
        return self._anim_progress

    def _set_anim_progress(self, v: float):
        self._anim_progress = v
        self.update()

    anim_progress = Property(float, _get_anim_progress, _set_anim_progress)

    def load_datasets(self, datasets: list[DatasetResults]):
        self._datasets = datasets
        self._current_idx = 0
        self._start_anim()

    def set_dataset(self, idx: int):
        if 0 <= idx < len(self._datasets):
            self._current_idx = idx
            self._start_anim()

    # ── Comparison mode ──

    def set_comparison_mode(self, enabled: bool):
        self._comparison_mode = enabled
        self._start_anim()

    @property
    def comparison_mode(self) -> bool:
        return self._comparison_mode

    def _start_anim(self):
        """Restart the bar-grow animation from zero."""
        self._anim.stop()
        self._anim_progress = 0.0
        self._anim.start()

    @property
    def dataset_names(self) -> list[str]:
        return [d.name for d in self._datasets]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(Colors.BG))

        if not self._datasets:
            painter.setPen(QColor(Colors.TEXT_DIM))
            painter.setFont(QFont("sans-serif", 13))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "Load benchmark results to visualize")
            painter.end()
            return

        margin = 16
        gap = 16
        half_w = (w - margin * 3) // 2
        half_h = (h - margin * 3) // 2

        if self._comparison_mode and len(self._datasets) > 1:
            # ── Overlay mode: all datasets on the same charts ──
            all_ds = self._datasets

            # Panel 1: overlaid scatter
            self._paint_scatter_overlay(painter, margin, margin, half_w, half_h, all_ds)

            # Panel 2: grouped build-time bars
            self._paint_build_time_overlay(painter, margin * 2 + half_w, margin, half_w, half_h, all_ds)

            # Panel 3: overlaid latency
            self._paint_latency_overlay(painter, margin, margin * 2 + half_h, half_w, half_h, all_ds)

            # Panel 4: comparison legend
            self._paint_comparison_legend(painter, margin * 2 + half_w, margin * 2 + half_h, half_w, half_h, all_ds)
        else:
            ds = self._datasets[self._current_idx]

            # Panel 1: QPS vs Recall (top-left)
            self._paint_scatter(painter, margin, margin, half_w, half_h, ds)

            # Panel 2: Build time bars (top-right)
            self._paint_build_time(painter, margin * 2 + half_w, margin, half_w, half_h, ds)

            # Panel 3: Latency chart (bottom-left)
            self._paint_latency(painter, margin, margin * 2 + half_h, half_w, half_h, ds)

            # Panel 4: Summary metrics (bottom-right)
            self._paint_summary(painter, margin * 2 + half_w, margin * 2 + half_h, half_w, half_h, ds)

        # Hover tooltip
        if self._hovered_result:
            self._paint_tooltip(painter, self._hover_pos, self._hovered_result)

        painter.end()

    # --- Panel 1: QPS vs Recall scatter ---

    def _paint_scatter(self, painter: QPainter, x: int, y: int, w: int, h: int,
                       ds: DatasetResults):
        self._draw_panel_bg(painter, x, y, w, h, "QPS vs Recall",
                            f"{ds.name} · {len(ds.results)} configs")

        if not ds.results:
            return

        recalls = [r.recall for r in ds.results]
        qps_vals = [r.qps for r in ds.results]

        chart = ChartArea(x, y, w, h,
                          (min(recalls) - 0.02, 1.0),
                          (0, max(qps_vals) * 1.1),
                          "Recall", "QPS",
                          ".3f", ".0f")
        chart.draw_grid(painter)

        # Pareto frontier
        frontier = ds.pareto_frontier()
        if len(frontier) >= 2:
            path = QPainterPath()
            sp = chart.to_screen(frontier[0].recall, frontier[0].qps)
            path.moveTo(sp)
            for r in frontier[1:]:
                sp = chart.to_screen(r.recall, r.qps)
                path.lineTo(sp)
            painter.setPen(QPen(QColor(Colors.ACCENT), 1.5, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        # Data points
        for r in ds.results:
            sp = chart.to_screen(r.recall, r.qps)
            color = r.color

            # Glow
            glow = QRadialGradient(QPointF(0, 0), 12)
            glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 60))
            glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.save()
            painter.translate(sp)
            painter.drawEllipse(QPointF(0, 0), 12, 12)
            painter.restore()

            # Dot
            dot_size = 5
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.lighter(150), 1))
            painter.save()
            painter.translate(sp)
            painter.drawEllipse(QPointF(0, 0), dot_size, dot_size)
            painter.restore()

    # --- Panel 2: Build time bars ---

    def _paint_build_time(self, painter: QPainter, x: int, y: int, w: int, h: int,
                          ds: DatasetResults):
        self._draw_panel_bg(painter, x, y, w, h, "Build Time (seconds)",
                            ", ".join(sorted(set(r.method.upper() for r in ds.results))))

        if not ds.results:
            return

        # Deduplicate by method family
        families = {}
        for r in ds.results:
            if r.method == "hnsw":
                key = f"HNSW M{r.params.get('M', '?')}"
            elif r.method == "ivf":
                key = "IVF"
            else:
                key = r.name
            if key not in families or r.build_s > families[key].build_s:
                families[key] = r

        items = sorted(families.values(), key=lambda r: r.build_s, reverse=True)
        if not items:
            return

        max_build = max(r.build_s for r in items)
        bar_area_x = x + 90
        bar_area_w = w - 110
        bar_h = min(28, (h - 60) // max(len(items), 1))
        start_y = y + 40

        for i, r in enumerate(items):
            by = start_y + i * (bar_h + 6)
            bar_w = r.build_s / max_build * bar_area_w if max_build > 0 else 0
            bar_w *= self._anim_progress  # animate growth

            # Bar
            grad = QLinearGradient(QPointF(0, 0), QPointF(bar_w, 0))
            c = r.color
            grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 180))
            grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 100))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(int(bar_area_x), int(by), int(bar_w), bar_h, 3, 3)

            # Label
            painter.setPen(QColor(Colors.TEXT))
            painter.setFont(QFont("monospace", 8))
            label = r.name.replace("hnsw_", "HNSW ").replace("ivf_", "IVF ").replace("_", " ")
            painter.drawText(x + 8, int(by + bar_h // 2 + 4), label)

            # Value
            painter.setPen(QColor(Colors.TEXT_DIM))
            painter.drawText(int(bar_area_x + bar_w + 6), int(by + bar_h // 2 + 4),
                             f"{r.build_s:.1f}s")

    # --- Panel 3: Latency ---

    def _paint_latency(self, painter: QPainter, x: int, y: int, w: int, h: int,
                       ds: DatasetResults):
        self._draw_panel_bg(painter, x, y, w, h, "Query Latency (ms/query)",
                            f"{ds.n_train:,} vectors · {ds.dim}D")

        if not ds.results:
            return

        latencies = sorted([r.latency_ms for r in ds.results])
        if not latencies:
            return

        chart = ChartArea(x, y, w, h,
                          (0, len(latencies)),
                          (0, max(latencies) * 1.1),
                          "Config #", "Latency (ms)",
                          ".0f", ".2f")
        chart.draw_grid(painter)

        # Bar chart
        bar_w = max(4, chart.plot_w // len(latencies) - 2)
        for i, lat in enumerate(latencies):
            sp = chart.to_screen(i, lat)
            base = chart.to_screen(i, 0)

            # Animate: scale height by _anim_progress
            anim_h = (base.y() - sp.y()) * self._anim_progress
            anim_top = base.y() - anim_h

            # Color by latency
            if lat < 1.0:
                c = QColor(Colors.SUCCESS)   # green — fast
            elif lat < 5.0:
                c = QColor(Colors.ACCENT)    # amber — moderate
            else:
                c = QColor(Colors.ERROR)     # red — slow

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c))
            bw = max(bar_w, 3)
            bh = anim_h
            painter.drawRect(int(sp.x() - bw / 2), int(anim_top), bw, int(bh))

    # --- Panel 4: Summary metrics ---

    def _paint_summary(self, painter: QPainter, x: int, y: int, w: int, h: int,
                       ds: DatasetResults):
        self._draw_panel_bg(painter, x, y, w, h, "Dataset Summary",
                            f"{ds.dim}D · {ds.n_train:,} train · {ds.n_test:,} test")

        if not ds.results:
            return

        metrics = [
            ("Dataset", ds.name),
            ("Dimensions", str(ds.dim)),
            ("Training vectors", f"{ds.n_train:,}"),
            ("Test queries", f"{ds.n_test:,}"),
            ("Configurations", str(len(ds.results))),
            ("Best recall", f"{max(r.recall for r in ds.results):.4f}"),
            ("Best QPS", f"{max(r.qps for r in ds.results):,}"),
            ("Fastest query", f"{min(r.latency_ms for r in ds.results):.3f} ms"),
            ("Methods", ", ".join(sorted(set(r.method.upper() for r in ds.results)))),
        ]

        # Status indicator
        best_recall = max(r.recall for r in ds.results)
        if best_recall >= 0.99:
            status_color = QColor(Colors.SUCCESS)
            status_text = "EXCELLENT"
        elif best_recall >= 0.95:
            status_color = QColor(Colors.ACCENT)
            status_text = "GOOD"
        else:
            status_color = QColor(Colors.ERROR)
            status_text = "NEEDS TUNING"

        # Status badge
        badge_w = 120
        badge_h = 28
        badge_x = x + w - badge_w - 12
        badge_y = y + 10
        painter.setPen(QPen(status_color, 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(badge_x, badge_y, badge_w, badge_h, 4, 4)
        painter.setPen(status_color)
        painter.setFont(QFont("monospace", 9, QFont.Weight.Bold))
        painter.drawText(badge_x + 8, badge_y + 18, status_text)

        # Metrics grid
        row_h = 22
        start_y = y + 48
        col1_x = x + 12
        col2_x = x + w // 2

        for i, (label, value) in enumerate(metrics):
            row_y = start_y + i * row_h
            cx = col1_x if i < 5 else col2_x
            cy = row_y if i < 5 else row_y - 5 * row_h

            # Divider line every other row
            if i % 2 == 0:
                painter.setPen(QPen(QColor(255, 255, 255, 8), 0.5))
                painter.drawLine(cx, int(cy + row_h - 2), cx + w // 2 - 20, int(cy + row_h - 2))

            painter.setPen(QColor(Colors.TEXT_DIM))
            painter.setFont(QFont("monospace", 8))
            painter.drawText(cx, int(cy + 14), label)

            painter.setPen(QColor(Colors.TEXT))
            painter.setFont(QFont("monospace", 9, QFont.Weight.Bold))
            painter.drawText(cx, int(cy + 28), value)

    # --- Overlay mode: Scatter comparison ---

    def _paint_scatter_overlay(self, painter: QPainter, x: int, y: int,
                               w: int, h: int, datasets: list[DatasetResults]):
        self._draw_panel_bg(painter, x, y, w, h, "QPS vs Recall — Comparison")

        all_results = [r for ds in datasets for r in ds.results]
        if not all_results:
            return

        recalls = [r.recall for r in all_results]
        qps_vals = [r.qps for r in all_results]

        chart = ChartArea(x, y, w, h,
                          (min(recalls) - 0.02, 1.0),
                          (0, max(qps_vals) * 1.1),
                          "Recall", "QPS",
                          ".3f", ".0f")
        chart.draw_grid(painter)

        # Draw each dataset's points in its assigned colour
        for di, ds in enumerate(datasets):
            color = self._OVERLAY_PALETTE[di % len(self._OVERLAY_PALETTE)]
            for r in ds.results:
                sp = chart.to_screen(r.recall, r.qps)

                # Glow
                glow = QRadialGradient(QPointF(0, 0), 14)
                glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 50))
                glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(glow))
                painter.save()
                painter.translate(sp)
                painter.drawEllipse(QPointF(0, 0), 14, 14)
                painter.restore()

                # Dot — slightly larger so overlapping is visible
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(color.lighter(150), 1))
                painter.save()
                painter.translate(sp)
                painter.drawEllipse(QPointF(0, 0), 5, 5)
                painter.restore()

    # --- Overlay mode: Build time grouped bars ---

    def _paint_build_time_overlay(self, painter: QPainter, x: int, y: int,
                                   w: int, h: int, datasets: list[DatasetResults]):
        self._draw_panel_bg(painter, x, y, w, h, "Build Time — Comparison")

        # Collect unique method families across all datasets
        all_families: list[str] = []
        family_map: dict[str, list[tuple[int, BenchmarkResult]]] = {}
        for di, ds in enumerate(datasets):
            for r in ds.results:
                if r.method == "hnsw":
                    key = f"HNSW M{r.params.get('M', '?')}"
                elif r.method == "ivf":
                    key = "IVF"
                else:
                    key = r.name
                if key not in family_map:
                    all_families.append(key)
                    family_map[key] = []
                family_map[key].append((di, r))

        if not all_families:
            return

        # Compute max build time across everything
        max_build = max(r.build_s for entries in family_map.values() for _, r in entries)
        n_groups = len(all_families)
        n_bars_per_group = len(datasets)
        bar_area_x = x + 90
        bar_area_w = w - 110
        group_h = min(32, (h - 60) // max(n_groups, 1))
        single_bar_h = max(3, (group_h - 4) // n_bars_per_group)
        start_y = y + 40

        for gi, family in enumerate(all_families):
            gy = start_y + gi * (group_h + 8)
            entries = family_map[family]

            # Family label
            painter.setPen(QColor(Colors.TEXT))
            painter.setFont(QFont("monospace", 8))
            painter.drawText(x + 8, int(gy + group_h // 2 + 4), family)

            for bi, (di, r) in enumerate(entries):
                by = gy + bi * (single_bar_h + 1)
                bar_w = r.build_s / max_build * bar_area_w if max_build > 0 else 0
                bar_w *= self._anim_progress

                color = self._OVERLAY_PALETTE[di % len(self._OVERLAY_PALETTE)]
                grad = QLinearGradient(QPointF(0, 0), QPointF(bar_w, 0))
                grad.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 180))
                grad.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 100))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(grad))
                painter.drawRoundedRect(int(bar_area_x), int(by), int(bar_w), single_bar_h, 2, 2)

                # Value label on last bar in group
                if bi == len(entries) - 1:
                    painter.setPen(QColor(Colors.TEXT_DIM))
                    painter.setFont(QFont("monospace", 7))
                    painter.drawText(int(bar_area_x + bar_w + 4), int(by + single_bar_h - 1),
                                     f"{r.build_s:.1f}s")

    # --- Overlay mode: Latency comparison ---

    def _paint_latency_overlay(self, painter: QPainter, x: int, y: int,
                                w: int, h: int, datasets: list[DatasetResults]):
        self._draw_panel_bg(painter, x, y, w, h, "Query Latency — Comparison")

        all_latencies: list[tuple[int, float]] = []
        for di, ds in enumerate(datasets):
            for r in ds.results:
                all_latencies.append((di, r.latency_ms))

        if not all_latencies:
            return

        all_latencies.sort(key=lambda t: t[1])
        max_lat = max(l for _, l in all_latencies) * 1.1

        chart = ChartArea(x, y, w, h,
                          (0, len(all_latencies)),
                          (0, max_lat),
                          "Config #", "Latency (ms)",
                          ".0f", ".2f")
        chart.draw_grid(painter)

        bar_w = max(3, chart.plot_w // len(all_latencies) - 1)
        for i, (di, lat) in enumerate(all_latencies):
            sp = chart.to_screen(i, lat)
            base = chart.to_screen(i, 0)

            anim_h = (base.y() - sp.y()) * self._anim_progress
            anim_top = base.y() - anim_h

            color = self._OVERLAY_PALETTE[di % len(self._OVERLAY_PALETTE)]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            bw = max(bar_w, 3)
            painter.drawRect(int(sp.x() - bw / 2), int(anim_top), bw, int(anim_h))

    # --- Overlay mode: Comparison legend ---

    def _paint_comparison_legend(self, painter: QPainter, x: int, y: int,
                                  w: int, h: int, datasets: list[DatasetResults]):
        self._draw_panel_bg(painter, x, y, w, h, "Legend & Summary")

        start_y = y + 40
        row_h = 28
        swatch_w = 14
        swatch_h = 14

        for di, ds in enumerate(datasets):
            color = self._OVERLAY_PALETTE[di % len(self._OVERLAY_PALETTE)]
            ry = start_y + di * row_h

            # Colour swatch
            painter.setPen(QPen(color.lighter(130), 1))
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(x + 12, int(ry), swatch_w, swatch_h, 3, 3)

            # Dataset name
            painter.setPen(QColor(Colors.TEXT))
            painter.setFont(QFont("monospace", 9, QFont.Weight.Bold))
            painter.drawText(x + 32, int(ry + 12), ds.name)

            # Key stats on one line
            if ds.results:
                best_recall = max(r.recall for r in ds.results)
                best_qps = max(r.qps for r in ds.results)
                painter.setPen(QColor(Colors.TEXT_DIM))
                painter.setFont(QFont("monospace", 8))
                painter.drawText(x + 32, int(ry + 24),
                                 f"Recall {best_recall:.4f}  QPS {best_qps:,}  "
                                 f"{len(ds.results)} configs")

        # Divider line before totals
        total_y = start_y + len(datasets) * row_h + 8
        painter.setPen(QPen(QColor(255, 255, 255, 15), 0.5))
        painter.drawLine(x + 12, int(total_y), x + w - 12, int(total_y))

        # Aggregate stats
        total_y += 16
        total_configs = sum(len(ds.results) for ds in datasets)
        all_recalls = [r.recall for ds in datasets for r in ds.results]
        all_qps = [r.qps for ds in datasets for r in ds.results]
        agg_lines = [
            f"Datasets: {len(datasets)}",
            f"Total configs: {total_configs}",
            f"Best recall: {max(all_recalls):.4f}" if all_recalls else "",
            f"Best QPS: {max(all_qps):,}" if all_qps else "",
        ]
        painter.setPen(QColor(Colors.TEXT_DIM))
        painter.setFont(QFont("monospace", 8))
        for i, line in enumerate(agg_lines):
            if line:
                painter.drawText(x + 12, int(total_y + i * 18), line)

    # --- Helpers ---

    def _draw_panel_bg(self, painter: QPainter, x: int, y: int, w: int, h: int,
                       title: str, subtitle: str = ""):
        """Draw panel background with title and optional subtitle — gradient fill."""
        painter.setPen(Qt.PenStyle.NoPen)
        grad = Colors.linear_gradient(
            0, y, 0, y + h,
            (0.0, "#1a1f2b"), (1.0, "#131720"),
        )
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(x, y, w, h, 8, 8)

        # Top accent line
        painter.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        painter.drawLine(x + 8, y + 1, x + w - 8, y + 1)

        # Title
        painter.setPen(QColor(Colors.TEXT))
        painter.setFont(QFont("sans-serif", 10, QFont.Weight.Bold))
        painter.drawText(x + 12, y + 20, title)

        # Subtitle (parameters or context)
        if subtitle:
            painter.setPen(QColor(Colors.TEXT_DIM))
            painter.setFont(QFont("sans-serif", 7))
            painter.drawText(x + 12, y + 32, subtitle)

    def _paint_tooltip(self, painter: QPainter, pos: QPointF, result: BenchmarkResult):
        """Rich hover tooltip — 3 sections: metric name, values, contextual note."""
        # Compute percentile rank of this result within its dataset
        ds = self._datasets[self._current_idx]
        all_qps = sorted(r.qps for r in ds.results)
        all_recall = sorted(r.recall for r in ds.results)
        qps_rank = sum(1 for q in all_qps if q <= result.qps) / len(all_qps) * 100
        recall_rank = sum(1 for rc in all_recall if rc <= result.recall) / len(all_recall) * 100

        lines = [
            ("bold", result.name),
            ("dim", f"QPS: {result.qps:,}"),
            ("dim", f"Recall: {result.recall:.4f}"),
            ("dim", f"Build: {result.build_s:.1f}s"),
            ("dim", f"Latency: {result.latency_ms:.3f}ms"),
            ("sep", ""),  # separator
            ("note", f"QPS percentile: {qps_rank:.0f}th"),
            ("note", f"Recall percentile: {recall_rank:.0f}th"),
            ("hint", "Higher QPS & recall = better"),
        ]

        painter.setFont(QFont("monospace", 8))
        fm = painter.fontMetrics()
        max_w = max(
            fm.horizontalAdvance(l[1]) for l in lines if l[0] != "sep"
        )
        tip_w = max_w + 20
        line_h = 15
        sep_h = 6
        tip_h = sum(sep_h if l[0] == "sep" else line_h for l in lines) + 12

        tx = pos.x() + 15
        ty = pos.y() - tip_h - 5
        if tx + tip_w > self.width():
            tx = pos.x() - tip_w - 15
        if ty < 0:
            ty = pos.y() + 15

        # Background with gradient
        painter.setPen(Qt.PenStyle.NoPen)
        grad = Colors.linear_gradient(
            0, ty, 0, ty + tip_h,
            (0.0, "#1e2533"), (1.0, "#161b22"),
        )
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(int(tx), int(ty), int(tip_w), int(tip_h), 6, 6)

        # Top accent line
        painter.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        painter.drawLine(int(tx), int(ty), int(tx + tip_w), int(ty))

        # Draw lines
        cur_y = ty + 16
        for kind, text in lines:
            if kind == "sep":
                painter.setPen(QPen(QColor(255, 255, 255, 20), 0.5))
                painter.drawLine(int(tx + 6), int(cur_y), int(tx + tip_w - 6), int(cur_y))
                cur_y += sep_h
                continue
            if kind == "bold":
                painter.setPen(QColor(Colors.TEXT))
                painter.setFont(QFont("monospace", 8, QFont.Weight.Bold))
            elif kind == "note":
                painter.setPen(QColor(Colors.ACCENT_BRIGHT))
                painter.setFont(QFont("monospace", 8))
            elif kind == "hint":
                painter.setPen(QColor(Colors.TEXT_MUTED))
                painter.setFont(QFont("monospace", 7))
            else:
                painter.setPen(QColor(Colors.TEXT_DIM))
                painter.setFont(QFont("monospace", 8))
            painter.drawText(int(tx + 10), int(cur_y), text)
            cur_y += line_h

    # --- Mouse ---

    def mouseMoveEvent(self, event):
        if not self._datasets:
            return
        ds = self._datasets[self._current_idx]
        pos = event.position()
        self._hover_pos = pos

        # Check if hovering over a scatter point
        w, h = self.width(), self.height()
        margin = 16
        half_w = (w - margin * 3) // 2
        chart_x, chart_y = margin, margin
        chart_w, chart_h = half_w, (h - margin * 3) // 2

        if chart_x <= pos.x() <= chart_x + chart_w and chart_y <= pos.y() <= chart_y + chart_h:
            best, best_d = None, 15
            for r in ds.results:
                recalls = [rr.recall for rr in ds.results]
                qps_vals = [rr.qps for rr in ds.results]
                chart = ChartArea(chart_x, chart_y, chart_w, chart_h,
                                  (min(recalls) - 0.02, 1.0),
                                  (0, max(qps_vals) * 1.1))
                sp = chart.to_screen(r.recall, r.qps)
                d = math.sqrt((pos.x() - sp.x()) ** 2 + (pos.y() - sp.y()) ** 2)
                if d < best_d:
                    best_d = d
                    best = r
            if best != self._hovered_result:
                self._hovered_result = best
                self.update()
        else:
            if self._hovered_result:
                self._hovered_result = None
                self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()  # Debounce redraw


# ---------------------------------------------------------------------------
# Benchmark View — main widget
# ---------------------------------------------------------------------------

class BenchmarkView(QWidget):
    """Benchmark Dashboard with chart visualization."""

    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        tb_w, tb = build_toolbar("Benchmark Dashboard")

        # Dataset selector (added after the stretch that build_toolbar inserts)
        tb.insertWidget(tb.count() - 1, QLabel("Dataset:"))
        self.dataset_combo = QComboBox()
        self.dataset_combo.setMinimumWidth(180)
        self.dataset_combo.currentIndexChanged.connect(self._on_dataset)
        tb.insertWidget(tb.count() - 1, self.dataset_combo)

        # Load button
        load_btn = QPushButton("Load Results")
        load_btn.setIcon(icon("upload", Colors.TEXT))
        load_btn.clicked.connect(self._on_load)
        tb.insertWidget(tb.count() - 1, load_btn)

        # Comparison mode toggle
        self.compare_btn = QPushButton("Compare")
        self.compare_btn.setCheckable(True)
        self.compare_btn.setIcon(icon("layers", Colors.TEXT))
        self.compare_btn.setToolTip("Toggle comparison overlay mode — show all datasets together")
        self.compare_btn.toggled.connect(self._on_compare_toggle)
        tb.insertWidget(tb.count() - 1, self.compare_btn)

        # Export PNG button
        export_btn = QPushButton("Export PNG")
        export_btn.setIcon(icon("download", Colors.TEXT))
        export_btn.setToolTip("Save the current benchmark view as a PNG image")
        export_btn.clicked.connect(self._on_export_png)
        tb.insertWidget(tb.count() - 1, export_btn)

        layout.addWidget(tb_w)

        # Canvas
        self.canvas = BenchmarkCanvas()
        layout.addWidget(self.canvas, stretch=1)

        # Info bar
        self.info_bar = build_info_bar("Load benchmark results from SplatsDB benchmarks/ directory")
        layout.addWidget(self.info_bar)

        self.setStyleSheet(f"background-color: {Colors.BG};")

        # Auto-load default path
        default_path = "/mnt/d/splatdb/benchmarks"
        if os.path.isdir(default_path):
            self._load_from_path(default_path)

    def _load_from_path(self, path: str):
        datasets = load_benchmark_data(path)
        if datasets:
            self.canvas.load_datasets(datasets)
            self.dataset_combo.blockSignals(True)
            self.dataset_combo.clear()
            for ds in datasets:
                self.dataset_combo.addItem(f"{ds.name} ({ds.n_train:,} vecs, {ds.dim}D)")
            self.dataset_combo.blockSignals(False)
            self.info_bar.setText(
                f"Loaded {len(datasets)} datasets, "
                f"{sum(len(d.results) for d in datasets)} total configurations"
            )
        else:
            self.info_bar.setText(f"No benchmark results found in {path}")

    def _on_dataset(self, idx):
        self.canvas.set_dataset(idx)
        if 0 <= idx < len(self.canvas._datasets):
            ds = self.canvas._datasets[idx]
            self.info_bar.setText(
                f"{ds.name} · {ds.n_train:,} vectors · {ds.dim}D · "
                f"{len(ds.results)} configurations · Best recall: {max(r.recall for r in ds.results):.4f}"
            )

    def _on_load(self):
        path = QFileDialog.getExistingDirectory(self, "Select Benchmark Results Directory")
        if path:
            self._load_from_path(path)

    def _on_compare_toggle(self, checked: bool):
        """Toggle comparison overlay mode on the canvas."""
        self.canvas.set_comparison_mode(checked)
        if checked and self.canvas._datasets:
            self.info_bar.setText(
                f"Comparison mode — overlaying {len(self.canvas._datasets)} datasets"
            )
        elif self.canvas._datasets:
            self._on_dataset(self.dataset_combo.currentIndex())

    def _on_export_png(self):
        """Export the current benchmark canvas view as a PNG image."""
        default_name = "benchmark_comparison" if self.canvas.comparison_mode else "benchmark"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Benchmark View", f"{default_name}.png",
            "PNG Images (*.png);;All Files (*)",
        )
        if path:
            pixmap = self.canvas.grab()
            if pixmap.toImage().save(path, "PNG"):
                self.info_bar.setText(f"Exported benchmark view to {path}")
            else:
                self.info_bar.setText(f"Failed to export to {path}")

    def get_params(self) -> list:
        return [
            {"name": "n_queries", "label": "Queries", "type": "spin", "min": 100, "max": 100000, "default": 1000},
            {"name": "top_k", "label": "Top K", "type": "spin", "min": 1, "max": 1024, "default": 64},
        ]
