# SPDX-License-Identifier: GPL-3.0
"""Cluster Distribution View — KDE topographic visualization.

Mathematical foundation:
  Kernel Density Estimation:
    p̂ₖ(x) = (1/nₖ) Σᵢ K_h(x - xᵢ)
  where K_h(u) = (2πh²)⁻¹ exp(-||u||²/2h²)

  Silverman's bandwidth: h = 1.06 σ n^(-1/5)

  Iso-density contours at golden-ratio-spaced levels:
    φₖ = φ_max · φ^(-k)  where φ = (1+√5)/2

  Voronoi tessellation for cluster territory boundaries.

  Mahalanobis ellipses (1σ, 2σ, 3σ) from covariance Σₖ.

Renders as a topographic map: filled density bands + crisp contour lines
+ Voronoi boundaries + sigma ellipses + centroid markers.
"""

from __future__ import annotations

import colorsys
import os
import time
import numpy as np
from typing import Optional
from collections import defaultdict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSlider, QSplitter, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QSizePolicy, QFrame,
)
from PySide6.QtCore import Signal, Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QPainterPath, QImage, QLinearGradient, QPixmap, QTransform,
)

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.widgets import build_toolbar

# ---------------------------------------------------------------------------
# Perceptual palette — same golden-ratio hue spacing as Splat3D
# ---------------------------------------------------------------------------
_COLORS = [
    (245, 158, 11),   # Amber
    (59, 130, 246),   # Blue
    (16, 185, 129),   # Emerald
    (239, 68, 68),    # Red
    (139, 92, 246),   # Violet
    (236, 72, 153),   # Pink
    (20, 184, 166),   # Teal
    (249, 115, 22),   # Orange
    (6, 182, 212),    # Cyan
    (132, 204, 22),   # Lime
]

PHI = (1 + np.sqrt(5)) / 2  # Golden ratio ≈ 1.618

# Global palette hue rotation offset (smooth color palette rotation)
_palette_offset: float = 0.0


def _cluster_qcolor(k: int) -> QColor:
    """Get cluster color with optional palette rotation offset."""
    base = QColor(*_COLORS[k % len(_COLORS)])
    if _palette_offset != 0.0:
        h, s, v, a = base.getHsvF()
        h = (h + _palette_offset) % 1.0
        base.setHsvF(h, s, v, a)
    return base


# ---------------------------------------------------------------------------
# KDE computation
# ---------------------------------------------------------------------------

def compute_kde(
    positions: np.ndarray,  # (N, 2)
    labels: np.ndarray,     # (N,)
    grid_res: int = 150,
    padding: float = 0.15,
):
    """Compute KDE density field for each cluster on a regular grid.

    Returns (xx, yy, densities, extents) where:
      densities: (K, grid_res, grid_res) — density per cluster
      extents: (x_min, x_max, y_min, y_max) — data bounds with padding
    """
    x_min, y_min = positions.min(axis=0)
    x_max, y_max = positions.max(axis=0)

    # Add padding proportional to range
    rx, ry = x_max - x_min, y_max - y_min
    x_min -= rx * padding
    x_max += rx * padding
    y_min -= ry * padding
    y_max += ry * padding

    xx, yy = np.meshgrid(
        np.linspace(x_min, x_max, grid_res),
        np.linspace(y_min, y_max, grid_res),
    )

    n_clusters = int(labels.max()) + 1
    densities = np.zeros((n_clusters, grid_res, grid_res), dtype=np.float32)

    for k in range(n_clusters):
        mask = labels == k
        pts = positions[mask]
        n_k = len(pts)
        if n_k == 0:
            continue

        # Silverman's rule of thumb
        std = pts.std()
        h = 1.06 * std * max(n_k, 1) ** (-0.2) if std > 0 else 1.0
        h = max(h, rx * 0.05)  # floor to avoid too-tight kernels

        # Vectorized: broadcast (n_k, 1, 1) against (1, grid_res, grid_res)
        dx = xx[np.newaxis, :, :] - pts[:, 0, np.newaxis, np.newaxis]   # (n_k, H, W)
        dy = yy[np.newaxis, :, :] - pts[:, 1, np.newaxis, np.newaxis]
        r2 = (dx ** 2 + dy ** 2) / (h ** 2)
        densities[k] = np.exp(-0.5 * r2).sum(axis=0) / n_k

    return xx, yy, densities, (x_min, x_max, y_min, y_max)


# ---------------------------------------------------------------------------
# Marching squares contour extraction
# ---------------------------------------------------------------------------

def extract_contours(density: np.ndarray, threshold: float):
    """Extract iso-density contour paths at given threshold using marching squares.

    Returns list of QPainterPath objects.
    """
    h, w = density.shape
    paths = []
    segments = []

    for i in range(h - 1):
        for j in range(w - 1):
            # 4 corners
            v00 = density[i, j] >= threshold
            v10 = density[i, j + 1] >= threshold
            v01 = density[i + 1, j] >= threshold
            v11 = density[i + 1, j + 1] >= threshold

            case = (v00 << 3) | (v10 << 2) | (v11 << 1) | v01
            if case == 0 or case == 15:
                continue

            # Interpolate edge crossings
            def lerp(a, b):
                if abs(a - b) < 1e-10:
                    return 0.5
                return (threshold - a) / (b - a)

            # Edge midpoints (in grid coords)
            top = (j + lerp(density[i, j], density[i, j + 1]), i)
            right = (j + 1, i + lerp(density[i, j + 1], density[i + 1, j + 1]))
            bottom = (j + lerp(density[i + 1, j], density[i + 1, j + 1]), i + 1)
            left = (j, i + lerp(density[i, j], density[i + 1, j]))

            # Connect edges based on case (simplified — covers all 16 cases)
            edge_pairs = {
                1: [(left, bottom)], 2: [(bottom, right)],
                3: [(left, right)], 4: [(top, right)],
                5: [(top, left), (bottom, right)],  # saddle
                6: [(top, bottom)], 7: [(top, left)],
                8: [(top, left)], 9: [(top, bottom)],
                10: [(top, right), (left, bottom)],  # saddle
                11: [(top, right)], 12: [(left, right)],
                13: [(bottom, right)], 14: [(left, bottom)],
            }
            if case in edge_pairs:
                for e1, e2 in edge_pairs[case]:
                    segments.append((e1, e2))

    if not segments:
        return []

    # Convert segments to QPainterPaths
    # Simple approach: draw all segments as individual sub-paths
    path = QPainterPath()
    for (x1, y1), (x2, y2) in segments:
        path.moveTo(x1, y1)
        path.lineTo(x2, y2)
    return [path]


