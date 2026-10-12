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
    QFileDialog,
)
from PySide6.QtCore import Signal, Qt, QTimer, QPointF, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QRadialGradient, QLinearGradient, QPainterPath, QPolygonF,
    QImage, QPixmap, QCursor,
)

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon
from splatsdb_ui.utils.widgets import build_toolbar, build_info_bar, make_button

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
        """Compute energy on a 2D grid using vectorized numpy broadcasting.

        Instead of a Python double for-loop calling self.energy() per point,
        we build the full grid of (x, y) coordinates and compute all distances
        and energies in one batch using numpy broadcasting.
        """
        if not self.mu:
            return np.zeros((resolution, resolution), dtype=np.float32)

        xs = np.linspace(x_range[0], x_range[1], resolution, dtype=np.float64)
        ys = np.linspace(y_range[0], y_range[1], resolution, dtype=np.float64)

        # Build (resolution, resolution, 2) grid of world coordinates
        # grid_yx[i, j] = [xs[j], ys[i]]  (matches old loop order: i=y-row, j=x-col)
        xx, yy = np.meshgrid(xs, ys)  # each shape (resolution, resolution)
        grid_points = np.stack([xx, yy], axis=-1)  # (R, R, 2)

        # Convert splat parameters to arrays
        mu_arr = np.array(self.mu, dtype=np.float64)   # (N, 2)
        alpha_arr = np.array(self.alpha, dtype=np.float64)  # (N,)
        kappa_arr = np.array(self.kappa, dtype=np.float64)  # (N,)

        # Compute squared distances: ||x - mu_i||^2
        # grid_points: (R, R, 2) -> (R, R, 1, 2)
        # mu_arr:      (N, 2)    -> (1, 1, N, 2)
        diff = grid_points[:, :, np.newaxis, :] - mu_arr[np.newaxis, np.newaxis, :, :]  # (R, R, N, 2)
        d2 = np.sum(diff ** 2, axis=-1)  # (R, R, N)

        # Energy computation: alpha_i * exp(-kappa_i * d2_i)
        exp_terms = alpha_arr[np.newaxis, np.newaxis, :] * np.exp(-kappa_arr[np.newaxis, np.newaxis, :] * d2)  # (R, R, N)
        total = np.sum(exp_terms, axis=-1)  # (R, R)

        # E(x) = -log(total), clamp to 10.0 where total is tiny
        grid = np.where(total < 1e-10, 10.0, -np.log(np.maximum(total, 1e-300)))
        return grid.astype(np.float32)

    @staticmethod
    def classify(energy: float) -> tuple[str, QColor]:
        """Classify energy into confidence zone."""
        if energy < 0.3:
            return "high_confidence", QColor(Colors.CONFIDENCE_HIGH)
        elif energy < 0.7:
            return "moderate", QColor(Colors.CONFIDENCE_MOD)
        else:
            return "uncertain", QColor(Colors.CONFIDENCE_LOW)

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
        self._cache_size: Optional[tuple[int, int]] = None
        self._pixmap_cache: Optional[QPixmap] = None
        self._pixmap_cache_key: Optional[tuple] = None

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
        self._target_zoom = 1.0

        # Hover position for energy tooltip (screen coords)
        self._hover_screen_pos: Optional[QPointF] = None
        self._crosshair_pos: Optional[QPointF] = None
        self._show_crosshair = True

        # Smooth color transition — blend factor between old and new heatmap
        self._transition_alpha = 1.0  # 1.0 = fully showing new
        self._prev_heatmap: Optional[QImage] = None

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

        # Deterministic star field with twinkling parameters
        # Each star: (x_frac, y_frac, base_size, twinkle_speed, twinkle_phase, base_brightness)
        self._stars = []
        for i in range(80):
            rng = random.Random(42 + i)
            star = (
                rng.random(),                              # x fraction
                rng.random(),                              # y fraction
                rng.randint(6, 28),                        # base size (subtle)
                rng.uniform(0.5, 3.0),                     # twinkle speed
                rng.uniform(0, 2 * math.pi),               # twinkle phase offset
                rng.randint(40, 120),                      # base brightness
            )
            self._stars.append(star)

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
        # Store previous heatmap for smooth transition
        if self._heatmap_cache is not None:
            self._prev_heatmap = QImage(self._heatmap_cache)
            self._transition_alpha = 0.0  # start fading in

        self._energy_grid = self._engine.energy_grid(
            self._grid_x_range, self._grid_y_range, self._grid_resolution)
        self._heatmap_cache = None
        self._cache_size = None
        self._pixmap_cache = None
        self._pixmap_cache_key = None

    def export_heatmap_png(self, path: str):
        """Export the current heatmap as a PNG file."""
        if self._heatmap_cache is not None:
            self._heatmap_cache.save(path)
        elif self._energy_grid is not None:
            w, h = self.width(), self.height()
            res = self._energy_grid.shape[0]
            img = QImage(res, res, QImage.Format_ARGB32_Premultiplied)
            for i in range(res):
                for j in range(res):
                    color = self._energy_to_color(self._energy_grid[i, j])
                    img.setPixelColor(j, i, color)
            scaled = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            scaled.save(path)

    # --- Settings ---

    def set_show_gradient(self, on: bool): self._show_gradient = on; self.update()
    def set_show_contours(self, on: bool): self._show_contours = on; self.update()
    def set_show_splats(self, on: bool): self._show_splats = on; self.update()
    def set_show_zones(self, on: bool): self._show_zones = on; self.update()
    def set_show_exploration(self, on: bool): self._show_exploration = on; self.update()

    def set_contour_count(self, n: int):
        self._contour_count = n
        self._heatmap_cache = None
        self._cache_size = None
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
        """Relax energy landscape."""
        if not self._engine.alpha:
            return
        for _ in range(5):
            total = sum(self._engine.alpha)
            if total > 0:
                for i in range(len(self._engine.alpha)):
                    self._engine.alpha[i] *= 1.0 + self._engine.kappa[i] * 0.01
                total = sum(self._engine.alpha)
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

        # Smooth zoom animation — ease toward target
        if abs(self._zoom - self._target_zoom) > 0.001:
            self._zoom += (self._target_zoom - self._zoom) * 0.15

        # Smooth color transition — fade from old to new heatmap
        if self._transition_alpha < 1.0:
            self._transition_alpha = min(1.0, self._transition_alpha + 0.05)

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

        # 1b. Twinkling star overlay
        self._paint_stars(painter, w, h)

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

        # 8. Hover info (splat-level)
        if self._hovered_idx >= 0:
            self._paint_hover_info(painter, w, h)

        # 9. Energy tooltip at cursor (grid-level)
        self._paint_energy_tooltip(painter, w, h)

        # 9b. Interactive crosshair cursor
        self._paint_crosshair(painter, w, h)

        # 10. Color scale legend (right side)
        self._paint_color_scale(painter, w, h)

        # 11. Legend + info (left side + top-right system info)
        self._paint_legend(painter, w, h)

        # 12. Axis labels with scientific notation
        self._paint_axes(painter, w, h)

        painter.end()

    def _energy_to_color(self, e: float) -> QColor:
        """Map energy value to thermal color.

        0.0 → deep blue (low energy = high confidence)
        0.3 → teal green
        0.7 → amber/orange
        1.0+ → deep red/crimson
        """
        t = min(e / 2.0, 1.0)  # normalize to [0,1]

        # Anchor colors from theme constants
        cold  = QColor(Colors.THERMAL_COLD)
        teal  = QColor(Colors.THERMAL_TEAL)
        green = QColor(Colors.THERMAL_GREEN)
        amber = QColor(Colors.THERMAL_AMBER)
        hot   = QColor(Colors.THERMAL_HOT)

        if t < 0.15:
            return Colors.lerp_color(cold, teal, t / 0.15)
        elif t < 0.35:
            return Colors.lerp_color(teal, green, (t - 0.15) / 0.2)
        elif t < 0.55:
            return Colors.lerp_color(green, amber, (t - 0.35) / 0.2)
        elif t < 0.75:
            return Colors.lerp_color(amber, QColor(240, 100, 20), (t - 0.55) / 0.2)
        else:
            return Colors.lerp_color(QColor(240, 100, 20), hot, (t - 0.75) / 0.25)

    def _paint_heatmap(self, painter: QPainter, w: int, h: int):
        """Render energy field as thermal heatmap with QPixmap caching and smooth transitions."""
        # Build QImage cache if needed
        if self._heatmap_cache is None or self._cache_size != (w, h):
            grid = self._energy_grid
            if grid is None:
                return

            res = grid.shape[0]
            img = QImage(res, res, QImage.Format_ARGB32_Premultiplied)

            for i in range(res):
                for j in range(res):
                    color = self._energy_to_color(grid[i, j])
                    img.setPixelColor(j, i, color)

            # Scale to widget size
            scaled = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self._heatmap_cache = scaled
            self._cache_size = (w, h)
            self._pixmap_cache = None  # invalidate pixmap too

        # Render previous heatmap during transition
        if self._transition_alpha < 1.0 and self._prev_heatmap is not None:
            prev_scaled = self._prev_heatmap.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            painter.drawImage(0, 0, prev_scaled)
            # Overlay new heatmap with transition alpha
            painter.setOpacity(self._transition_alpha)
            painter.drawImage(0, 0, self._heatmap_cache)
            painter.setOpacity(1.0)
        else:
            # Use QPixmap cache for faster blitting
            cache_key = (w, h)
            if self._pixmap_cache is None or self._pixmap_cache_key != cache_key:
                self._pixmap_cache = QPixmap.fromImage(self._heatmap_cache)
                self._pixmap_cache_key = cache_key
            painter.drawPixmap(0, 0, self._pixmap_cache)

    def _paint_stars(self, painter: QPainter, w: int, h: int):
        """Twinkling star field overlay — visible in low-energy (dark) regions."""
        if self._energy_grid is None:
            return

        t = self._time
        for (x_frac, y_frac, base_size, speed, phase, base_bright) in self._stars:
            # Twinkling: sinusoidal brightness modulation
            twinkle = 0.5 + 0.5 * math.sin(t * speed + phase)
            brightness = int(base_bright * (0.3 + 0.7 * twinkle))
            if brightness < 10:
                continue

            sx = x_frac * w
            sy = y_frac * h
            size = base_size * (0.6 + 0.4 * twinkle)

            # Warm star color (slight golden tint fits thermal theme)
            r = min(255, brightness + 30)
            g = min(255, brightness + 15)
            b = min(255, brightness)

            # Soft glow
            glow = QRadialGradient(QPointF(sx, sy), size)
            glow.setColorAt(0.0, QColor(r, g, b, brightness))
            glow.setColorAt(0.4, QColor(r, g, b, int(brightness * 0.4)))
            glow.setColorAt(1.0, QColor(r, g, b, 0))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(sx, sy), size, size)

            # Bright core dot
            if brightness > 60:
                core_alpha = min(255, brightness + 40)
                painter.setBrush(QBrush(QColor(255, 255, 240, core_alpha)))
                painter.drawEllipse(QPointF(sx, sy), max(1.0, size * 0.12), max(1.0, size * 0.12))

    def _paint_zones(self, painter: QPainter, w: int, h: int):
        """Paint confidence zone boundaries with pulsing glow on high-energy zones."""
        grid = self._energy_grid
        if grid is None:
            return

        t = self._time

        # Draw zone boundaries at E=0.3 and E=0.7
        for level, color, label in [
            (0.3, QColor(Colors.CONFIDENCE_HIGH), "High confidence"),
            (0.7, QColor(Colors.CONFIDENCE_LOW), "Low confidence"),
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

        # Pulsing glow on high-energy zones
        if self._energy_grid is not None:
            res = self._energy_grid.shape[0]
            pulse_t = 0.5 + 0.5 * math.sin(t * 1.8)
            # Sample sparse grid for high-energy hotspots
            for i in range(0, res, 6):
                for j in range(0, res, 6):
                    e = self._energy_grid[i, j]
                    if e < 0.6:
                        continue
                    x = self._grid_x_range[0] + j / res * (self._grid_x_range[1] - self._grid_x_range[0])
                    y = self._grid_y_range[0] + i / res * (self._grid_y_range[1] - self._grid_y_range[0])
                    sp = self._world_to_screen(x, y)

                    # Pulsing radius and alpha
                    base_r = 12 + e * 10
                    radius = base_r * (0.8 + 0.4 * pulse_t)
                    glow_alpha = int(40 * min(e, 1.5) * (0.6 + 0.4 * pulse_t))

                    # Multi-ring glow
                    for ring in range(3):
                        r_mult = 1.0 + ring * 0.5
                        ring_alpha = max(0, glow_alpha - ring * 12)
                        if ring_alpha <= 0:
                            continue

                        glow = QRadialGradient(QPointF(0, 0), radius * r_mult)
                        # Crimson/amber pulse
                        cr = min(255, 200 + int(55 * pulse_t))
                        cg = int(80 - 30 * pulse_t)
                        cb = int(30 + 20 * pulse_t)
                        glow.setColorAt(0.0, QColor(cr, cg, cb, ring_alpha))
                        glow.setColorAt(0.6, QColor(cr, cg // 2, cb, ring_alpha // 3))
                        glow.setColorAt(1.0, QColor(cr, 0, cb, 0))

                        painter.setPen(Qt.NoPen)
                        painter.setBrush(QBrush(glow))
                        painter.save()
                        painter.translate(sp)
                        painter.drawEllipse(QPointF(0, 0), radius * r_mult, radius * r_mult)
                        painter.restore()

    def _paint_contours(self, painter: QPainter, w: int, h: int):
        """Golden-ratio iso-contour lines with smooth thermal color transitions and labels."""
        grid = self._energy_grid
        if grid is None:
            return

        e_min = float(grid.min())
        e_max = float(grid.max())
        if e_max - e_min < 0.01:
            return

        # Golden-ratio contour spacing
        n = self._contour_count
        t = self._time
        for k in range(n):
            frac = (k + 1) / (n + 1)
            level = e_min + frac * (e_max - e_min)

            # Smooth thermal contour color based on energy level
            base_color = self._energy_to_color(level)
            # Add subtle time-based shimmer
            shimmer = 0.85 + 0.15 * math.sin(t * 0.8 + k * 0.7)
            r = min(255, int(base_color.red() * shimmer + 60 * (1 - frac)))
            g = min(255, int(base_color.green() * shimmer + 40 * (1 - frac)))
            b = min(255, int(base_color.blue() * shimmer + 80 * (1 - frac)))

            # Contour opacity fades with index, with gentle pulse
            alpha_base = 160 * (1.0 - 0.3 * k / n)
            alpha_pulse = alpha_base * (0.85 + 0.15 * math.sin(t * 1.2 + k * PHI))
            alpha = int(max(30, min(220, alpha_pulse)))

            contour_color = QColor(r, g, b, alpha)
            painter.setPen(QPen(contour_color, 1.2))
            painter.setBrush(Qt.NoBrush)

            paths = marching_squares(grid, level, self._grid_x_range, self._grid_y_range)
            for path_pts in paths:
                if len(path_pts) < 2:
                    continue
                screen_pts = [self._world_to_screen(p.x(), p.y()) for p in path_pts]
                painter.drawPolyline(QPolygonF(screen_pts))

                # Contour label at midpoint of each path
                if len(screen_pts) > 4:
                    mid = len(screen_pts) // 2
                    lp = screen_pts[mid]
                    painter.setFont(QFont("monospace", 6))
                    label_color = QColor(r, g, b, min(255, alpha + 40))
                    painter.setPen(label_color)
                    # Scientific notation for energy values
                    if abs(level) < 0.01 or abs(level) >= 1000:
                        label = f"{level:.1e}"
                    else:
                        label = f"{level:.2f}"
                    painter.drawText(int(lp.x() + 4), int(lp.y() - 4), label)

    def _paint_gradient_field(self, painter: QPainter, w: int, h: int):
        """Draw energy gradient arrows ∇E(x) with flowing animation."""
        if not self._engine.mu:
            return

        t = self._time
        xr, yr = self._grid_x_range, self._grid_y_range
        spacing = 8  # arrows per axis
        xs = np.linspace(xr[0] + 0.5, xr[1] - 0.5, spacing)
        ys = np.linspace(yr[0] + 0.5, yr[1] - 0.5, spacing)

        for iy, y in enumerate(ys):
            for ix, x in enumerate(xs):
                pt = np.array([x, y])
                e = self._engine.energy(pt)
                grad = self._engine.gradient(pt)

                # Arrow from gradient
                mag = float(np.linalg.norm(grad))
                if mag < 0.01:
                    continue

                # Normalize and scale arrow with flowing animation
                direction = grad / mag
                # Subtle oscillation in arrow length — "flowing" effect
                flow_phase = t * 1.5 + ix * 0.4 + iy * 0.3
                flow_mod = 0.85 + 0.15 * math.sin(flow_phase)
                arrow_len = min(mag * 15, 25) * flow_mod
                end = pt + direction * arrow_len * 0.1

                sp = self._world_to_screen(x, y)
                ep = self._world_to_screen(float(end[0]), float(end[1]))

                # Color by energy with flowing alpha
                _, color = EBMEngine.classify(e)
                base_alpha = int(40 + min(e * 60, 160))
                # Pulsing alpha for "energy flow" feel
                alpha_pulse = base_alpha * (0.8 + 0.2 * math.sin(flow_phase + 0.5))
                color.setAlpha(int(max(20, min(255, alpha_pulse))))

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
        xr, yr = self._grid_x_range, self._grid_y_range
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
            rc = QColor(Colors.CONFIDENCE_LOW)
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
            low_color = QColor(Colors.CONFIDENCE_LOW)
            low_color.setAlpha(int(80 * min(e, 1)))
            painter.setPen(QPen(low_color, 1, Qt.DashLine))
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
            ring_color = QColor(Colors.ACCENT)
            ring_color.setAlpha(ring_alpha)
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
            line_color = QColor(Colors.ACCENT)
            line_color.setAlpha(int(150 * fade))
            painter.setPen(QPen(line_color, 2.0 * fade))
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

    # --- Energy tooltip (grid-level hover) ---

    def _energy_at_screen(self, sx: float, sy: float) -> Optional[float]:
        """Sample energy grid at screen coordinates."""
        grid = self._energy_grid
        if grid is None:
            return None
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return None

        # Convert screen to grid indices
        res = grid.shape[0]
        gj = sx / w * res
        gi = (1.0 - sy / h) * res

        # Bilinear interpolation
        gi0 = int(gi)
        gj0 = int(gj)
        if gi0 < 0 or gi0 >= res - 1 or gj0 < 0 or gj0 >= res - 1:
            if 0 <= gi0 < res and 0 <= gj0 < res:
                return float(grid[gi0, gj0])
            return None

        fi = gi - gi0
        fj = gj - gj0
        e00 = float(grid[gi0, gj0])
        e01 = float(grid[gi0, gj0 + 1])
        e10 = float(grid[gi0 + 1, gj0])
        e11 = float(grid[gi0 + 1, gj0 + 1])
        e = e00 * (1 - fi) * (1 - fj) + e01 * (1 - fi) * fj + e10 * fi * (1 - fj) + e11 * fi * fj
        return e

    def _paint_energy_tooltip(self, painter: QPainter, w: int, h: int):
        """Show a floating tooltip with energy value at the cursor position on the grid."""
        pos = self._hover_screen_pos
        if pos is None:
            return
        # Only show if not hovering a splat (splat has its own tooltip)
        if self._hovered_idx >= 0:
            return

        energy = self._energy_at_screen(pos.x(), pos.y())
        if energy is None:
            return

        confidence = 1.0 / (1.0 + energy)
        zone_name, _ = EBMEngine.classify(energy)
        color = self._energy_to_color(energy)

        # World coordinates
        wx, wy = self._screen_to_world(pos.x(), pos.y())

        # Tooltip content
        lines = [
            f"E = {energy:.3f}",
            f"C = {confidence:.3f}",
            f"({wx:.1f}, {wy:.1f})",
            zone_name,
        ]

        font = QFont("monospace", 8)
        painter.setFont(font)
        fm = painter.fontMetrics()
        line_h = fm.height()
        max_tw = max(fm.horizontalAdvance(l) for l in lines)
        pad_x, pad_y = 6, 4
        tip_w = max_tw + pad_x * 2
        tip_h = line_h * len(lines) + pad_y * 2

        # Position tooltip offset from cursor, keep inside widget
        tx = pos.x() + 16
        ty = pos.y() - tip_h - 8
        if tx + tip_w > w - 10:
            tx = pos.x() - tip_w - 16
        if ty < 10:
            ty = pos.y() + 16

        # Background
        bg = QColor(Colors.BG_RAISED)
        bg.setAlpha(220)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(int(tx), int(ty), int(tip_w), int(tip_h), 5, 5)

        # Left accent bar colored by energy
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(int(tx), int(ty), 3, int(tip_h), 2, 2)

        # Text
        text_colors = [
            QColor(Colors.TEXT),
            QColor(Colors.TEXT_DIM),
            QColor(Colors.TEXT_DIM),
            color.lighter(130),
        ]
        for i, line in enumerate(lines):
            painter.setPen(text_colors[i])
            painter.drawText(int(tx + pad_x + 4), int(ty + pad_y + line_h * (i + 1) - 2), line)

    # --- Color scale legend (right side) ---

    def _paint_color_scale(self, painter: QPainter, w: int, h: int):
        """Render the energy color scale legend on the right side of the canvas.

        Vertical gradient bar mapping energy values (0..2+) to the thermal
        color palette (blue=cold → teal → green → amber → red=hot).
        """
        # Dimensions
        bar_w = 16
        bar_h = min(240, h - 100)
        if bar_h < 60:
            return
        bar_x = w - bar_w - 50
        bar_y = 90  # below the system info box

        # Semi-transparent background panel
        panel_pad = 6
        panel_x = bar_x - panel_pad
        panel_y = bar_y - 24  # room for title
        panel_w = bar_w + 42 + panel_pad * 2
        panel_h = bar_h + 24 + panel_pad * 2

        bg = QColor(Colors.BG_RAISED)
        bg.setAlpha(200)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(panel_x, panel_y, panel_w, panel_h, 6, 6)

        # Title
        painter.setFont(QFont("monospace", 7, QFont.Bold))
        painter.setPen(QColor(Colors.TEXT))
        painter.drawText(panel_x + panel_pad, bar_y - 8, "ENERGY SCALE")

        # Draw gradient bar: top=hot (high E), bottom=cold (low E)
        for i in range(bar_h):
            frac = 1.0 - i / bar_h  # 1 at top, 0 at bottom
            e = frac * 2.0           # energy value
            color = self._energy_to_color(e)
            painter.setPen(QPen(color))
            painter.drawLine(bar_x, bar_y + i, bar_x + bar_w, bar_y + i)

        # Border
        painter.setPen(QPen(QColor(Colors.TEXT_DIM), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(bar_x, bar_y, bar_w, bar_h)

        # Tick marks and labels
        painter.setFont(QFont("monospace", 7))
        painter.setPen(QColor(Colors.TEXT_DIM))
        ticks = [
            (0.0, "0.0 Cold", QColor(100, 140, 220)),     # bottom = cold blue
            (0.15, "0.3", QColor(80, 180, 100)),            # teal-green
            (0.5, "1.0", QColor(245, 180, 30)),             # amber
            (0.75, "1.5", QColor(230, 100, 30)),            # orange
            (1.0, "2.0+ Hot", QColor(220, 50, 50)),         # top = hot red
        ]
        for frac, label, tick_color in ticks:
            y = bar_y + int((1.0 - frac) * bar_h)
            # Tick line
            painter.setPen(QPen(tick_color, 1))
            painter.drawLine(bar_x + bar_w, y, bar_x + bar_w + 4, y)
            # Label
            painter.setPen(tick_color.lighter(120))
            painter.drawText(bar_x + bar_w + 6, y + 4, label)

        # Confidence zone mini-legend below the bar
        zone_y = bar_y + bar_h + 8
        painter.setFont(QFont("monospace", 6))
        for color_hex, label in [
            (QColor(Colors.CONFIDENCE_HIGH), "High conf"),
            (QColor(Colors.ACCENT), "Moderate"),
            (QColor(Colors.CONFIDENCE_LOW), "Uncertain"),
        ]:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color_hex))
            painter.drawEllipse(QPointF(bar_x + 4, zone_y), 3, 3)
            painter.setPen(QColor(Colors.TEXT_DIM))
            painter.drawText(bar_x + 10, int(zone_y + 3), label)
            zone_y += 12

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

        painter.setPen(QColor(0))
        painter.drawRect(bar_x, bar_y, bar_w, bar_h)

        painter.setPen(QColor(Colors.TEXT_DIM))
        painter.drawText(bar_x + bar_w + 4, bar_y + 8, "0.0")
        painter.drawText(bar_x + bar_w + 4, bar_y + bar_h // 2 + 4, "1.0")
        painter.drawText(bar_x + bar_w + 4, bar_y + bar_h, "2.0+")

        # Zone indicators
        zone_y = bar_y + bar_h + 22
        for color, label in [
            (QColor(Colors.CONFIDENCE_HIGH), "High conf"),
            (QColor(Colors.ACCENT), "Moderate"),
            (QColor(Colors.CONFIDENCE_LOW), "Uncertain"),
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
        painter.drawText(w - 187, 48, f"E(x) = -ln(Σ α·exp(-κ||x-μ||²))")
        painter.drawText(w - 187, 61, f"C(x) = 1/(1+E(x))")

    # --- Crosshair and axis labels ---

    def _paint_crosshair(self, painter: QPainter, w: int, h: int):
        """Interactive crosshair cursor showing energy at position."""
        pos = self._crosshair_pos
        if pos is None or not self._show_crosshair:
            return

        sx, sy = pos.x(), pos.y()
        if sx < 0 or sx > w or sy < 0 or sy > h:
            return

        energy = self._energy_at_screen(sx, sy)
        if energy is None:
            return

        color = self._energy_to_color(energy)

        # Crosshair lines
        cross_pen = QPen(QColor(color.red(), color.green(), color.blue(), 80), 1, Qt.DashLine)
        painter.setPen(cross_pen)
        painter.drawLine(int(sx), 0, int(sx), h)
        painter.drawLine(0, int(sy), w, int(sy))

        # Crosshair center dot
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 160)))
        painter.drawEllipse(QPointF(sx, sy), 4, 4)

        # Energy readout near cursor
        wx, wy = self._screen_to_world(sx, sy)
        painter.setFont(QFont("monospace", 8))
        painter.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 200)))
        confidence = 1.0 / (1.0 + energy)
        text = f"E={energy:.3f} C={confidence:.3f}"
        if abs(energy) >= 1000:
            text = f"E={energy:.1e} C={confidence:.3f}"
        painter.drawText(int(sx + 10), int(sy - 10), text)

    def _paint_axes(self, painter: QPainter, w: int, h: int):
        """Axis labels with scientific notation for energy values."""
        xr = self._grid_x_range
        yr = self._grid_y_range

        painter.setFont(QFont("monospace", 7))
        painter.setPen(QColor(Colors.TEXT_DIM))

        def sci_fmt(v: float) -> str:
            """Format value with scientific notation when appropriate."""
            if abs(v) < 0.01 and v != 0:
                return f"{v:.1e}"
            elif abs(v) >= 1000:
                return f"{v:.1e}"
            elif abs(v) >= 100:
                return f"{v:.0f}"
            else:
                return f"{v:.1f}"

        # X axis labels along bottom
        n_x = 5
        for i in range(n_x + 1):
            frac = i / n_x
            v = xr[0] + frac * (xr[1] - xr[0])
            x = frac * w
            painter.drawText(int(x - 15), h - 4, sci_fmt(v))
            # Tick mark
            painter.setPen(QPen(QColor(Colors.TEXT_DIM), 0.5))
            painter.drawLine(int(x), h - 14, int(x), h - 8)
            painter.setPen(QColor(Colors.TEXT_DIM))

        # Y axis labels along left
        n_y = 5
        for i in range(n_y + 1):
            frac = i / n_y
            v = yr[1] - frac * (yr[1] - yr[0])  # top = max
            y = frac * h
            painter.drawText(2, int(y + 4), sci_fmt(v))
            # Tick mark
            painter.setPen(QPen(QColor(Colors.TEXT_DIM), 0.5))
            painter.drawLine(0, int(y), 6, int(y))
            painter.setPen(QColor(Colors.TEXT_DIM))

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
        self._hover_screen_pos = pos
        self._crosshair_pos = pos
        # Tooltip on hover
        energy = self._energy_at_screen(pos.x(), pos.y())
        if energy is not None and self._hovered_idx < 0:
            wx, wy = self._screen_to_world(pos.x(), pos.y())
            confidence = 1.0 / (1.0 + energy)
            zone_name, _ = EBMEngine.classify(energy)
            self.setToolTip(
                f"E = {energy:.4f}\n"
                f"C = {confidence:.4f}\n"
                f"({wx:.2f}, {wy:.2f})\n"
                f"Zone: {zone_name}"
            )
        else:
            self.setToolTip("")

    def mouseReleaseEvent(self, event):
        self._drag_start = None

    def wheelEvent(self, event):
        """Smooth zoom with mouse wheel."""
        delta = event.angleDelta().y()
        zoom_factor = 1.15 if delta > 0 else 1.0 / 1.15
        self._target_zoom = max(0.1, min(10.0, self._target_zoom * zoom_factor))
        self._zoom = self._target_zoom  # direct for now; animation in _tick
        self._heatmap_cache = None
        self._cache_size = None
        self._pixmap_cache = None

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
        tb_w, tb = build_toolbar(
            "EBM Energy Landscape",
            subtitle="E(x) = -ln(Σ α·exp(-κ||x-μ||²))",
        )

        # Contour count (insert before stretch)
        tb.insertWidget(tb.count() - 1, QLabel("Contours:"))
        self.contour_slider = QSlider(Qt.Horizontal)
        self.contour_slider.setRange(2, 16)
        self.contour_slider.setValue(8)
        self.contour_slider.setFixedWidth(80)
        self.contour_slider.valueChanged.connect(self._on_contours)
        tb.insertWidget(tb.count() - 1, self.contour_slider)

        # Toggles
        self.grad_cb = QCheckBox("∇E")
        self.grad_cb.setChecked(True)
        self.grad_cb.toggled.connect(lambda v: self.canvas.set_show_gradient(v))
        tb.insertWidget(tb.count() - 1, self.grad_cb)

        self.contour_cb = QCheckBox("Contours")
        self.contour_cb.setChecked(True)
        self.contour_cb.toggled.connect(lambda v: self.canvas.set_show_contours(v))
        tb.insertWidget(tb.count() - 1, self.contour_cb)

        self.splat_cb = QCheckBox("Splats")
        self.splat_cb.setChecked(True)
        self.splat_cb.toggled.connect(lambda v: self.canvas.set_show_splats(v))
        tb.insertWidget(tb.count() - 1, self.splat_cb)

        self.zone_cb = QCheckBox("Zones")
        self.zone_cb.setChecked(True)
        self.zone_cb.toggled.connect(lambda v: self.canvas.set_show_zones(v))
        tb.insertWidget(tb.count() - 1, self.zone_cb)

        self.explore_cb = QCheckBox("Explore")
        self.explore_cb.setChecked(True)
        self.explore_cb.toggled.connect(lambda v: self.canvas.set_show_exploration(v))
        tb.insertWidget(tb.count() - 1, self.explore_cb)

        # Actions
        avalanche_btn = make_button("⚡ Avalanche", outlined=True,
                                    callback=self._on_avalanche)
        tb.insertWidget(tb.count() - 1, avalanche_btn)

        relax_btn = QPushButton("Relax")
        relax_btn.clicked.connect(self._on_relax)
        tb.insertWidget(tb.count() - 1, relax_btn)

        export_btn = QPushButton("📷 Export PNG")
        export_btn.clicked.connect(self._on_export)
        tb.insertWidget(tb.count() - 1, export_btn)

        layout.addWidget(tb_w)

        # Canvas
        self.canvas = EBMCanvas()
        self.canvas.node_clicked.connect(self._on_select)
        layout.addWidget(self.canvas, stretch=1)

        # Info bar
        self.info_bar = build_info_bar(
            "Hover splats to inspect · Double-click to select · ⚡ Avalanche to cascade"
        )
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

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Heatmap as PNG", "ebm_heatmap.png", "PNG Images (*.png)"
        )
        if path:
            self.canvas.export_heatmap_png(path)
            self.info_bar.setText(f"Heatmap exported to {path}")
