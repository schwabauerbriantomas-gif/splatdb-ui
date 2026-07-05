# SPDX-License-Identifier: GPL-3.0
"""EBM Energy Landscape — QPainter-based energy landscape visualization.

Mathematics (ported from SplatsDB Rust backend):
  Energy:        E(x) = -log(Σᵢ αᵢ · exp(-κᵢ · ||x - μᵢ||²))
  Confidence:    C(x) = 1 / (1 + E(x))
  Gradient:      ∇E(x) = Σᵢ [2κᵢαᵢexp(-κᵢd²)(x-μᵢ)] / Σᵢ [αᵢexp(-κᵢd²)]
  Free energy:   F = -log(Z), Z = Σαᵢ

  Confidence zones:
    E < 0.3 → High confidence (well-known region)
    0.3 ≤ E < 0.7 → Moderate confidence
    E ≥ 0.7 → Low confidence (uncertain / unexplored)

SOC (Self-Organized Criticality):
  Criticality index: CI = 0.6·σ²_E/(σ²_E+1) + 0.4·σ²_S/(σ²_S+1)
  States: Subcritical (CI<0.3), Critical (0.3≤CI<0.7), Supercritical (CI≥0.7)
  Avalanche: BFS cascade releasing 30% energy per cluster

Visualization layers:
  1. Energy heatmap — 2D slice of E(x) through PCA projection
  2. Isoline contours — marching squares at golden-ratio levels
  3. Gradient field — ∇E arrows showing energy ascent
  4. Splat centers — μᵢ positions with αᵢ-proportional radius
  5. Confidence zone overlays — green/yellow/red shading
  6. Avalanche cascade — animated BFS propagation
  7. Exploration regions — high-energy zones with Boltzmann weighting

Visual style: "Thermal Cartography" — deep ocean blacks for low energy,
  molten amber for high energy, green confidence islands.
"""

from __future__ import annotations

import math
import random
import numpy as np
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QCheckBox, QSizePolicy, QFrame,
)
from PySide6.QtCore import Signal, Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QRadialGradient, QLinearGradient, QPainterPath, QPolygonF,
    QImage, QPixmap,
)

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon

# ---------------------------------------------------------------------------
# EBM math engine — pure Python port of the Rust backend
# ---------------------------------------------------------------------------

class EBMEngine:
    """Energy-Based Model computation engine.

    E(x) = -log(Σᵢ αᵢ · exp(-κᵢ · ||x - μᵢ||²))
    """

    def __init__(self):
        self.mu: list[np.ndarray] = []      # centers
        self.alpha: list[float] = []         # weights
        self.kappa: list[float] = []         # concentration
        self._pca_matrix: Optional[np.ndarray] = None
        self._pca_mean: Optional[np.ndarray] = None

    def load_splats(self, nodes: list[dict]):
        """Load splat data from node list."""
        self.mu.clear()
        self.alpha.clear()
        self.kappa.clear()

        vectors = []
        for node in nodes:
            vec = node.get("vector", [])
            if len(vec) >= 2:
                vectors.append(vec)
                pos = np.array(node.get("position", vec[:3]), dtype=np.float32)
                if len(pos) < 2:
                    pos = np.array(vec[:2], dtype=np.float32)
                # Project to 2D if needed
                if len(pos) > 2:
                    pos = pos[:2]
                self.mu.append(pos)
                self.alpha.append(node.get("opacity", 0.8))
                self.kappa.append(node.get("metadata", {}).get("kappa", 1.0))

        if len(vectors) > 2:
            # PCA projection for high-dim vectors
            mat = np.array(vectors, dtype=np.float32)
            mean = mat.mean(axis=0)
            centered = mat - mean
            if centered.shape[1] >= 2:
                cov = centered.T @ centered / max(len(centered) - 1, 1)
                try:
                    eigvals, eigvecs = np.linalg.eigh(cov)
                    # Top 2 components
                    idx = np.argsort(eigvals)[::-1][:2]
                    self._pca_matrix = eigvecs[:, idx].T  # (2, D)
                    self._pca_mean = mean
                    # Re-project mu via PCA
                    self.mu = []
                    for vec in vectors:
                        projected = self._pca_matrix @ (np.array(vec, dtype=np.float32) - mean)
                        self.mu.append(projected)
                except:
                    pass

    def energy(self, x: np.ndarray) -> float:
        """E(x) = -log(Σᵢ αᵢ exp(-κᵢ ||x-μᵢ||²))"""
        total = 0.0
        for mu_i, a_i, k_i in zip(self.mu, self.alpha, self.kappa):
            d2 = float(np.sum((x - mu_i) ** 2))
            total += a_i * math.exp(-k_i * d2)
        if total < 1e-10:
            return 10.0
        return -math.log(total)

    def confidence(self, x: np.ndarray) -> float:
        """C(x) = 1 / (1 + E(x))"""
        return 1.0 / (1.0 + self.energy(x))

    def gradient(self, x: np.ndarray) -> np.ndarray:
        """∇E(x) = Σ [2κα·exp(-κd²)(x-μ)] / Σ [α·exp(-κd²)]"""
        dim = len(x)
        grad = np.zeros(dim, dtype=np.float64)
        total = 0.0
        for mu_i, a_i, k_i in zip(self.mu, self.alpha, self.kappa):
            diff = x - mu_i
            d2 = float(np.sum(diff ** 2))
            exp_term = math.exp(-k_i * d2)
            factor = 2.0 * k_i * a_i * exp_term
            grad += factor * diff
            total += a_i * exp_term
        if total > 1e-10:
            grad /= total
        return grad

    def energy_grid(self, x_range: tuple, y_range: tuple, resolution: int) -> np.ndarray:
        """Compute energy on a 2D grid."""
        xs = np.linspace(x_range[0], x_range[1], resolution)
        ys = np.linspace(y_range[0], y_range[1], resolution)
        grid = np.zeros((resolution, resolution), dtype=np.float32)
        for i, y in enumerate(ys):
            for j, x in enumerate(xs):
                grid[i, j] = self.energy(np.array([x, y]))
        return grid

    @staticmethod
    def classify(energy: float) -> tuple[str, QColor]:
        """Classify energy into confidence zone."""
        if energy < 0.3:
            return "high_confidence", QColor(34, 197, 94)   # green
        elif energy < 0.7:
            return "moderate", QColor(245, 158, 11)         # amber
        else:
            return "uncertain", QColor(239, 68, 68)          # red

    def free_energy(self) -> float:
        """F = -log(Z), Z = Σαᵢ"""
        z = sum(self.alpha)
        if z > 0:
            return -math.log(z)
        return float('inf')