# ---------------------------------------------------------------------------
# Voronoi computation (pixel-based)
# ---------------------------------------------------------------------------

def compute_voronoi(
    centroids: np.ndarray,  # (K, 2) in data space
    grid_res: int,
    extents: tuple,
) -> np.ndarray:
    """Compute Voronoi assignment map on grid.

    Returns (grid_res, grid_res) array of cluster indices.
    """
    x_min, x_max, y_min, y_max = extents
    xx, yy = np.meshgrid(
        np.linspace(x_min, x_max, grid_res),
        np.linspace(y_min, y_max, grid_res),
    )

    # Distance from each grid point to each centroid
    n_clusters = len(centroids)
    dists = np.zeros((n_clusters, grid_res, grid_res), dtype=np.float32)
    for k in range(n_clusters):
        dists[k] = (xx - centroids[k, 0]) ** 2 + (yy - centroids[k, 1]) ** 2

    assignment = np.argmin(dists, axis=0)
    return assignment


def voronoi_edges(assignment: np.ndarray) -> list:
    """Extract Voronoi boundary pixels."""
    h, w = assignment.shape
    edges = []
    for i in range(1, h - 1):
        for j in range(1, w - 1):
            c = assignment[i, j]
            if (assignment[i - 1, j] != c or assignment[i + 1, j] != c or
                    assignment[i, j - 1] != c or assignment[i, j + 1] != c):
                edges.append((j, i))  # (x, y) in grid coords
    return edges


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

