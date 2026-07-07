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
import numpy as np
from typing import Optional
from collections import defaultdict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSplitter, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QSizePolicy, QFrame,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QPainterPath, QImage, QLinearGradient,
)

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon

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


def _cluster_qcolor(k: int) -> QColor:
    return QColor(*_COLORS[k % len(_COLORS)])


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

        for pt in pts:
            dx = xx - pt[0]
            dy = yy - pt[1]
            r2 = (dx ** 2 + dy ** 2) / (h ** 2)
            densities[k] += np.exp(-0.5 * r2)
        densities[k] /= n_k

    return xx, yy, densities, (x_min, x_max, y_min, y_max)


# ---------------------------------------------------------------------------
# Marching squares contour extraction
# ---------------------------------------------------------------------------

def extract_contours(density: np.ndarray, threshold: float):
    """Extract iso-density contour paths at given threshold using marching squares.

    Returns list of QPainterPath objects.
    """
    h, w = density.shape
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
        self._contour_paths: list = []  # [(color, width, path), ...]
        self._voronoi_edge_pts: list = []
        self._extents: tuple = (0, 1, 0, 1)
        self._grid_res: int = 150

        self._hovered_cluster: int = -1
        self._selected_cluster: int = -1

        self.show_contours = True
        self.show_voronoi = True
        self.show_sigma = True
        self.show_points = True
        self.show_density = True

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

        self.update()

    def _build_density_image(self, densities: np.ndarray):
        """Render KDE density as a QImage with topographic banding."""
        grid_res = self._grid_res
        img = QImage(grid_res, grid_res, QImage.Format_ARGB32)

        # Dominant cluster per pixel + total density
        dominant = np.argmax(densities, axis=0)
        max_density = np.max(densities, axis=0)

        # Global max for normalization
        d_max = max_density.max()
        if d_max < 1e-10:
            d_max = 1.0

        # Topographic contour bands at golden-ratio-spaced levels
        n_bands = 6
        band_levels = []
        level = 1.0
        for _ in range(n_bands):
            band_levels.append(level)
            level /= PHI  # Golden ratio spacing

        for y in range(grid_res):
            for x in range(grid_res):
                k = dominant[y, x]
                d = max_density[y, x] / d_max

                base_color = _cluster_qcolor(k)

                # Determine band index
                band = 0
                for b, bl in enumerate(band_levels):
                    if d >= bl:
                        band = b
                        break

                # Brightness: increase with band level (higher density = brighter)
                brightness = 0.15 + 0.12 * band
                alpha = int(min(brightness * 255, 180))

                # Mix color with darkness
                r = int(base_color.red() * brightness)
                g = int(base_color.green() * brightness)
                b_val = int(base_color.blue() * brightness)

                # Slight band boundary darkening for topographic effect
                for bl in band_levels:
                    rel_dist = abs(d - bl) / max(bl, 0.01)
                    if rel_dist < 0.03:
                        r = int(r * 0.6)
                        g = int(g * 0.6)
                        b_val = int(b_val * 0.6)
                        break

                img.setPixelColor(x, y, QColor(r, g, b_val, alpha))

        self._density_image = img

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

    def paintEvent(self, event):
        if self._positions is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        painter.fillRect(0, 0, w, h, QColor(Colors.BG))

        # Subtle graph paper grid
        painter.setPen(QPen(QColor(255, 255, 255, 8), 0.5))
        for x in range(0, w, 25):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, 25):
            painter.drawLine(0, y, w, y)

        # Density heatmap
        if self.show_density and self._density_image is not None:
            margin = 50
            scaled = self._density_image.scaled(w - 2 * margin, h - 2 * margin)
            painter.drawImage(margin, margin, scaled)

        # Voronoi boundaries
        if self.show_voronoi and self._voronoi_edge_pts:
            painter.setPen(QPen(QColor(255, 255, 255, 25), 1.5))
            for gx, gy in self._voronoi_edge_pts:
                sx, sy = self._grid_to_screen(gx, gy)
                painter.drawPoint(int(sx), int(sy))

        # Contour lines
        if self.show_contours:
            for color, level, path in self._contour_paths:
                # Scale path from grid coords to screen coords
                screen_path = QPainterPath()
                # Recreate path with screen coords
                count = path.elementCount()
                for i in range(count):
                    el = path.elementAt(i)
                    sx, sy = self._grid_to_screen(el.x, el.y)
                    if i == 0 or el.type == 0:  # MoveTo
                        screen_path.moveTo(sx, sy)
                    else:
                        screen_path.lineTo(sx, sy)

                alpha = int(60 + level * 200)
                pen_color = QColor(color)
                pen_color.setAlpha(min(alpha, 220))
                width = 1.0 + level * 1.5
                painter.setPen(QPen(pen_color, width))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(screen_path)

        # Sigma ellipses
        if self.show_sigma and self._centroids is not None:
            for k in range(self._n_clusters):
                cx, cy = self._to_screen(self._centroids[k, 0], self._centroids[k, 1])
                cov = self._covariances[k]
                color = _cluster_qcolor(k)

                # Eigenvalues → sigma radii, eigenvectors → rotation
                try:
                    eigvals, eigvecs = np.linalg.eigh(cov)
                    eigvals = np.maximum(eigvals, 0.001)
                except:
                    eigvals = np.array([0.1, 0.1])
                    eigvecs = np.eye(2)

                angle = np.degrees(np.arctan2(eigvecs[1, 0], eigvecs[0, 0]))
                full_range_x = max(self._extents[1] - self._extents[0], 0.01)
                full_range_y = max(self._extents[3] - self._extents[2], 0.01)
                px_x = (w - 100) / full_range_x
                px_y = (h - 100) / full_range_y

                for sigma_mult, line_style, alpha_base in [
                    (3, Qt.DotLine, 25), (2, Qt.DashLine, 45), (1, Qt.SolidLine, 80)
                ]:
                    rx = np.sqrt(eigvals[0]) * sigma_mult * px_x
                    ry = np.sqrt(eigvals[1]) * sigma_mult * px_y

                    pen_color = QColor(color)
                    pen_color.setAlpha(alpha_base)
                    painter.setPen(QPen(pen_color, 1.2, line_style))
                    painter.setBrush(Qt.NoBrush)

                    painter.save()
                    painter.translate(cx, cy)
                    painter.rotate(-angle)
                    painter.drawEllipse(int(-rx), int(-ry), int(2 * rx), int(2 * ry))
                    painter.restore()

        # Points
        if self.show_points:
            for i in range(len(self._positions)):
                k = self._labels[i]
                sx, sy = self._to_screen(self._positions[i, 0], self._positions[i, 1])
                color = _cluster_qcolor(k)

                if k == self._hovered_cluster or k == self._selected_cluster:
                    painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
                    size = 5
                else:
                    painter.setPen(Qt.NoPen)
                    size = 3

                pc = QColor(color)
                pc.setAlpha(200)
                painter.setBrush(QBrush(pc))
                painter.drawEllipse(int(sx - size), int(sy - size), size * 2, size * 2)

        # Centroid markers
        if self._centroids is not None:
            for k in range(self._n_clusters):
                cx, cy = self._to_screen(self._centroids[k, 0], self._centroids[k, 1])
                color = _cluster_qcolor(k)
                mask = self._labels == k
                n_k = int(mask.sum())

                # Cross marker
                pen = QPen(QColor(color), 2.5)
                painter.setPen(pen)
                painter.drawLine(int(cx - 8), int(cy), int(cx + 8), int(cy))
                painter.drawLine(int(cx), int(cy - 8), int(cx), int(cy + 8))

                # Label with background
                label = f"C{k}"
                painter.setFont(QFont("monospace", 10, QFont.Bold))
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(label)
                th = fm.height()

                bg = QColor(Colors.BG)
                bg.setAlpha(220)
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(int(cx + 10), int(cy - th), tw + 8, th + 4, 4, 4)

                painter.setPen(QPen(color.lighter(130)))
                painter.drawText(int(cx + 14), int(cy - 2), label)

                painter.setFont(QFont("sans-serif", 8))
                painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
                painter.drawText(int(cx + 14), int(cy + 10), f"n={n_k}")

        # Inter-cluster arcs
        self._paint_connections(painter)

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
            # Gradient color based on score
            r = int(100 + 155 * score)
            g = int(180 * score)
            b = int(255 * (1 - score * 0.5))
            pen = QPen(QColor(r, g, b, alpha), 1.5 + score * 2)
            painter.setPen(pen)

            path = QPainterPath()
            path.moveTo(p1[0], p1[1])
            path.quadTo(mx, my, p2[0], p2[1])
            painter.drawPath(path)

            # Score label
            if score > 0.5:
                painter.setFont(QFont("monospace", 7))
                painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
                painter.drawText(int(mx - 12), int(my - 5), f"{score:.2f}")

    def mouseMoveEvent(self, event):
        if self._centroids is None:
            return
        pos = event.position()
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
        if self._hovered_cluster >= 0:
            self._selected_cluster = self._hovered_cluster
            self.cluster_clicked.emit(self._selected_cluster)
            self.update()