# ---------------------------------------------------------------------------
# Marching squares — iso-contour extraction
# ---------------------------------------------------------------------------

def marching_squares(grid: np.ndarray, level: float,
                     x_range: tuple, y_range: tuple) -> list[list[QPointF]]:
    """Extract iso-contour paths at a given energy level using marching squares.

    Bilinear interpolation on each cell → contour segments → connected paths.
    """
    rows, cols = grid.shape
    if rows < 2 or cols < 2:
        return []

    dx = (x_range[1] - x_range[0]) / (cols - 1)
    dy = (y_range[1] - y_range[0]) / (rows - 1)

    # Collect segments
    segments = []

    for i in range(rows - 1):
        for j in range(cols - 1):
            # Corner values (BL, BR, TR, TL)
            bl = grid[i + 1, j]
            br = grid[i + 1, j + 1]
            tr = grid[i, j + 1]
            tl = grid[i, j]

            x0 = x_range[0] + j * dx
            y0 = y_range[1] - (i + 1) * dy  # flip Y (grid row 0 = top)
            x1 = x0 + dx
            y1 = y0 + dy

            # Classify corners: above or below level
            code = 0
            if tl >= level: code |= 1
            if tr >= level: code |= 2
            if br >= level: code |= 4
            if bl >= level: code |= 8

            if code == 0 or code == 15:
                continue

            # Edge interpolation points
            def lerp(a, b, va, vb):
                if abs(vb - va) < 1e-10:
                    return (a + b) / 2
                t = (level - va) / (vb - va)
                return a + t * (b - a)

            # Edges: top (tl→tr), right (tr→br), bottom (bl→br), left (tl→bl)
            pts = {}
            if code & 1:  # tl above
                pass
            if code in (1, 14):
                t = lerp(0, dx, tl, tr)
                pts['t'] = QPointF(x0 + t, y1)
                t = lerp(0, dy, tl, bl)
                pts['l'] = QPointF(x0, y1 - t)
            elif code in (2, 13):
                t = lerp(0, dx, tl, tr)
                pts['t'] = QPointF(x0 + t, y1)
                t = lerp(0, dy, tr, br)
                pts['r'] = QPointF(x1, y1 - lerp(0, dy, tr, br))
            elif code in (3, 12):
                t = lerp(0, dy, tl, bl)
                pts['l'] = QPointF(x0, y1 - t)
                pts['r'] = QPointF(x1, y1 - lerp(0, dy, tr, br))
            elif code in (4, 11):
                pts['r'] = QPointF(x1, y1 - lerp(0, dy, tr, br))
                pts['b'] = QPointF(x0 + lerp(0, dx, bl, br), y0)
            elif code in (6, 9):
                pts['t'] = QPointF(x0 + lerp(0, dx, tl, tr), y1)
                pts['b'] = QPointF(x0 + lerp(0, dx, bl, br), y0)
            elif code in (7, 8):
                pts['b'] = QPointF(x0 + lerp(0, dx, bl, br), y0)
                pts['l'] = QPointF(x0, y1 - lerp(0, dy, tl, bl))
            elif code == 5:
                pts['t'] = QPointF(x0 + lerp(0, dx, tl, tr), y1)
                pts['r'] = QPointF(x1, y1 - lerp(0, dy, tr, br))
                pts['b'] = QPointF(x0 + lerp(0, dx, bl, br), y0)
                pts['l'] = QPointF(x0, y1 - lerp(0, dy, tl, bl))
            elif code == 10:
                pts['t'] = QPointF(x0 + lerp(0, dx, tl, tr), y1)
                pts['r'] = QPointF(x1, y1 - lerp(0, dy, tr, br))
                pts['b'] = QPointF(x0 + lerp(0, dx, bl, br), y0)
                pts['l'] = QPointF(x0, y1 - lerp(0, dy, tl, bl))

            # Extract segment pairs from the lookup
            seg_pairs = {
                1: [('t', 'l')], 2: [('t', 'r')], 3: [('l', 'r')],
                4: [('r', 'b')], 5: [('t', 'l'), ('r', 'b')],
                6: [('t', 'b')], 7: [('b', 'l')], 8: [('b', 'l')],
                9: [('t', 'b')], 10: [('t', 'r'), ('b', 'l')],
                11: [('r', 'b')], 12: [('l', 'r')], 13: [('t', 'l')],
                14: [('t', 'r')]
            }
            for e1, e2 in seg_pairs.get(code, []):
                if e1 in pts and e2 in pts:
                    segments.append((pts[e1], pts[e2]))

    # Simple path assembly — group connected segments
    return _assemble_paths(segments)