class ClusterCanvas(QWidget):
    """Topographic KDE visualization of cluster distributions."""

    cluster_clicked = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(500, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self._positions: Optional[np.ndarray] = None
        self._labels: Optional[np.ndarray] = None
        self._n_clusters: int = 0
        self._centroids: Optional[np.ndarray] = None
        self._covariances: Optional[np.ndarray] = None
        self._connections: list[dict] = []

        # Cached computation
        self._density_image: Optional[QImage] = None
        self._contour_paths: list = []  # [(color, level, path), ...]
        self._voronoi_edge_pts: list = []
        self._extents: tuple = (0, 1, 0, 1)
        self._grid_res: int = 150

        # Screen-space caches (rebuilt only on resize or data change)
        self._cached_size: tuple = (0, 0)
        self._cached_scaled_density: Optional[QImage] = None
        self._cached_voronoi_path: Optional[QPainterPath] = None
        self._cached_screen_contours: list = []  # [(color, level, screen_path), ...]

        self._hovered_cluster: int = -1
        self._selected_cluster: int = -1

        self.show_contours = True
        self.show_voronoi = True
        self.show_sigma = True
        self.show_points = True
        self.show_density = True

        # Density scale for colorbar
        self._density_max: float = 1.0

        # Fade transition state
        self._prev_density_image: Optional[QImage] = None
        self._cached_prev_scaled_density: Optional[QImage] = None
        self._fade_opacity: float = 1.0
        self._fade_steps: int = 0
        self._fade_total_steps: int = 25  # ~400ms at 60fps
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)  # ~60fps
        self._fade_timer.timeout.connect(self._on_fade_tick)

        # Hover label position (screen coords)
        self._hover_pos = None

        # Zoom/pan state with smooth animation
        self._zoom_level: float = 1.0
        self._target_zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._target_pan_x: float = 0.0
        self._target_pan_y: float = 0.0
        self._is_panning: bool = False
        self._pan_start = QPointF()
        self._pan_start_offset = (0.0, 0.0)
        self._zoom_pan_timer = QTimer(self)
        self._zoom_pan_timer.setInterval(16)
        self._zoom_pan_timer.timeout.connect(self._animate_zoom_pan)

        # Static pixmap cache for density/voronoi/contours
        self._static_pixmap: Optional[QPixmap] = None
        self._static_pixmap_dirty: bool = True

        # FPS counter (debug mode)
        self._debug_mode: bool = os.environ.get("SPLATSDB_DEBUG", "").strip() == "1"
        self._fps: float = 0.0
        self._frame_count: int = 0
        self._fps_time: float = time.time()
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(1000)
        self._fps_timer.timeout.connect(self._update_fps)
        if self._debug_mode:
            self._fps_timer.start()

        # Label animation state (per-cluster opacity)
        self._label_opacities: dict[int, float] = {}
        self._label_anim_timer = QTimer(self)
        self._label_anim_timer.setInterval(16)
        self._label_anim_timer.timeout.connect(self._animate_labels)

        # Resize debounce
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self._on_resize_debounced)

    def set_data(
        self,
        positions: np.ndarray,
        labels: np.ndarray,
        connections: list[dict] = None,
    ):
        self._positions = positions
        self._labels = labels
        self._n_clusters = int(labels.max()) + 1
        self._connections = connections or []

        # Save old density image for fade transition
        if self._density_image is not None:
            self._prev_density_image = self._density_image
            self._cached_prev_scaled_density = None
        else:
            self._prev_density_image = None

        # Centroids and covariances
        self._centroids = np.zeros((self._n_clusters, 2))
        self._covariances = np.zeros((self._n_clusters, 2, 2))
        for k in range(self._n_clusters):
            mask = labels == k
            if mask.any():
                pts = positions[mask]
                self._centroids[k] = pts.mean(axis=0)
                self._covariances[k] = np.cov(pts.T) if len(pts) > 1 else np.eye(2) * 0.01

        # Compute KDE
        xx, yy, densities, extents = compute_kde(positions, labels, self._grid_res)
        self._extents = extents

        # Build density QImage
        self._build_density_image(densities)

        # Extract contour lines
        self._extract_all_contours(densities)

        # Compute Voronoi
        assignment = compute_voronoi(self._centroids, self._grid_res, extents)
        self._voronoi_edge_pts = voronoi_edges(assignment)

        # Start fade transition (replaces direct self.update())
        self._start_fade_transition()

        # Mark static pixmap cache dirty for density/voronoi/contours
        self._static_pixmap_dirty = True

        # Start label animations — fade in new cluster labels
        self._label_opacities = {k: 0.0 for k in range(self._n_clusters)}
        self._label_anim_timer.start()

        # Reset zoom/pan on new data
        self._target_zoom = 1.0
        self._target_pan_x = 0.0
        self._target_pan_y = 0.0
        if not self._zoom_pan_timer.isActive():
            self._zoom_pan_timer.start()

    def _build_density_image(self, densities: np.ndarray):
        """Render KDE density as a QImage with topographic banding.

        Uses numpy vectorization instead of per-pixel Python loops
        for a ~100x speedup over the naive approach.
        """
        grid_res = self._grid_res

        # Dominant cluster per pixel + total density
        dominant = np.argmax(densities, axis=0)
        max_density = np.max(densities, axis=0)

        d_max = float(max_density.max())
        if d_max < 1e-10:
            d_max = 1.0
        self._density_max = d_max

        d_norm = max_density / d_max  # (grid_res, grid_res) normalised

        # Topographic contour bands at golden-ratio-spaced levels
        n_bands = 6
        band_levels = []
        level = 1.0
        for _ in range(n_bands):
            band_levels.append(level)
            level /= PHI

        # Vectorised band index computation
        band_idx = np.zeros((grid_res, grid_res), dtype=np.int32)
        for b, bl in enumerate(band_levels):
            mask = d_norm >= bl
            band_idx[mask] = b

        brightness = 0.15 + 0.12 * band_idx

        # Colour look-up table from palette
        n_c = max(self._n_clusters, 1)
        colors = np.array(
            [_COLORS[k % len(_COLORS)] for k in range(n_c)],
            dtype=np.float32,
        )

        base_r = colors[dominant, 0]
        base_g = colors[dominant, 1]
        base_b = colors[dominant, 2]

        r = base_r * brightness
        g = base_g * brightness
        b_val = base_b * brightness

        # Band boundary darkening (vectorised)
        for bl in band_levels:
            rel_dist = np.abs(d_norm - bl) / max(bl, 0.01)
            dark = rel_dist < 0.03
            r[dark] *= 0.6
            g[dark] *= 0.6
            b_val[dark] *= 0.6

        r = np.clip(r, 0, 255).astype(np.uint32)
        g = np.clip(g, 0, 255).astype(np.uint32)
        b_val = np.clip(b_val, 0, 255).astype(np.uint32)
        alpha = np.clip(brightness * 255, 0, 180).astype(np.uint32)

        # ARGB32 pixel buffer: 0xAARRGGBB
        pixels = (alpha << 24) | (r << 16) | (g << 8) | b_val
        pixels = np.ascontiguousarray(pixels)

        img = QImage(
            pixels.tobytes(), grid_res, grid_res,
            grid_res * 4, QImage.Format_ARGB32,
        )
        self._density_image = img.copy()

        # Invalidate screen cache since density image changed
        self._invalidate_screen_cache()

    def _extract_all_contours(self, densities: np.ndarray):
        """Extract contour lines for each cluster at golden-ratio levels."""
        self._contour_paths = []

        for k in range(self._n_clusters):
            d = densities[k]
            d_max = d.max()
            if d_max < 1e-10:
                continue

            color = _cluster_qcolor(k)

            # 4 contour levels at golden-ratio spacing
            for level_frac in [0.6, 0.37, 0.23, 0.14]:
                threshold = d_max * level_frac
                paths = extract_contours(d, threshold)
                for path in paths:
                    self._contour_paths.append((color, level_frac, path))

    def _to_screen(self, data_x: float, data_y: float) -> tuple:
        """Transform data coordinates to screen coordinates."""
        w, h = self.width(), self.height()
        margin = 50
        x_min, x_max, y_min, y_max = self._extents

        sx = margin + (data_x - x_min) / max(x_max - x_min, 1e-6) * (w - 2 * margin)
        sy = margin + (1 - (data_y - y_min) / max(y_max - y_min, 1e-6)) * (h - 2 * margin)
        return sx, sy

    def _grid_to_screen(self, gx: float, gy: float) -> tuple:
        """Transform grid coordinates to screen coordinates."""
        w, h = self.width(), self.height()
        margin = 50
        gr = self._grid_res

        sx = margin + gx / gr * (w - 2 * margin)
        sy = margin + gy / gr * (h - 2 * margin)
        return sx, sy

    # ------------------------------------------------------------------
    # Screen-space cache management
    # ------------------------------------------------------------------

    def _invalidate_screen_cache(self):
        """Mark screen-space caches as stale (called on data or size change)."""
        self._cached_size = (0, 0)
        self._cached_scaled_density = None
        self._cached_voronoi_path = None
        self._cached_screen_contours = []
        self._cached_prev_scaled_density = None
        self._static_pixmap_dirty = True

    def _rebuild_screen_caches(self):
        """Rebuild all screen-space resources from grid-space data.

        Called only when widget size changes or data is invalidated.
        This avoids per-frame recomputation in paintEvent.
        """
        w, h = self.width(), self.height()
        margin = 50
        draw_w, draw_h = w - 2 * margin, h - 2 * margin
        self._cached_size = (w, h)

        # 1. Scaled density image (avoid per-frame QImage.scaled)
        if self._density_image is not None:
            self._cached_scaled_density = self._density_image.scaled(
                draw_w, draw_h,
            )

        # 2. Voronoi edges as single QPainterPath (avoid per-frame drawPoint loop)
        if self._voronoi_edge_pts:
            vpath = QPainterPath()
            for gx, gy in self._voronoi_edge_pts:
                sx, sy = self._grid_to_screen(gx, gy)
                si, sj = int(sx), int(sy)
                vpath.moveTo(si, sj)
                vpath.lineTo(si + 1, sj)
            self._cached_voronoi_path = vpath
        else:
            self._cached_voronoi_path = None

        # 3. Contour paths pre-transformed to screen space
        self._cached_screen_contours = []
        for color, level, path in self._contour_paths:
            screen_path = QPainterPath()
            count = path.elementCount()
            for i in range(count):
                el = path.elementAt(i)
                sx, sy = self._grid_to_screen(el.x, el.y)
                if i == 0 or el.type == 0:  # MoveTo
                    screen_path.moveTo(sx, sy)
                else:
                    screen_path.lineTo(sx, sy)
            self._cached_screen_contours.append((color, level, screen_path))

    def _build_static_pixmap(self):
        """Render density, voronoi, and contours into a cached QPixmap.

        These are the most expensive static layers — caching avoids
        per-frame recomputation when only dynamic elements (hover, labels)
        change.
        """
        w, h = self.width(), self.height()
        margin = 50
        draw_w, draw_h = w - 2 * margin, h - 2 * margin

        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)

        # Density heatmap with fade transition
        if self.show_density:
            if self._fade_opacity < 1.0 and self._prev_density_image is not None:
                if self._cached_prev_scaled_density is None:
                    self._cached_prev_scaled_density = self._prev_density_image.scaled(
                        draw_w, draw_h,
                    )
                painter.setOpacity(1.0 - self._fade_opacity)
                painter.drawImage(margin, margin, self._cached_prev_scaled_density)
                painter.setOpacity(self._fade_opacity)
                if self._cached_scaled_density is not None:
                    painter.drawImage(margin, margin, self._cached_scaled_density)
            elif self._cached_scaled_density is not None:
                painter.drawImage(margin, margin, self._cached_scaled_density)

        # Voronoi boundaries
        if self.show_voronoi and self._cached_voronoi_path is not None:
            painter.setPen(QPen(Colors.with_alpha(QColor(Colors.TEXT), 25), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self._cached_voronoi_path)

        # Contour lines
        if self.show_contours:
            for color, level, screen_path in self._cached_screen_contours:
                alpha = int(60 + level * 200)
                pen_color = QColor(color)
                pen_color.setAlpha(min(alpha, 220))
                width = 1.0 + level * 1.5
                painter.setPen(QPen(pen_color, width))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(screen_path)

        painter.end()
        self._static_pixmap = pm
        self._static_pixmap_dirty = False

    def paintEvent(self, event):
        if self._positions is None:
            return

        t0 = time.time()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Rebuild screen-space caches only when size changes
        if (w, h) != self._cached_size:
            self._rebuild_screen_caches()

        # Background
        painter.fillRect(0, 0, w, h, QColor(Colors.BG))

        # Subtle graph paper grid
        pen_grid = QPen(Colors.with_alpha(QColor(Colors.TEXT), 8), 0.5)
        painter.setPen(pen_grid)
        for x in range(0, w, 25):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, 25):
            painter.drawLine(0, y, w, y)

        # Apply zoom/pan transform for data layers
        painter.save()
        cx, cy = w / 2.0, h / 2.0
        transform = QTransform()
        transform.translate(cx + self._pan_x, cy + self._pan_y)
        transform.scale(self._zoom_level, self._zoom_level)
        transform.translate(-cx, -cy)
        painter.setTransform(transform)

        # Static layers: density + voronoi + contours (cached pixmap)
        if self._static_pixmap_dirty or self._static_pixmap is None:
            self._build_static_pixmap()
        if self._static_pixmap is not None:
            painter.drawPixmap(0, 0, self._static_pixmap)

        # Sigma ellipses
        if self.show_sigma and self._centroids is not None:
            for k in range(self._n_clusters):
                cx_k, cy_k = self._to_screen(self._centroids[k, 0], self._centroids[k, 1])
                cov = self._covariances[k]
                color = _cluster_qcolor(k)

                try:
                    eigvals, eigvecs = np.linalg.eigh(cov)
                    eigvals = np.maximum(eigvals, 0.001)
                except Exception:
                    eigvals = np.array([0.1, 0.1])
                    eigvecs = np.eye(2)

                angle = np.degrees(np.arctan2(eigvecs[1, 0], eigvecs[0, 0]))
                full_range_x = max(self._extents[1] - self._extents[0], 0.01)
                full_range_y = max(self._extents[3] - self._extents[2], 0.01)
                px_x = (w - 100) / full_range_x
                px_y = (h - 100) / full_range_y

                for sigma_mult, line_style, alpha_base in [
                    (3, Qt.PenStyle.DotLine, 25), (2, Qt.PenStyle.DashLine, 45),
                    (1, Qt.PenStyle.SolidLine, 80)
                ]:
                    rx = np.sqrt(eigvals[0]) * sigma_mult * px_x
                    ry = np.sqrt(eigvals[1]) * sigma_mult * px_y

                    pen_color = QColor(color)
                    pen_color.setAlpha(alpha_base)
                    painter.setPen(QPen(pen_color, 1.2, line_style))
                    painter.setBrush(Qt.NoBrush)

                    painter.save()
                    painter.translate(cx_k, cy_k)
                    painter.rotate(-angle)
                    painter.drawEllipse(int(-rx), int(-ry), int(2 * rx), int(2 * ry))
                    painter.restore()

        # Cluster boundary highlighting on hover
        if self._hovered_cluster >= 0 and self._centroids is not None:
            k = self._hovered_cluster
            cx_k, cy_k = self._to_screen(self._centroids[k, 0], self._centroids[k, 1])
            color = _cluster_qcolor(k)
            cov = self._covariances[k] if k < len(self._covariances) else np.eye(2) * 0.01
            try:
                eigvals, eigvecs = np.linalg.eigh(cov)
                eigvals = np.maximum(eigvals, 0.001)
            except Exception:
                eigvals = np.array([0.1, 0.1])
                eigvecs = np.eye(2)
            angle = np.degrees(np.arctan2(eigvecs[1, 0], eigvecs[0, 0]))
            full_range_x = max(self._extents[1] - self._extents[0], 0.01)
            full_range_y = max(self._extents[3] - self._extents[2], 0.01)
            px_x = (w - 100) / full_range_x
            px_y = (h - 100) / full_range_y
            rx = np.sqrt(eigvals[0]) * 2.5 * px_x
            ry = np.sqrt(eigvals[1]) * 2.5 * px_y
            glow = QColor(color)
            glow.setAlpha(30)
            painter.setPen(QPen(QColor(color), 2, Qt.PenStyle.DashDotLine))
            painter.setBrush(QBrush(glow))
            painter.save()
            painter.translate(cx_k, cy_k)
            painter.rotate(-angle)
            painter.drawEllipse(int(-rx), int(-ry), int(2 * rx), int(2 * ry))
            painter.restore()

        # Point shadows for depth (render behind points)
        if self.show_points:
            pen_shadow = QPen(Qt.PenStyle.NoPen)
            shadow_color = QColor(0, 0, 0, 40)
            painter.setPen(pen_shadow)
            painter.setBrush(QBrush(shadow_color))
            for i in range(len(self._positions)):
                k = self._labels[i]
                sx, sy = self._to_screen(self._positions[i, 0], self._positions[i, 1])
                if k == self._hovered_cluster or k == self._selected_cluster:
                    painter.drawEllipse(int(sx - 5 + 1), int(sy - 5 + 1), 10, 10)
                else:
                    painter.drawEllipse(int(sx - 3 + 1), int(sy - 3 + 1), 6, 6)

        # Points
        if self.show_points:
            for i in range(len(self._positions)):
                k = self._labels[i]
                sx, sy = self._to_screen(self._positions[i, 0], self._positions[i, 1])
                color = _cluster_qcolor(k)

                if k == self._hovered_cluster or k == self._selected_cluster:
                    painter.setPen(QPen(Colors.with_alpha(QColor(Colors.TEXT), 180), 1))
                    size = 5
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                    size = 3

                pc = QColor(color)
                pc.setAlpha(200)
                painter.setBrush(QBrush(pc))
                painter.drawEllipse(int(sx - size), int(sy - size), size * 2, size * 2)

        # Centroid markers with animated labels
        if self._centroids is not None:
            for k in range(self._n_clusters):
                cx_k, cy_k = self._to_screen(self._centroids[k, 0], self._centroids[k, 1])
                color = _cluster_qcolor(k)
                mask = self._labels == k
                n_k = int(mask.sum())

                # Label opacity animation
                opacity = self._label_opacities.get(k, 1.0)

                # Cross marker
                painter.setPen(QPen(QColor(color), 2.5))
                painter.drawLine(int(cx_k - 8), int(cy_k), int(cx_k + 8), int(cy_k))
                painter.drawLine(int(cx_k), int(cy_k - 8), int(cx_k), int(cy_k + 8))

                # Label with background (animated opacity)
                painter.setOpacity(opacity)
                label = f"C{k}"
                painter.setFont(QFont("monospace", 9, QFont.Weight.Bold))
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(label)
                th = fm.height()

                bg = QColor(Colors.BG)
                bg.setAlpha(180)
                painter.fillRect(int(cx_k + 10), int(cy_k - th), tw + 6, th + 2, bg)

                painter.setPen(QPen(color))
                painter.drawText(int(cx_k + 13), int(cy_k - 2), label)

                painter.setFont(QFont("sans-serif", 7))
                painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
                painter.drawText(int(cx_k + 13), int(cy_k + 10), f"n={n_k}")
                painter.setOpacity(1.0)

        # Inter-cluster arcs
        self._paint_connections(painter)

        # Restore from zoom/pan transform
        painter.restore()

        # UI overlays (not affected by zoom/pan)
        self._paint_colorbar(painter)
        self._paint_legend(painter)
        self._paint_hover_label(painter)

        if self._debug_mode:
            self._paint_fps_counter(painter)

        # FPS frame counting
        self._frame_count += 1

        painter.end()

    def _paint_connections(self, painter: QPainter):
        if not self._connections or self._centroids is None:
            return
        for conn in self._connections:
            src, dst = conn.get("source", 0), conn.get("target", 0)
            score = conn.get("score", 0)
            if src >= self._n_clusters or dst >= self._n_clusters:
                continue

            p1 = self._to_screen(self._centroids[src, 0], self._centroids[src, 1])
            p2 = self._to_screen(self._centroids[dst, 0], self._centroids[dst, 1])

            mx = (p1[0] + p2[0]) / 2
            my = (p1[1] + p2[1]) / 2 - 30 * (1 - score)

            alpha = int(score * 180)
            # Use amber-to-blue gradient based on score
            arc_color = Colors.lerp_color(
                QColor(Colors.INFO), QColor(Colors.ACCENT), score
            )
            arc_color.setAlpha(alpha)
            painter.setPen(QPen(arc_color, 1.5 + score * 2))

            path = QPainterPath()
            path.moveTo(p1[0], p1[1])
            path.quadTo(mx, my, p2[0], p2[1])
            painter.drawPath(path)

            # Score label
            if score > 0.5:
                painter.setFont(QFont("monospace", 7))
                painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
                painter.drawText(int(mx - 12), int(my - 5), f"{score:.2f}")

    # ------------------------------------------------------------------
    # Fade transition
    # ------------------------------------------------------------------

    def _start_fade_transition(self):
        """Start a crossfade animation from old to new density image."""
        if self._prev_density_image is not None:
            self._fade_opacity = 0.0
            self._fade_steps = 0
            self._fade_timer.start()
        else:
            self._fade_opacity = 1.0
        self.update()

    def _on_fade_tick(self):
        """Advance the fade animation by one step (called by timer)."""
        self._fade_steps += 1
        # Ease-out quadratic curve for smooth deceleration
        t = self._fade_steps / self._fade_total_steps
        self._fade_opacity = 1.0 - (1.0 - t) ** 2

        if self._fade_steps >= self._fade_total_steps:
            self._fade_timer.stop()
            self._fade_opacity = 1.0
            self._prev_density_image = None
            self._cached_prev_scaled_density = None
            self._static_pixmap_dirty = True  # Rebuild static cache without fade

        self.update()

    # ------------------------------------------------------------------
    # Density colorbar
    # ------------------------------------------------------------------

    def _paint_colorbar(self, painter: QPainter):
        """Draw a density scale colorbar on the right side of the canvas."""
        w, h = self.width(), self.height()
        margin = 50

        bar_w = 14
        bar_h = h - 2 * margin - 60
        if bar_h < 60:
            return
        bar_x = w - margin + 10
        bar_y = margin + 30

        # Vertical gradient: bottom=low → top=high, using amber base color
        gradient = QLinearGradient(bar_x, bar_y + bar_h, bar_x, bar_y)
        amber = _COLORS[0]  # Amber as representative density color
        n_steps = 10
        for i in range(n_steps + 1):
            t = i / n_steps
            brightness = 0.15 + 0.60 * t
            r = int(min(amber[0] * brightness, 255))
            g = int(min(amber[1] * brightness, 255))
            b = int(min(amber[2] * brightness, 255))
            gradient.setColorAt(1.0 - t, QColor(r, g, b, 200))

        # Bar background + border
        painter.setPen(QPen(Colors.with_alpha(QColor(Colors.TEXT), 35), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(int(bar_x), int(bar_y), bar_w, int(bar_h), 3, 3)

        # Band-level tick marks
        band_levels = []
        level = 1.0
        for _ in range(6):
            band_levels.append(level)
            level /= PHI

        painter.setFont(QFont("sans-serif", 7))
        for bl in band_levels:
            y_pos = bar_y + bar_h * (1.0 - bl)
            if y_pos < bar_y or y_pos > bar_y + bar_h:
                continue
            # Tick mark
            painter.setPen(QPen(Colors.with_alpha(QColor(Colors.TEXT), 50), 0.5))
            painter.drawLine(int(bar_x - 3), int(y_pos), int(bar_x), int(y_pos))
            # Value label
            val = self._density_max * bl
            painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
            painter.drawText(int(bar_x + bar_w + 3), int(y_pos + 4), f"{val:.2f}")

        # Top/Bottom labels
        painter.setPen(QPen(QColor(Colors.TEXT)))
        painter.setFont(QFont("sans-serif", 7, QFont.Weight.Bold))
        painter.drawText(int(bar_x - 1), int(bar_y - 6), "High")
        painter.drawText(int(bar_x + 2), int(bar_y + bar_h + 12), "Low")

        # Rotated "Density" title
        painter.save()
        painter.translate(int(bar_x - 6), int(bar_y + bar_h / 2))
        painter.rotate(-90)
        painter.setFont(QFont("sans-serif", 8, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
        painter.drawText(0, 0, "Density")
        painter.restore()

    # ------------------------------------------------------------------
    # Hover label overlay
    # ------------------------------------------------------------------

    def _paint_hover_label(self, painter: QPainter):
        """Draw a floating info card for the hovered cluster."""
        if self._hovered_cluster < 0 or self._centroids is None:
            return
        if self._hover_pos is None:
            return

        k = self._hovered_cluster
        color = _cluster_qcolor(k)
        mask = self._labels == k
        n_k = int(mask.sum())

        # Compute spread (σ)
        spread = 0.0
        if self._covariances is not None and k < len(self._covariances):
            spread = float(np.sqrt(np.trace(self._covariances[k]) / 2))

        lines = [
            f"Cluster C{k}",
            f"Points: {n_k}",
            f"Spread (σ): {spread:.3f}",
        ]

        # Measure text
        painter.setFont(QFont("sans-serif", 9))
        fm = painter.fontMetrics()
        line_h = fm.height()
        max_w = max(fm.horizontalAdvance(l) for l in lines)

        padding = 8
        box_w = max_w + 2 * padding + 4  # +4 for accent bar
        box_h = len(lines) * line_h + 2 * padding

        # Position near centroid, offset to avoid obscuring it
        cx, cy = self._to_screen(self._centroids[k, 0], self._centroids[k, 1])
        bx = cx + 22
        by = cy - box_h // 2

        # Clamp within widget bounds
        w, h = self.width(), self.height()
        if bx + box_w > w - 10:
            bx = cx - box_w - 22
        if by < 10:
            by = 10
        if by + box_h > h - 10:
            by = h - box_h - 10

        # Background card with rounded corners
        bg = QColor(Colors.BG_RAISED)
        bg.setAlpha(230)
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(int(bx), int(by), int(box_w), int(box_h), 6, 6)

        # Accent color bar on the left edge
        accent = QColor(color)
        accent.setAlpha(200)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(accent))
        painter.drawRoundedRect(int(bx), int(by), 4, int(box_h), 2, 2)

        # Text lines
        text_x = int(bx + padding + 4)
        for i, line in enumerate(lines):
            ty = int(by + padding + (i + 1) * line_h - 3)
            if i == 0:
                painter.setFont(QFont("sans-serif", 9, QFont.Weight.Bold))
                painter.setPen(QPen(color))
            else:
                painter.setFont(QFont("sans-serif", 9))
                painter.setPen(QPen(QColor(Colors.TEXT)))
            painter.drawText(text_x, ty, line)

        # Highlight ring around hovered centroid
        painter.setPen(QPen(QColor(color), 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(int(cx - 14), int(cy - 14), 28, 28)

    # ------------------------------------------------------------------
    # Color legend with count badges
    # ------------------------------------------------------------------

    def _paint_legend(self, painter: QPainter):
        """Draw cluster color legend with count badges in bottom-left."""
        if self._n_clusters == 0 or self._labels is None:
            return

        w, h = self.width(), self.height()
        padding = 8
        swatch_size = 12
        row_h = 20
        badge_w = 32
        badge_h = 16

        n = self._n_clusters
        box_w = 120
        box_h = padding + n * row_h + padding

        lx = 60
        ly = h - box_h - 10

        # Background card
        bg = QColor(Colors.BG_RAISED)
        bg.setAlpha(210)
        painter.setPen(QPen(QColor(Colors.BORDER), 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(lx, ly, box_w, box_h, 6, 6)

        for k in range(n):
            color = _cluster_qcolor(k)
            ry = ly + padding + k * row_h

            # Color swatch
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(lx + padding, int(ry), swatch_size, swatch_size, 2, 2)

            # Cluster label
            painter.setPen(QColor(Colors.TEXT))
            painter.setFont(QFont("sans-serif", 8))
            painter.drawText(lx + padding + swatch_size + 5, int(ry + 10), f"C{k}")

            # Count badge
            n_k = int((self._labels == k).sum())
            badge_x = lx + box_w - badge_w - 4
            badge_bg = QColor(color)
            badge_bg.setAlpha(40)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(badge_bg))
            painter.drawRoundedRect(badge_x, int(ry), badge_w, badge_h, 3, 3)
            painter.setPen(QColor(color))
            painter.setFont(QFont("monospace", 7, QFont.Weight.Bold))
            painter.drawText(badge_x + 4, int(ry + 11), f"n={n_k}")

    # ------------------------------------------------------------------
    # FPS counter (debug mode)
    # ------------------------------------------------------------------

    def _paint_fps_counter(self, painter: QPainter):
        """Render FPS counter in the top-left corner."""
        painter.setPen(QColor(Colors.ACCENT))
        painter.setFont(QFont("monospace", 9))
        painter.drawText(10, 20, f"FPS: {self._fps:.0f}")
        painter.setPen(QColor(Colors.TEXT_DIM))
        painter.drawText(10, 34, f"Zoom: {self._zoom_level:.2f}x")

    def _update_fps(self):
        """Update FPS calculation every second."""
        now = time.time()
        elapsed = now - self._fps_time
        if elapsed > 0:
            self._fps = self._frame_count / elapsed
        self._frame_count = 0
        self._fps_time = now

    # ------------------------------------------------------------------
    # Label animation
    # ------------------------------------------------------------------

    def _animate_labels(self):
        """Gradually increase label opacity from 0 to 1."""
        all_done = True
        for k in self._label_opacities:
            if self._label_opacities[k] < 1.0:
                self._label_opacities[k] = min(1.0, self._label_opacities[k] + 0.06)
                all_done = False
        if all_done:
            self._label_anim_timer.stop()
        self.update()

    # ------------------------------------------------------------------
    # Zoom/pan smooth animation
    # ------------------------------------------------------------------

    def _animate_zoom_pan(self):
        """Smooth interpolation toward target zoom/pan values."""
        lerp = 0.15
        dx = self._target_zoom - self._zoom_level
        dpx = self._target_pan_x - self._pan_x
        dpy = self._target_pan_y - self._pan_y

        self._zoom_level += dx * lerp
        self._pan_x += dpx * lerp
        self._pan_y += dpy * lerp

        if abs(dx) < 0.001 and abs(dpx) < 0.5 and abs(dpy) < 0.5:
            self._zoom_level = self._target_zoom
            self._pan_x = self._target_pan_x
            self._pan_y = self._target_pan_y
            self._zoom_pan_timer.stop()

        self.update()

    def wheelEvent(self, event):
        """Zoom in/out with scroll wheel, centered on mouse position."""
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 1 / 1.1
        new_zoom = self._target_zoom * factor
        new_zoom = max(0.25, min(10.0, new_zoom))
        self._target_zoom = new_zoom
        if not self._zoom_pan_timer.isActive():
            self._zoom_pan_timer.start()

    # ------------------------------------------------------------------
    # Resize debounce
    # ------------------------------------------------------------------

    def _on_resize_debounced(self):
        """Called after resize settles — rebuild caches."""
        self._invalidate_screen_cache()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()  # Debounce: rebuild after 50ms settle

    def mouseMoveEvent(self, event):
        if self._centroids is None:
            return
        pos = event.position()

        # Handle panning when middle button or right button is held
        if self._is_panning:
            dx = pos.x() - self._pan_start.x()
            dy = pos.y() - self._pan_start.y()
            self._target_pan_x = self._pan_start_offset[0] + dx
            self._target_pan_y = self._pan_start_offset[1] + dy
            if not self._zoom_pan_timer.isActive():
                self._zoom_pan_timer.start()
            return

        self._hover_pos = pos
        closest, min_d = -1, 60
        for k in range(self._n_clusters):
            cx, cy = self._to_screen(self._centroids[k, 0], self._centroids[k, 1])
            d = ((pos.x() - cx) ** 2 + (pos.y() - cy) ** 2) ** 0.5
            if d < min_d:
                min_d = d
                closest = k
        if closest != self._hovered_cluster:
            self._hovered_cluster = closest
            self.update()

    def mousePressEvent(self, event):
        # Middle or right button starts panning
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._is_panning = True
            self._pan_start = event.position()
            self._pan_start_offset = (self._target_pan_x, self._target_pan_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self._hovered_cluster >= 0:
            self._selected_cluster = self._hovered_cluster
            self.cluster_clicked.emit(self._selected_cluster)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event):
        """Double-click to reset zoom/pan."""
        self._target_zoom = 1.0
        self._target_pan_x = 0.0
        self._target_pan_y = 0.0
        if not self._zoom_pan_timer.isActive():
            self._zoom_pan_timer.start()


# ---------------------------------------------------------------------------
# Stats panel
# ---------------------------------------------------------------------------

class ClusterStatsPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("CLUSTER TOPOLOGY")
        title.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        layout.addWidget(title)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Cluster", "n", "σ", "ρ"])
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {Colors.BG}; border: 1px solid {Colors.BORDER};
                border-radius: 6px; color: {Colors.TEXT}; font-size: 11px;
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_RAISED}; color: {Colors.TEXT_DIM};
                border: none; padding: 4px; font-size: 10px;
            }}
        """)
        layout.addWidget(self.tree)
        self.setStyleSheet(f"background-color: {Colors.BG_RAISED};")

    def update_stats(self, labels, centroids, covariances):
        self.tree.clear()
        for k in range(len(centroids)):
            mask = labels == k
            n = int(mask.sum())
            std = float(np.sqrt(np.trace(covariances[k]) / 2))
            density = n / max(std ** 2, 0.001)
            color = _cluster_qcolor(k)
            item = QTreeWidgetItem([f"● C{k}", str(n), f"{std:.3f}", f"{density:.1f}"])
            item.setForeground(0, color)
            self.tree.addTopLevelItem(item)


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

class ClusterView(QWidget):
    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._nodes: list[dict] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tb_w, tb = build_toolbar("Cluster Distribution")

        # Projection selector (insert before the stretch)
        tb.insertWidget(tb.count() - 1, QLabel("Projection:"))
        self.proj_combo = QComboBox()
        self.proj_combo.addItems(["PCA", "t-SNE", "First 2 Dims"])
        self.proj_combo.setCurrentText("First 2 Dims")
        self.proj_combo.currentTextChanged.connect(self._rebuild)
        tb.insertWidget(tb.count() - 1, self.proj_combo)

        tb.insertWidget(tb.count() - 1, QLabel("K:"))
        self.k_slider = QSlider(Qt.Horizontal)
        self.k_slider.setRange(2, 12)
        self.k_slider.setValue(5)
        self.k_slider.setFixedWidth(80)
        self.k_slider.valueChanged.connect(self._rebuild)
        tb.insertWidget(tb.count() - 1, self.k_slider)
        self.k_label = QLabel("5")
        self.k_label.setStyleSheet(f"color: {Colors.ACCENT}; font-weight: 700;")
        tb.insertWidget(tb.count() - 1, self.k_label)

        layout.addWidget(tb_w)

        splitter = QSplitter(Qt.Horizontal)
        self.canvas = ClusterCanvas()
        splitter.addWidget(self.canvas)
        self.stats = ClusterStatsPanel()
        splitter.addWidget(self.stats)
        splitter.setSizes([700, 280])
        layout.addWidget(splitter, stretch=1)

        self.setStyleSheet(f"background-color: {Colors.BG};")

    def load_nodes(self, nodes: list[dict]):
        self._nodes = nodes
        self._rebuild()

    def _rebuild(self):
        if not self._nodes:
            return
        self.k_label.setText(str(self.k_slider.value()))

        vectors = []
        for n in self._nodes:
            v = n.get("vector", n.get("position", []))
            vectors.append(v[:min(len(v), 64)] if v else [0.0])
        max_len = max(len(v) for v in vectors)
        mat = np.zeros((len(vectors), max_len), dtype=np.float32)
        for i, v in enumerate(vectors):
            mat[i, :len(v)] = v[:max_len]

        proj = self.proj_combo.currentText()
        if proj == "First 2 Dims":
            positions = mat[:, :2]
        elif proj == "PCA":
            try:
                from sklearn.decomposition import PCA
                positions = PCA(n_components=2).fit_transform(mat)
            except: positions = mat[:, :2]
        else:
            try:
                from sklearn.manifold import TSNE
                positions = TSNE(n_components=2, perplexity=min(30, len(mat) - 1)).fit_transform(mat)
            except: positions = mat[:, :2]

        positions = positions.astype(np.float32)

        k = self.k_slider.value()
        try:
            from sklearn.cluster import KMeans
            labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(mat)
        except:
            labels = np.digitize(mat[:, 0], np.linspace(mat[:, 0].min(), mat[:, 0].max(), k)) - 1

        connections = self._cluster_connections(labels)
        self.canvas.set_data(positions, labels, connections)

        centroids = np.zeros((k, 2))
        covs = np.zeros((k, 2, 2))
        for c in range(k):
            mask = labels == c
            if mask.any():
                pts = positions[mask]
                centroids[c] = pts.mean(axis=0)
                covs[c] = np.cov(pts.T) if len(pts) > 1 else np.eye(2) * 0.01
        self.stats.update_stats(labels, centroids, covs)

    def _cluster_connections(self, labels):
        n_clusters = int(labels.max()) + 1
        affinity = np.zeros((n_clusters, n_clusters))
        counts = np.zeros((n_clusters, n_clusters))
        id_to_idx = {n.get("id", str(i)): i for i, n in enumerate(self._nodes)}
        for i, node in enumerate(self._nodes):
            ci = labels[i]
            for conn in node.get("connections", []):
                j = id_to_idx.get(conn.get("id"))
                if j is not None and j < len(labels):
                    affinity[ci, labels[j]] += conn.get("score", 0)
                    counts[ci, labels[j]] += 1
        connections = []
        for i in range(n_clusters):
            for j in range(i + 1, n_clusters):
                if counts[i, j] > 0:
                    connections.append({"source": i, "target": j,
                                        "score": affinity[i, j] / counts[i, j]})
        return connections