# ---------------------------------------------------------------------------
# Stats panel
# ---------------------------------------------------------------------------

class ClusterStatsPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("CLUSTER TOPOLOGY")
        title.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;"
        )
        layout.addWidget(title)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Cluster", "Count", "Spread", "Density"])
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setAlternatingRowColors(True)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {Colors.BG}; border: 1px solid {Colors.BORDER};
                border-radius: 8px; color: {Colors.TEXT}; font-size: 11px;
            }}
            QTreeWidget::item {{
                padding: 6px 8px; border-bottom: 1px solid {Colors.BG_RAISED};
            }}
            QHeaderView::section {{
                background-color: {Colors.BG_RAISED}; color: {Colors.TEXT_DIM};
                border: none; border-bottom: 1px solid {Colors.BORDER}; padding: 6px 8px;
                font-size: 10px; font-weight: 600; text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
        """)
        layout.addWidget(self.tree)

        # Info label
        self.info = QLabel("")
        self.info.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; padding-top: 4px;")
        layout.addWidget(self.info)

        self.setStyleSheet(f"""
            ClusterStatsPanel {{
                background-color: {Colors.BG_RAISED};
                border-left: 1px solid {Colors.BORDER};
            }}
        """)

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

        tb = QHBoxLayout()
        tb.setContentsMargins(12, 8, 12, 8)
        tb.setSpacing(10)

        title = QLabel("Cluster Distribution")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 14px; font-weight: 700;")
        tb.addWidget(title)

        tb.addWidget(QLabel("Projection:"))
        self.proj_combo = QComboBox()
        self.proj_combo.addItems(["PCA", "t-SNE", "First 2 Dims"])
        self.proj_combo.setCurrentText("First 2 Dims")
        self.proj_combo.currentTextChanged.connect(self._rebuild)
        tb.addWidget(self.proj_combo)

        tb.addWidget(QLabel("K:"))
        self.k_slider = QSlider(Qt.Horizontal)
        self.k_slider.setRange(2, 12)
        self.k_slider.setValue(5)
        self.k_slider.setFixedWidth(80)
        self.k_slider.valueChanged.connect(self._rebuild)
        tb.addWidget(self.k_slider)
        self.k_label = QLabel("5")
        self.k_label.setStyleSheet(f"color: {Colors.ACCENT}; font-weight: 700;")
        tb.addWidget(self.k_label)

        tb.addStretch()

        tb_w = QWidget()
        tb_w.setLayout(tb)
        tb_w.setStyleSheet(
            f"background-color: {Colors.BG_RAISED}; border-bottom: 1px solid {Colors.BORDER};"
        )
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