def _assemble_paths(segments: list) -> list[list[QPointF]]:
    """Greedy assembly of segments into continuous paths."""
    if not segments:
        return []

    paths = []
    remaining = list(segments)

    while remaining:
        path = [remaining[0][0], remaining[0][1]]
        remaining.pop(0)
        changed = True
        while changed and remaining:
            changed = False
            head = path[-1]
            for k, (a, b) in enumerate(remaining):
                if _pt_dist(head, a) < 2.0:
                    path.append(b)
                    remaining.pop(k)
                    changed = True
                    break
                elif _pt_dist(head, b) < 2.0:
                    path.append(a)
                    remaining.pop(k)
                    changed = True
                    break
        if len(path) >= 2:
            paths.append(path)

    return paths


def _pt_dist(a: QPointF, b: QPointF) -> float:
    dx = a.x() - b.x()
    dy = a.y() - b.y()
    return math.sqrt(dx * dx + dy * dy)


# ---------------------------------------------------------------------------
# EBM Canvas — main rendering widget
# ---------------------------------------------------------------------------

PHI = (1 + math.sqrt(5)) / 2

class EBMCanvas(QWidget):
    """Energy landscape canvas — thermal cartography rendering."""

    node_clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(600, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self._engine = EBMEngine()
        self._nodes: list[dict] = []
        self._energy_grid: Optional[np.ndarray] = None
        self._grid_x_range = (-15, 15)
        self._grid_y_range = (-15, 15)
        self._grid_resolution = 80
        self._heatmap_cache: Optional[QImage] = None

        self._show_gradient = True
        self._show_contours = True
        self._show_splats = True
        self._show_zones = True
        self._show_exploration = True
        self._contour_count = 8

        self._hovered_idx = -1
        self._selected_idx = -1
        self._drag_start = None
        self._pan_offset = QPointF(0, 0)
        self._zoom = 1.0

        # Avalanche animation
        self._avalanche_active = False
        self._avalanche_path: list[int] = []
        self._avalanche_step = 0
        self._avalanche_energy = 0.0

        # Animation
        self._time = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

        # Deterministic star field
        self._stars = [(random.Random(42 + i).random(), random.Random(42 + i + 100).random(),
                        random.Random(42 + i + 200).randint(8, 25)) for i in range(60)]

    def load_nodes(self, nodes: list[dict]):
        self._nodes = nodes
        self._engine.load_splats(nodes)

        if self._engine.mu:
            mu_arr = np.array(self._engine.mu)
            x_min, x_max = mu_arr[:, 0].min() - 3, mu_arr[:, 0].max() + 3
            y_min, y_max = mu_arr[:, 1].min() - 3, mu_arr[:, 1].max() + 3
            span = max(x_max - x_min, y_max - y_min)
            cx, cy = (x_max + x_min) / 2, (y_max + y_min) / 2
            self._grid_x_range = (cx - span / 2, cx + span / 2)
            self._grid_y_range = (cy - span / 2, cy + span / 2)
        else:
            self._grid_x_range = (-15, 15)
            self._grid_y_range = (-15, 15)

        self._recompute_grid()

    def _recompute_grid(self):
        self._energy_grid = self._engine.energy_grid(
            self._grid_x_range, self._grid_y_range, self._grid_resolution)
        self._heatmap_cache = None

    # --- Settings ---

    def set_show_gradient(self, on: bool): self._show_gradient = on; self.update()
    def set_show_contours(self, on: bool): self._show_contours = on; self.update()
    def set_show_splats(self, on: bool): self._show_splats = on; self.update()
    def set_show_zones(self, on: bool): self._show_zones = on; self.update()
    def set_show_exploration(self, on: bool): self._show_exploration = on; self.update()

    def set_contour_count(self, n: int):
        self._contour_count = n
        self._heatmap_cache = None
        self.update()

    def trigger_avalanche(self):
        """Trigger animated avalanche cascade."""
        if not self._engine.mu:
            return
        # Find highest energy center
        max_e, max_i = -1, 0
        for i, mu in enumerate(self._engine.mu):
            e = self._engine.energy(mu)
            if e > max_e:
                max_e, max_i = e, i

        # BFS cascade
        visited = {max_i}
        queue = [max_i]
        path = [max_i]
        while queue:
            idx = queue.pop(0)
            # Find nearest neighbors
            dists = [(j, float(np.sum((self._engine.mu[idx] - self._engine.mu[j]) ** 2)))
                     for j in range(len(self._engine.mu)) if j not in visited]
            dists.sort(key=lambda x: x[1])
            for j, d in dists[:3]:
                if self._engine.energy(self._engine.mu[j]) > 0.3:
                    visited.add(j)
                    queue.append(j)
                    path.append(j)
                if len(path) > 30:
                    break
            if len(path) > 30:
                break

        self._avalanche_path = path
        self._avalanche_step = 0
        self._avalanche_active = True
        self._avalanche_energy = max_e

    def relax_system(self):
        """Relax energy landscape — distribute alpha more uniformly."""
        if not self._engine.alpha:
            return
        for _ in range(5):
            total = sum(self._engine.alpha)
            if total > 0:
                for i in range(len(self._engine.alpha)):
                    # Decrease high-kappa splats' contribution (true relaxation)
                    self._engine.alpha[i] *= 1.0 - self._engine.kappa[i] * 0.01
                total = sum(self._engine.alpha)
                if total > 0:
                    for i in range(len(self._engine.alpha)):
                        self._engine.alpha[i] /= total
        self._recompute_grid()
        self.update()

    # --- Animation ---

    def _tick(self):
        self._time += 0.033
        if self._avalanche_active:
            self._avalanche_step += 1
            if self._avalanche_step >= len(self._avalanche_path) * 4:
                self._avalanche_active = False
        self.update()

    # --- Coordinate transforms ---

    def _world_to_screen(self, wx: float, wy: float) -> QPointF:
        w, h = self.width(), self.height()
        xr, yr = self._grid_x_range, self._grid_y_range
        sx = (wx - xr[0]) / (xr[1] - xr[0]) * w
        sy = (1 - (wy - yr[0]) / (yr[1] - yr[0])) * h
        return QPointF(sx, sy)

    def _screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        w, h = self.width(), self.height()
        xr, yr = self._grid_x_range, self._grid_y_range
        wx = sx / w * (xr[1] - xr[0]) + xr[0]
        wy = (1 - sy / h) * (yr[1] - yr[0]) + yr[0]
        return wx, wy

    # --- Rendering ---

    def paintEvent(self, event):
        if not self._nodes:
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(Colors.BG))
            painter.setPen(QColor(Colors.TEXT_DIM))
            painter.setFont(QFont("sans-serif", 13))
            painter.drawText(self.rect(), Qt.AlignCenter, "Load data to visualize energy landscape")
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # 1. Energy heatmap
        self._paint_heatmap(painter, w, h)

        # 2. Confidence zone overlays
        if self._show_zones:
            self._paint_zones(painter, w, h)

        # 3. Isoline contours
        if self._show_contours:
            self._paint_contours(painter, w, h)

        # 4. Gradient field
        if self._show_gradient:
            self._paint_gradient_field(painter, w, h)

        # 5. Exploration regions
        if self._show_exploration:
            self._paint_exploration(painter, w, h)

        # 6. Splat centers
        if self._show_splats:
            self._paint_splats(painter, w, h)

        # 7. Avalanche animation
        if self._avalanche_active:
            self._paint_avalanche(painter, w, h)

        # 8. Hover info
        if self._hovered_idx >= 0:
            self._paint_hover_info(painter, w, h)

        # 9. Legend + info
        self._paint_legend(painter, w, h)

        painter.end()

    def _energy_to_color(self, e: float) -> QColor:
        """Map energy value to thermal color.

        0.0 → deep blue (low energy = high confidence)
        0.3 → teal green
        0.7 → amber/orange
        1.0+ → deep red/crimson
        """
        t = min(e / 2.0, 1.0)  # normalize to [0,1]

        if t < 0.15:
            # Deep blue → dark teal
            r = int(10 + t / 0.15 * 20)
            g = int(20 + t / 0.15 * 60)
            b = int(80 + t / 0.15 * 40)
        elif t < 0.35:
            # Teal → green
            s = (t - 0.15) / 0.2
            r = int(30 - s * 10)
            g = int(80 + s * 80)
            b = int(120 - s * 70)
        elif t < 0.55:
            # Green → amber
            s = (t - 0.35) / 0.2
            r = int(20 + s * 180)
            g = int(160 + s * 20)
            b = int(50 - s * 30)
        elif t < 0.75:
            # Amber → orange
            s = (t - 0.55) / 0.2
            r = int(200 + s * 40)
            g = int(180 - s * 80)
            b = int(20)
        else:
            # Orange → crimson
            s = (t - 0.75) / 0.25
            r = int(240 - s * 20)
            g = int(100 - s * 70)
            b = int(20 + s * 20)

        return QColor(
            max(0, min(255, r)),
            max(0, min(255, g)),
            max(0, min(255, b)),
        )

    def _paint_heatmap(self, painter: QPainter, w: int, h: int):
        """Render energy field as thermal heatmap."""
        if self._heatmap_cache and self._heatmap_cache.size() == self.size():
            painter.drawImage(0, 0, self._heatmap_cache)
            return

        grid = self._energy_grid
        if grid is None:
            return

        res = grid.shape[0]
        img = QImage(res, res, QImage.Format_ARGB32_Premultiplied)

        e_min = float(grid.min())
        e_max = float(grid.max())
        if e_max - e_min < 1e-6:
            e_max = e_min + 1.0

        for i in range(res):
            for j in range(res):
                color = self._energy_to_color(grid[i, j])
                img.setPixelColor(j, i, color)

        # Scale to widget size
        scaled = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._heatmap_cache = scaled
        painter.drawImage(0, 0, scaled)

    def _paint_zones(self, painter: QPainter, w: int, h: int):
        """Paint confidence zone boundaries."""
        grid = self._energy_grid
        if grid is None:
            return

        # Draw zone boundaries at E=0.3 and E=0.7
        for level, color, label in [
            (0.3, QColor(34, 197, 94, 120), "High confidence"),
            (0.7, QColor(239, 68, 68, 120), "Low confidence"),
        ]:
            paths = marching_squares(grid, level, self._grid_x_range, self._grid_y_range)
            for path_pts in paths:
                if len(path_pts) < 2:
                    continue
                screen_pts = [self._world_to_screen(p.x(), p.y()) for p in path_pts]
                poly = QPolygonF(screen_pts)
                pen = QPen(color, 2.0, Qt.DashDotLine)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPolyline(poly)

    def _paint_contours(self, painter: QPainter, w: int, h: int):
        """Golden-ratio iso-contour lines."""
        grid = self._energy_grid
        if grid is None:
            return

        e_min = float(grid.min())
        e_max = float(grid.max())
        if e_max - e_min < 0.01:
            return

        # Golden-ratio contour spacing
        n = self._contour_count
        for k in range(n):
            t = (k + 1) / (n + 1)
            level = e_min + t * (e_max - e_min)

            # Contour opacity fades with index
            alpha = int(180 * (1.0 - 0.4 * k / n))
            pen_color = QColor(255, 255, 255, alpha)
            painter.setPen(QPen(pen_color, 1.2))
            painter.setBrush(Qt.NoBrush)

            paths = marching_squares(grid, level, self._grid_x_range, self._grid_y_range)
            for path_pts in paths:
                if len(path_pts) < 2:
                    continue
                screen_pts = [self._world_to_screen(p.x(), p.y()) for p in path_pts]
                painter.drawPolyline(QPolygonF(screen_pts))

    def _paint_gradient_field(self, painter: QPainter, w: int, h: int):
        """Draw energy gradient arrows ∇E(x)."""
        if not self._engine.mu:
            return

        xr, yr = self._grid_x_range, self._grid_y_range
        spacing = 8  # arrows per axis
        xs = np.linspace(xr[0] + 0.5, xr[1] - 0.5, spacing)
        ys = np.linspace(yr[0] + 0.5, yr[1] - 0.5, spacing)

        for y in ys:
            for x in xs:
                pt = np.array([x, y])
                e = self._engine.energy(pt)
                grad = self._engine.gradient(pt)

                # Arrow from gradient
                mag = float(np.linalg.norm(grad))
                if mag < 0.01:
                    continue

                # Normalize and scale arrow
                direction = grad / mag
                arrow_len = min(mag * 15, 25)
                end = pt + direction * arrow_len * 0.1

                sp = self._world_to_screen(x, y)
                ep = self._world_to_screen(float(end[0]), float(end[1]))

                # Color by energy
                _, color = EBMEngine.classify(e)
                color.setAlpha(int(40 + min(e * 60, 160)))

                painter.setPen(QPen(color, 1.0))
                painter.drawLine(sp, ep)

                # Arrowhead
                dx = ep.x() - sp.x()
                dy = ep.y() - sp.y()
                length = math.sqrt(dx * dx + dy * dy)
                if length > 3:
                    ux, uy = dx / length, dy / length
                    # Small arrowhead
                    head_len = 3
                    px, py = -uy, ux  # perpendicular
                    tip = ep
                    left = QPointF(tip.x() - ux * head_len + px * head_len * 0.5,
                                   tip.y() - uy * head_len + py * head_len * 0.5)
                    right = QPointF(tip.x() - ux * head_len - px * head_len * 0.5,
                                    tip.y() - uy * head_len - py * head_len * 0.5)
                    painter.drawPolyline(QPolygonF([left, tip, right]))

    def _paint_exploration(self, painter: QPainter, w: int, h: int):
        """Highlight high-energy (uncertain) regions as pulsing circles."""
        if not self._engine.mu:
            return

        # Find high energy points
        high_e_points = []
        for i, mu in enumerate(self._engine.mu):
            e = self._engine.energy(mu)
            if e >= 0.5:
                high_e_points.append((mu, e))

        # Also sample grid for high-energy zones
        if self._energy_grid is not None:
            res = self._energy_grid.shape[0]
            for i in range(0, res, 4):
                for j in range(0, res, 4):
                    if self._energy_grid[i, j] > 0.8:
                        x = self._grid_x_range[0] + j / res * (self._grid_x_range[1] - self._grid_x_range[0])
                        y = self._grid_y_range[0] + i / res * (self._grid_y_range[1] - self._grid_y_range[0])
                        high_e_points.append((np.array([x, y]), self._energy_grid[i, j]))

        for mu, e in high_e_points:
            sp = self._world_to_screen(float(mu[0]), float(mu[1]))
            pulse = 8 + 6 * math.sin(self._time * 2.0 + e * 5)
            radius = pulse + e * 8

            # Pulsing glow
            glow = QRadialGradient(QPointF(0, 0), radius)
            rc = QColor(239, 68, 68)
            glow.setColorAt(0.0, QColor(rc.red(), rc.green(), rc.blue(), int(60 * min(e, 1))))
            glow.setColorAt(0.5, QColor(rc.red(), rc.green(), rc.blue(), int(20 * min(e, 1))))
            glow.setColorAt(1.0, QColor(rc.red(), rc.green(), rc.blue(), 0))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow))
            painter.save()
            painter.translate(sp)
            painter.drawEllipse(QPointF(0, 0), radius, radius)
            painter.restore()

            # Dashed circle
            painter.setPen(QPen(QColor(239, 68, 68, int(80 * min(e, 1))), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.save()
            painter.translate(sp)
            painter.drawEllipse(QPointF(0, 0), radius * 1.3, radius * 1.3)
            painter.restore()

    def _paint_splats(self, painter: QPainter, w: int, h: int):
        """Draw splat centers μᵢ with αᵢ-proportional radius and confidence coloring."""
        for i, mu in enumerate(self._engine.mu):
            if i >= len(self._engine.alpha):
                break

            sp = self._world_to_screen(float(mu[0]), float(mu[1]))
            alpha = self._engine.alpha[i]
            e = self._engine.energy(mu)
            zone, color = EBMEngine.classify(e)

            # Radius proportional to alpha
            base_r = 6 + alpha * 14

            # Hover/selection
            is_hover = i == self._hovered_idx
            is_sel = i == self._selected_idx
            if is_hover or is_sel:
                base_r *= 1.3
                color = color.lighter(140)

            # Glow
            glow = QRadialGradient(QPointF(0, 0), base_r * 2.5)
            gc = QColor(color)
            glow.setColorAt(0.0, QColor(gc.red(), gc.green(), gc.blue(), 80))
            glow.setColorAt(0.5, QColor(gc.red(), gc.green(), gc.blue(), 20))
            glow.setColorAt(1.0, QColor(gc.red(), gc.green(), gc.blue(), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow))
            painter.save()
            painter.translate(sp)
            painter.drawEllipse(QPointF(0, 0), base_r * 2.5, base_r * 2.5)
            painter.restore()

            # Core
            core = QRadialGradient(QPointF(0, 0), base_r)
            ci = QColor(color).lighter(150)
            ci.setAlpha(230)
            mid = QColor(color).lighter(110)
            mid.setAlpha(180)
            edge = QColor(color).darker(130)
            edge.setAlpha(120)
            outer = QColor(color).darker(180)
            outer.setAlpha(0)
            core.setColorAt(0.0, ci)
            core.setColorAt(0.4, mid)
            core.setColorAt(0.75, edge)
            core.setColorAt(1.0, outer)

            painter.setBrush(QBrush(core))
            painter.setPen(QPen(QColor(color).lighter(160), 1.5 if is_sel else 0.8))
            painter.save()
            painter.translate(sp)
            painter.drawEllipse(QPointF(0, 0), base_r, base_r)
            painter.restore()

            # Selection ring
            if is_sel:
                painter.setPen(QPen(QColor(Colors.ACCENT), 2.5, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.save()
                painter.translate(sp)
                painter.drawEllipse(QPointF(0, 0), base_r * 1.5, base_r * 1.5)
                painter.restore()

            # Label
            if is_hover or is_sel:
                meta = self._nodes[i].get("metadata", {}) if i < len(self._nodes) else {}
                label = meta.get("label", f"Splat {i}")
                font = QFont("monospace", 9, QFont.Medium)
                painter.setFont(font)
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(label)
                lx = sp.x() - tw / 2
                ly = sp.y() + base_r + 14

                bg = QColor(Colors.BG_RAISED)
                bg.setAlpha(210)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(bg))
                painter.drawRoundedRect(int(lx - 4), int(ly - fm.height() + 2),
                                        tw + 8, fm.height() + 4, 4, 4)

                painter.setPen(QPen(QColor(Colors.TEXT)))
                painter.drawText(int(lx), int(ly + 2), label)
                # Energy value
                e_text = f"E={e:.3f} C={1/(1+e):.3f}"
                painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
                painter.setFont(QFont("monospace", 8))
                painter.drawText(int(lx), int(ly + 16), e_text)

    def _paint_avalanche(self, painter: QPainter, w: int, h: int):
        """Animated avalanche cascade."""
        step = self._avalanche_step
        visible = min(step // 3, len(self._avalanche_path))

        for k in range(visible):
            idx = self._avalanche_path[k]
            if idx >= len(self._engine.mu):
                continue

            mu = self._engine.mu[idx]
            sp = self._world_to_screen(float(mu[0]), float(mu[1]))

            # Expanding shockwave ring
            age = step - k * 3
            radius = 5 + age * 2.5
            fade = max(0, 1.0 - age / 40.0)

            ring_alpha = int(200 * fade)
            ring_color = QColor(245, 158, 11, ring_alpha)
            painter.setPen(QPen(ring_color, 2.5 * fade))
            painter.setBrush(Qt.NoBrush)
            painter.save()
            painter.translate(sp)
            painter.drawEllipse(QPointF(0, 0), radius, radius)
            painter.restore()

            # Inner flash
            if age < 10:
                flash_r = 8 + age * 1.5
                flash = QRadialGradient(QPointF(0, 0), flash_r)
                fc = QColor(255, 200, 50)
                flash.setColorAt(0.0, QColor(fc.red(), fc.green(), fc.blue(), int(180 * (1 - age / 10))))
                flash.setColorAt(1.0, QColor(fc.red(), fc.green(), fc.blue(), 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(flash))
                painter.save()
                painter.translate(sp)
                painter.drawEllipse(QPointF(0, 0), flash_r, flash_r)
                painter.restore()

        # Connection lines between cascade steps
        for k in range(1, visible):
            i = self._avalanche_path[k - 1]
            j = self._avalanche_path[k]
            if i >= len(self._engine.mu) or j >= len(self._engine.mu):
                continue
            sp1 = self._world_to_screen(float(self._engine.mu[i][0]), float(self._engine.mu[i][1]))
            sp2 = self._world_to_screen(float(self._engine.mu[j][0]), float(self._engine.mu[j][1]))

            age = step - k * 3
            fade = max(0, 1.0 - age / 30.0)
            painter.setPen(QPen(QColor(245, 158, 11, int(150 * fade)), 2.0 * fade))
            painter.drawLine(sp1, sp2)

    def _paint_hover_info(self, painter: QPainter, w: int, h: int):
        """Show energy at hover position."""
        if self._hovered_idx < 0:
            return
        mu = self._engine.mu[self._hovered_idx]
        e = self._engine.energy(mu)
        c = 1 / (1 + e)
        zone_name, _ = EBMEngine.classify(e)

        painter.setPen(Qt.NoPen)
        bg = QColor(Colors.BG_RAISED)
        bg.setAlpha(200)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(w - 220, h - 90, 210, 80, 6, 6)

        painter.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        painter.drawLine(w - 220, h - 90, w - 10, h - 90)

        painter.setFont(QFont("monospace", 9))
        painter.setPen(QColor(Colors.TEXT))
        painter.drawText(w - 212, h - 72, f"E(x) = {e:.4f}")
        painter.drawText(w - 212, h - 57, f"C(x) = {c:.4f}")
        painter.drawText(w - 212, h - 42, f"Zone: {zone_name}")
        painter.setPen(QColor(Colors.TEXT_DIM))
        painter.drawText(w - 212, h - 27, f"Free energy F = {self._engine.free_energy():.4f}")

    def _paint_legend(self, painter: QPainter, w: int, h: int):
        """Thermal legend + system info."""
        # Legend bar (left side)
        bar_x, bar_y = 12, h - 28 - 140
        bar_w, bar_h = 18, 140

        painter.setPen(Qt.NoPen)
        bg = QColor(Colors.BG_RAISED)
        bg.setAlpha(190)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(bar_x - 4, bar_y - 20, bar_w + 70, bar_h + 35, 6, 6)

        painter.setFont(QFont("monospace", 7))
        painter.setPen(QColor(Colors.TEXT_DIM))
        painter.drawText(bar_x, bar_y - 6, "E(x)")

        for i in range(bar_h):
            e = i / bar_h * 2.0  # 0 to 2.0
            color = self._energy_to_color(e)
            painter.setPen(QPen(color))
            painter.drawLine(bar_x, bar_y + i, bar_x + bar_w, bar_y + i)

        painter.setPen(QColor(0, 0, 0))
        painter.drawRect(bar_x, bar_y, bar_w, bar_h)

        painter.setPen(QColor(Colors.TEXT_DIM))
        painter.drawText(bar_x + bar_w + 4, bar_y + 8, "0.0")
        painter.drawText(bar_x + bar_w + 4, bar_y + bar_h // 2 + 4, "1.0")
        painter.drawText(bar_x + bar_w + 4, bar_y + bar_h, "2.0+")

        # Zone indicators
        zone_y = bar_y + bar_h + 22
        for color, label in [
            (QColor(34, 197, 94), "High conf"),
            (QColor(245, 158, 11), "Moderate"),
            (QColor(239, 68, 68), "Uncertain"),
        ]:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(bar_x + 4, zone_y), 4, 4)
            painter.setPen(QColor(Colors.TEXT_DIM))
            painter.drawText(bar_x + 12, int(zone_y + 4), label)
            zone_y += 14

        # System info (top-right)
        n_splats = len(self._engine.mu)
        fe = self._engine.free_energy()

        painter.setPen(Qt.NoPen)
        bg2 = QColor(Colors.BG_RAISED)
        bg2.setAlpha(190)
        painter.setBrush(QBrush(bg2))
        painter.drawRoundedRect(w - 195, 8, 185, 65, 6, 6)

        painter.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        painter.drawLine(w - 195, 8, w - 10, 8)

        painter.setFont(QFont("monospace", 7))
        painter.setPen(QColor(Colors.TEXT))
        painter.drawText(w - 187, 22, "EBM ENERGY LANDSCAPE")
        painter.setPen(QColor(Colors.TEXT_DIM))
        painter.drawText(w - 187, 35, f"Splats: {n_splats}  Free E: {fe:.3f}")
        painter.drawText(w - 187, 48, "E(x) = -ln(Σ α·exp(-κ||x-μ||²))")
        painter.drawText(w - 187, 61, "C(x) = 1/(1+E(x))")

    # --- Mouse ---

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.position()
        elif event.button() == Qt.RightButton:
            self._select_at(event.position())

    def mouseDoubleClickEvent(self, event):
        self._select_at(event.position())

    def mouseMoveEvent(self, event):
        pos = event.position()
        self._hover_at(pos)

    def mouseReleaseEvent(self, event):
        self._drag_start = None

    def _hover_at(self, pos):
        best, best_d = -1, 30
        for i, mu in enumerate(self._engine.mu):
            sp = self._world_to_screen(float(mu[0]), float(mu[1]))
            d = math.sqrt((pos.x() - sp.x()) ** 2 + (pos.y() - sp.y()) ** 2)
            if d < best_d:
                best_d = d
                best = i
        if best != self._hovered_idx:
            self._hovered_idx = best
            self.setCursor(Qt.PointingHandCursor if best >= 0 else Qt.ArrowCursor)

    def _select_at(self, pos):
        best, best_d = -1, 40
        for i, mu in enumerate(self._engine.mu):
            sp = self._world_to_screen(float(mu[0]), float(mu[1]))
            d = math.sqrt((pos.x() - sp.x()) ** 2 + (pos.y() - sp.y()) ** 2)
            if d < best_d:
                best_d = d
                best = i
        if best >= 0:
            self._selected_idx = best
            if best < len(self._nodes):
                nid = self._nodes[best].get("id", "")
                self.node_clicked.emit(nid)


# ---------------------------------------------------------------------------
# EBM View — main widget with toolbar
# ---------------------------------------------------------------------------

class EBMView(QWidget):
    """EBM Energy Landscape visualization."""

    node_selected = Signal(str)
    node_hovered = Signal(str)

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
        tb = QHBoxLayout()
        tb.setContentsMargins(12, 8, 12, 8)
        tb.setSpacing(10)

        title = QLabel("EBM Energy Landscape")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 14px; font-weight: 700;")
        tb.addWidget(title)

        sub = QLabel("E(x) = -ln(Σ α·exp(-κ||x-μ||²))")
        sub.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px; font-family: monospace;")
        tb.addWidget(sub)

        tb.addStretch()

        # Contour count
        tb.addWidget(QLabel("Contours:"))
        self.contour_slider = QSlider(Qt.Horizontal)
        self.contour_slider.setRange(2, 16)
        self.contour_slider.setValue(8)
        self.contour_slider.setFixedWidth(80)
        self.contour_slider.valueChanged.connect(self._on_contours)
        tb.addWidget(self.contour_slider)

        # Toggles
        self.grad_cb = QCheckBox("∇E")
        self.grad_cb.setChecked(True)
        self.grad_cb.toggled.connect(lambda v: self.canvas.set_show_gradient(v))
        tb.addWidget(self.grad_cb)

        self.contour_cb = QCheckBox("Contours")
        self.contour_cb.setChecked(True)
        self.contour_cb.toggled.connect(lambda v: self.canvas.set_show_contours(v))
        tb.addWidget(self.contour_cb)

        self.splat_cb = QCheckBox("Splats")
        self.splat_cb.setChecked(True)
        self.splat_cb.toggled.connect(lambda v: self.canvas.set_show_splats(v))
        tb.addWidget(self.splat_cb)

        self.zone_cb = QCheckBox("Zones")
        self.zone_cb.setChecked(True)
        self.zone_cb.toggled.connect(lambda v: self.canvas.set_show_zones(v))
        tb.addWidget(self.zone_cb)

        self.explore_cb = QCheckBox("Explore")
        self.explore_cb.setChecked(True)
        self.explore_cb.toggled.connect(lambda v: self.canvas.set_show_exploration(v))
        tb.addWidget(self.explore_cb)

        # Actions
        avalanche_btn = QPushButton("⚡ Avalanche")
        avalanche_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_OVERLAY}; color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT}; border-radius: 4px;
                padding: 4px 10px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Colors.ACCENT}; color: {Colors.BG}; }}
        """)
        avalanche_btn.clicked.connect(self._on_avalanche)
        tb.addWidget(avalanche_btn)

        relax_btn = QPushButton("Relax")
        relax_btn.clicked.connect(self._on_relax)
        tb.addWidget(relax_btn)

        tb_w = QWidget()
        tb_w.setLayout(tb)
        tb_w.setStyleSheet(
            f"background-color: {Colors.BG_RAISED}; border-bottom: 1px solid {Colors.BORDER};"
            + f"QCheckBox {{ color: {Colors.TEXT}; font-size: 11px; }}"
            + f"QLabel {{ color: {Colors.TEXT_DIM}; font-size: 11px; }}"
            + f"QPushButton {{ background: {Colors.BG_OVERLAY}; color: {Colors.TEXT}; border: 1px solid {Colors.BORDER}; border-radius: 4px; padding: 4px 10px; }}"
            + f"QPushButton:hover {{ background: {Colors.BG_HOVER}; }}"
        )
        layout.addWidget(tb_w)

        # Canvas
        self.canvas = EBMCanvas()
        self.canvas.node_clicked.connect(self._on_select)
        layout.addWidget(self.canvas, stretch=1)

        # Info bar
        self.info_bar = QLabel("Hover splats to inspect · Double-click to select · ⚡ Avalanche to cascade")
        self.info_bar.setStyleSheet(f"""
            color: {Colors.TEXT_DIM}; font-size: 11px; padding: 6px 12px;
            background-color: {Colors.BG_RAISED}; border-top: 1px solid {Colors.BORDER};
        """)
        layout.addWidget(self.info_bar)

        self.setStyleSheet(f"background-color: {Colors.BG};")

    def load_nodes(self, nodes: list[dict]):
        self.canvas.load_nodes(nodes)
        n = len(nodes)
        self.info_bar.setText(
            f"{n} splats · Free energy F={self.canvas._engine.free_energy():.3f} · "
            f"Hover to inspect · ⚡ Avalanche to cascade"
        )

    def select_node(self, node_id: str):
        pass

    def _on_select(self, node_id: str):
        self.node_selected.emit(node_id)

    def _on_contours(self, val):
        self.canvas.set_contour_count(val)

    def _on_avalanche(self):
        self.canvas.trigger_avalanche()
        self.info_bar.setText("⚡ Avalanche cascade triggered!")

    def _on_relax(self):
        self.canvas.relax_system()
        fe = self.canvas._engine.free_energy()
        self.info_bar.setText(f"System relaxed · Free energy F={fe:.3f}")
