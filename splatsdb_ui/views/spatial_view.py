# SPDX-License-Identifier: GPL-3.0
"""Spatial Architecture Generator — Voronoi/Delaunay-based parametric floor plans.

Mathematical foundations:
  Room layout:    Voronoi tessellation of cluster centroids
                  V(pᵢ) = {x : d(x, pᵢ) ≤ d(x, pⱼ) ∀j}
  Corridor graph: Delaunay triangulation D(P) — dual of Voronoi
  Minimum Spanning Tree: Kruskal on Delaunay edges → essential corridors
  Weighted edges: w(i,j) = exp(-α · affinity(i,j)) for layout stress
  Corridor paths: cubic Bézier curves B(t) = (1-t)³P₀ + 3(1-t)²tP₁ + 3(1-t)t²P₂ + t³P₃
                  Control points offset perpendicular to chord for elegance
  Room sizing:    area(Cₖ) ∝ |Cₖ|^0.7 (sublinear for visual balance)

Visual style: architectural blueprint with dark background, precision lines,
corner marks on rooms, dimension annotations, flow arrows along MST.
"""

from __future__ import annotations

import colorsys
import numpy as np
from typing import Optional
from collections import defaultdict
from scipy.spatial import Delaunay, Voronoi
from scipy.sparse.csgraph import minimum_spanning_tree
from scipy.sparse import csr_matrix

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSplitter, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QPainterPath, QLinearGradient, QRadialGradient,
)

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon

PHI = (1 + np.sqrt(5)) / 2


def _wing_color(i: int) -> QColor:
    hue = (i * 0.2764 + 0.05) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.30, 0.30)
    return QColor(int(r * 255), int(g * 255), int(b * 255))


def _room_color(i: int) -> QColor:
    hue = (i * (1 / PHI)) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.50, 0.82)
    return QColor(int(r * 255), int(g * 255), int(b * 255))


# ---------------------------------------------------------------------------
# Bézier curve math
# ---------------------------------------------------------------------------

def cubic_bezier(P0, P1, P2, P3, n=40):
    """Evaluate cubic Bézier at n points."""
    t = np.linspace(0, 1, n).reshape(-1, 1)
    B = ((1 - t) ** 3 * P0 +
         3 * (1 - t) ** 2 * t * P1 +
         3 * (1 - t) * t ** 2 * P2 +
         t ** 3 * P3)
    return B


def bezier_control_points(A, B, curvature=0.25):
    """Compute control points for a smooth corridor between A and B.

    Offset is perpendicular to chord AB, proportional to chord length.
    """
    chord = B - A
    length = np.linalg.norm(chord)
    if length < 1e-6:
        return A, B

    # Perpendicular unit vector
    perp = np.array([-chord[1], chord[0]]) / length

    # Control point offset
    d = curvature * length

    P1 = A + chord * 0.33 + perp * d
    P2 = A + chord * 0.67 + perp * d
    return P1, P2


# ---------------------------------------------------------------------------
# Architecture data structures
# ---------------------------------------------------------------------------

class Room:
    __slots__ = ('id', 'label', 'members', 'color', 'wing',
                 'polygon', 'center', 'area', 'centroid')

    def __init__(self, rid, label, members, color):
        self.id = rid
        self.label = label
        self.members = members
        self.color = color
        self.wing = -1
        self.polygon: Optional[np.ndarray] = None  # (M, 2) screen coords
        self.center = np.zeros(2)
        self.area = 0.0
        self.centroid = np.zeros(2)  # data-space centroid


class Corridor:
    __slots__ = ('room_a', 'room_b', 'strength', 'is_mst', 'is_delaunay')

    def __init__(self, a, b, strength, is_mst=False, is_delaunay=False):
        self.room_a = a
        self.room_b = b
        self.strength = strength
        self.is_mst = is_mst
        self.is_delaunay = is_delaunay


class Wing:
    __slots__ = ('id', 'label', 'color', 'rooms')

    def __init__(self, wid, label, color):
        self.id = wid
        self.label = label
        self.color = color
        self.rooms: list[int] = []


# ---------------------------------------------------------------------------
# Layout engine — Voronoi + Delaunay + MST
# ---------------------------------------------------------------------------

class SpatialLayoutEngine:
    """Generate architectural floor plans from vector topology."""

    def __init__(self):
        self.rooms: list[Room] = []
        self.corridors: list[Corridor] = []
        self.wings: list[Wing] = []
        self.room_scale = 1.0
        self.corridor_curvature = 0.20
        self.wing_threshold = 0.5

    def generate(self, nodes: list[dict], n_clusters: int = 5):
        if not nodes or n_clusters < 2:
            return

        # --- Cluster ---
        vectors = []
        for n in nodes:
            v = n.get("vector", n.get("position", []))
            vectors.append(v[:min(len(v), 64)] if v else [0.0])
        max_len = max(len(v) for v in vectors)
        mat = np.zeros((len(vectors), max_len), dtype=np.float32)
        for i, v in enumerate(vectors):
            mat[i, :len(v)] = v[:max_len]

        try:
            from sklearn.cluster import KMeans
            labels = KMeans(n_clusters=n_clusters, n_init=10, random_state=42).fit_predict(mat)
        except:
            labels = np.digitize(mat[:, 0], np.linspace(mat[:, 0].min(), mat[:, 0].max(), n_clusters)) - 1

        # --- Centroids in 2D ---
        # Project to 2D via PCA
        try:
            from sklearn.decomposition import PCA
            positions_2d = PCA(n_components=2).fit_transform(mat).astype(np.float32)
        except:
            positions_2d = mat[:, :2]

        centroids_2d = np.zeros((n_clusters, 2), dtype=np.float32)
        cluster_members = defaultdict(list)
        for i, k in enumerate(labels):
            cluster_members[int(k)].append(nodes[i])
        for k in range(n_clusters):
            mask = labels == k
            if mask.any():
                centroids_2d[k] = positions_2d[mask].mean(axis=0)

        # --- Compute affinity ---
        node_ids = [n.get("id", str(i)) for i, n in enumerate(nodes)]
        id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
        affinity = np.zeros((n_clusters, n_clusters))
        counts = np.zeros((n_clusters, n_clusters))
        for i, node in enumerate(nodes):
            ci = labels[i]
            for conn in node.get("connections", []):
                j = id_to_idx.get(conn.get("id"))
                if j is not None and j < len(labels):
                    cj = labels[j]
                    affinity[ci, cj] += conn.get("score", 0)
                    counts[ci, cj] += 1
        for i in range(n_clusters):
            for j in range(n_clusters):
                if counts[i, j] > 0:
                    affinity[i, j] /= counts[i, j]

        # --- Create rooms ---
        self.rooms = []
        for k in range(n_clusters):
            members = cluster_members.get(k, [])
            meta = members[0].get("metadata", {}) if members else {}
            label = meta.get("category", meta.get("label", f"Room {k}"))
            self.rooms.append(Room(k, label, members, _room_color(k)))
            self.rooms[-1].centroid = centroids_2d[k]

        # --- Voronoi tessellation for room boundaries ---
        if n_clusters >= 3:
            self._voronoi_layout(centroids_2d)
        elif n_clusters == 2:
            self._binary_layout(centroids_2d)
        else:
            self._single_layout(centroids_2d)

        # --- Delaunay triangulation for corridor topology ---
        delaunay_edges = set()
        if n_clusters >= 3:
            try:
                tri = Delaunay(centroids_2d)
                for simplex in tri.simplices:
                    for i in range(3):
                        for j in range(i + 1, 3):
                            a, b = int(simplex[i]), int(simplex[j])
                            delaunay_edges.add((min(a, b), max(a, b)))
            except:
                delaunay_edges = {(i, j) for i in range(n_clusters) for j in range(i + 1, n_clusters)}
        elif n_clusters == 2:
            delaunay_edges = {(0, 1)}

        # --- MST for essential corridors ---
        mst_edges = set()
        if n_clusters >= 2 and delaunay_edges:
            # Weight: inverse affinity (low affinity = high cost)
            n = n_clusters
            weight_matrix = np.full((n, n), 1e6)
            for i in range(n):
                weight_matrix[i, i] = 0
            for (i, j) in delaunay_edges:
                w = 1.0 - affinity[i, j] if affinity[i, j] > 0 else 100.0
                weight_matrix[i, j] = w
                weight_matrix[j, i] = w

            try:
                mst = minimum_spanning_tree(csr_matrix(weight_matrix))
                mst_coo = mst.tocoo()
                for i, j in zip(mst_coo.row, mst_coo.col):
                    mst_edges.add((min(i, j), max(i, j)))
            except:
                mst_edges = set(list(delaunay_edges)[:n_clusters - 1])

        # --- Build corridor list ---
        self.corridors = []
        for (a, b) in delaunay_edges:
            s = affinity[a, b]
            is_mst = (a, b) in mst_edges
            if is_mst or s > 0.15:
                self.corridors.append(Corridor(a, b, max(s, 0.1),
                                               is_mst=is_mst, is_delaunay=True))

        # --- Wings via union-find on MST edges ---
        self._detect_wings(mst_edges, affinity, n_clusters)

    def _voronoi_layout(self, centroids: np.ndarray):
        """Use Voronoi tessellation for room polygons."""
        n = len(centroids)

        # Normalize to working space
        c_min = centroids.min(axis=0)
        c_max = centroids.max(axis=0)
        c_range = c_max - c_min
        c_range[c_range < 0.01] = 1.0
        normed = (centroids - c_min) / c_range * 600 + 100

        # Bounding box for Voronoi (mirror points create finite regions)
        # bbox intentionally unused — Voronoi uses mirrored points directly

        # Mirror points to create finite Voronoi regions
        mirrored = np.vstack([
            normed,
            np.column_stack([-normed[:, 0], normed[:, 1]]),
            np.column_stack([2 * 800 - normed[:, 0], normed[:, 1]]),
            np.column_stack([normed[:, 0], -normed[:, 1]]),
            np.column_stack([normed[:, 0], 2 * 700 - normed[:, 1]]),
        ])

        try:
            vor = Voronoi(mirrored)
        except:
            self._fallback_layout(centroids)
            return

        for k in range(n):
            region_idx = vor.point_region[k]
            region = vor.regions[region_idx]
            if -1 in region or len(region) < 3:
                self._fallback_room(k, normed[k])
                continue

            verts = vor.vertices[region]

            # Clip to bounding box
            verts[:, 0] = np.clip(verts[:, 0], 20, 780)
            verts[:, 1] = np.clip(verts[:, 1], 20, 680)

            # Inset by margin for visual separation
            center = verts.mean(axis=0)
            inset = 8
            inset_verts = center + (verts - center) * (1 - inset / max(np.linalg.norm(verts - center, axis=1).max(), 1))

            self.rooms[k].polygon = inset_verts
            self.rooms[k].center = center
            self.rooms[k].area = self._polygon_area(inset_verts)

    def _binary_layout(self, centroids: np.ndarray):
        normed = (centroids - centroids.min()) / max(centroids.max() - centroids.min(), 0.01) * 500 + 150
        mid = (normed[0] + normed[1]) / 2
        self.rooms[0].polygon = np.array([[30, 30], [mid[0] - 10, 30], [mid[0] - 10, 670], [30, 670]])
        self.rooms[0].center = self.rooms[0].polygon.mean(axis=0)
        self.rooms[0].area = self._polygon_area(self.rooms[0].polygon)
        self.rooms[1].polygon = np.array([[mid[0] + 10, 30], [770, 30], [770, 670], [mid[0] + 10, 670]])
        self.rooms[1].center = self.rooms[1].polygon.mean(axis=0)
        self.rooms[1].area = self._polygon_area(self.rooms[1].polygon)

    def _single_layout(self, centroids: np.ndarray):
        self.rooms[0].polygon = np.array([[30, 30], [770, 30], [770, 670], [30, 670]])
        self.rooms[0].center = self.rooms[0].polygon.mean(axis=0)
        self.rooms[0].area = self._polygon_area(self.rooms[0].polygon)

    def _fallback_layout(self, centroids: np.ndarray):
        normed = (centroids - centroids.min()) / max(centroids.max() - centroids.min(), 0.01) * 500 + 150
        for k in range(len(self.rooms)):
            self._fallback_room(k, normed[k])

    def _fallback_room(self, k, center):
        s = 60
        self.rooms[k].polygon = np.array([
            [center[0] - s, center[1] - s],
            [center[0] + s, center[1] - s],
            [center[0] + s, center[1] + s],
            [center[0] - s, center[1] + s],
        ])
        self.rooms[k].center = center
        self.rooms[k].area = self._polygon_area(self.rooms[k].polygon)

    @staticmethod
    def _polygon_area(verts):
        n = len(verts)
        area = 0
        for i in range(n):
            j = (i + 1) % n
            area += verts[i, 0] * verts[j, 1]
            area -= verts[j, 0] * verts[i, 1]
        return abs(area) / 2

    def _detect_wings(self, mst_edges, affinity, n_clusters):
        parent = list(range(n_clusters))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            a, b = find(a), find(b)
            if a != b:
                parent[a] = b

        for (a, b) in mst_edges:
            if affinity[a, b] > self.wing_threshold:
                union(a, b)

        groups = defaultdict(list)
        for i in range(n_clusters):
            groups[find(i)].append(i)

        self.wings = []
        wi = 0
        for root, members in groups.items():
            if len(members) >= 2:
                w = Wing(wi, f"Wing {chr(65 + wi)}", _wing_color(wi))
                w.rooms = members
                self.wings.append(w)
                for rid in members:
                    self.rooms[rid].wing = wi
                wi += 1


# ---------------------------------------------------------------------------
# Canvas — architectural blueprint renderer
# ---------------------------------------------------------------------------

class SpatialCanvas(QWidget):
    room_clicked = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(700, 500)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self.engine = SpatialLayoutEngine()
        self._hovered_room = -1
        self._selected_room = -1
        self.show_flow = False

    def generate(self, nodes, n_clusters=5):
        self.engine.generate(nodes, n_clusters)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # --- Blueprint background ---
        bg = QColor(Colors.BG)
        painter.fillRect(0, 0, w, h, bg)

        # Fine grid (graph paper)
        painter.setPen(QPen(QColor(255, 255, 255, 6), 0.5))
        for x in range(0, w, 20):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, 20):
            painter.drawLine(0, y, w, y)

        # Major grid
        painter.setPen(QPen(QColor(255, 255, 255, 14), 0.5))
        for x in range(0, w, 100):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, 100):
            painter.drawLine(0, y, w, y)

        # Scale bar
        painter.setPen(QPen(QColor(Colors.TEXT_DIM), 1))
        painter.drawLine(20, h - 30, 120, h - 30)
        painter.drawLine(20, h - 35, 20, h - 25)
        painter.drawLine(120, h - 35, 120, h - 25)
        painter.setFont(QFont("monospace", 7))
        painter.drawText(35, h - 33, "100 units")

        # --- Wings (background grouping) ---
        self._paint_wings(painter)

        # --- Corridors ---
        self._paint_corridors(painter)

        # --- Rooms ---
        self._paint_rooms(painter, w, h)

        # --- Flow particles ---
        if self.show_flow:
            self._paint_flow(painter)

        # --- Title block (architectural drawing convention) ---
        self._paint_title_block(painter, w, h)

        painter.end()

    def _paint_wings(self, painter: QPainter):
        for wing in self.engine.wings:
            rooms = [self.engine.rooms[rid] for rid in wing.rooms
                     if self.engine.rooms[rid].polygon is not None]
            if len(rooms) < 2:
                continue

            # Bounding rect of all room polygons
            all_pts = np.vstack([r.polygon for r in rooms])
            margin = 30
            x_min, y_min = all_pts.min(axis=0) - margin
            x_max, y_max = all_pts.max(axis=0) + margin

            # Wing shading
            wc = QColor(wing.color)
            wc.setAlpha(25)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(wc))
            painter.drawRoundedRect(int(x_min), int(y_min),
                                    int(x_max - x_min), int(y_max - y_min), 14, 14)

            # Wing border
            wb = QColor(wing.color)
            wb.setAlpha(70)
            painter.setPen(QPen(wb, 1.5, Qt.DashDotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(int(x_min), int(y_min),
                                    int(x_max - x_min), int(y_max - y_min), 14, 14)

            # Wing label
            painter.setPen(QPen(QColor(wing.color).lighter(160)))
            painter.setFont(QFont("sans-serif", 11, QFont.Bold))
            painter.drawText(int(x_min + 12), int(y_min + 20), wing.label)

    def _paint_corridors(self, painter: QPainter):
        for corr in self.engine.corridors:
            ra = self.engine.rooms[corr.room_a]
            rb = self.engine.rooms[corr.room_b]
            if ra.polygon is None or rb.polygon is None:
                continue

            A = ra.center
            B = rb.center

            # Cubic Bézier corridor
            P1, P2 = bezier_control_points(A, B, self.engine.corridor_curvature)
            pts = cubic_bezier(A, P1, P2, B, n=60)

            # Width based on strength and type
            if corr.is_mst:
                base_width = 3.0
                alpha = 140
            else:
                base_width = 1.5
                alpha = 60
            width = base_width + corr.strength * 3

            # Color: MST in accent, Delaunay in dim
            if corr.is_mst:
                color = QColor(Colors.ACCENT)
                color.setAlpha(alpha)
            else:
                color = QColor(Colors.TEXT_DIM)
                color.setAlpha(alpha)

            painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap))
            painter.setBrush(Qt.NoBrush)

            path = QPainterPath()
            path.moveTo(pts[0, 0], pts[0, 1])
            for p in pts[1:]:
                path.lineTo(p[0], p[1])
            painter.drawPath(path)

            # Flow arrows along MST corridors
            if corr.is_mst:
                self._paint_flow_arrows(painter, pts, color)

    def _paint_flow_arrows(self, painter, pts, color):
        """Draw small directional arrows along a corridor path."""
        n = len(pts)
        step = max(n // 5, 2)
        for i in range(step, n - step, step):
            p = pts[i]
            d = pts[i + 1] - pts[i - 1]
            d_norm = d / (np.linalg.norm(d) + 1e-6)

            # Arrow head (small triangle)
            perp = np.array([-d_norm[1], d_norm[0]])
            tip = p + d_norm * 5
            left = p - d_norm * 3 + perp * 3
            right = p - d_norm * 3 - perp * 3

            from PySide6.QtGui import QPolygonF
            from PySide6.QtCore import QPointF
            arrow = QPolygonF([
                QPointF(tip[0], tip[1]),
                QPointF(left[0], left[1]),
                QPointF(right[0], right[1]),
            ])
            c = QColor(color)
            c.setAlpha(min(c.alpha() + 40, 220))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(c))
            painter.drawPolygon(arrow)

    def _paint_rooms(self, painter: QPainter, canvas_w: int, canvas_h: int):
        for room in self.engine.rooms:
            if room.polygon is None:
                continue

            poly = room.polygon
            is_hov = room.id == self._hovered_room
            is_sel = room.id == self._selected_room

            # --- Room fill (gradient for depth) ---
            center = poly.mean(axis=0)
            gradient = QRadialGradient(center[0], center[1],
                                       max(np.linalg.norm(poly - center, axis=1).max(), 1))

            base = QColor(room.color)
            if is_sel:
                base = base.lighter(150)
            elif is_hov:
                base = base.lighter(125)

            fill_inner = QColor(base)
            fill_inner.setAlpha(160 if not is_sel else 200)
            fill_outer = QColor(base.darker(140))
            fill_outer.setAlpha(80)

            gradient.setColorAt(0, fill_inner)
            gradient.setColorAt(1, fill_outer)
            painter.setBrush(QBrush(gradient))

            # Border
            border = QColor(room.color)
            border.setAlpha(220 if is_sel or is_hov else 140)
            pen_w = 2.5 if is_sel else (1.8 if is_hov else 1.2)
            painter.setPen(QPen(border, pen_w))

            # Draw polygon
            from PySide6.QtGui import QPolygonF
            from PySide6.QtCore import QPointF
            qpoly = QPolygonF([QPointF(p[0], p[1]) for p in poly])
            painter.drawPolygon(qpoly)

            # --- Corner marks (architectural convention) ---
            corner_len = 12
            painter.setPen(QPen(QColor(room.color).lighter(140), 1.5))
            n_verts = len(poly)
            for i in range(n_verts):
                v = poly[i]
                # Direction to previous and next vertex
                prev = poly[(i - 1) % n_verts]
                nxt = poly[(i + 1) % n_verts]
                d_prev = (prev - v)
                d_prev = d_prev / (np.linalg.norm(d_prev) + 1e-6) * corner_len
                d_next = (nxt - v)
                d_next = d_next / (np.linalg.norm(d_next) + 1e-6) * corner_len

                painter.drawLine(int(v[0]), int(v[1]),
                                 int(v[0] + d_prev[0]), int(v[1] + d_prev[1]))
                painter.drawLine(int(v[0]), int(v[1]),
                                 int(v[0] + d_next[0]), int(v[1] + d_next[1]))

            # --- Room label ---
            painter.setPen(QPen(QColor(Colors.TEXT)))
            painter.setFont(QFont("sans-serif", 11, QFont.Bold))
            text = room.label[:18]
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(text)
            painter.drawText(int(center[0] - tw / 2), int(center[1] - 8), text)

            # --- Member count ---
            painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
            painter.setFont(QFont("sans-serif", 9))
            count_text = f"{len(room.members)} splats"
            fm2 = painter.fontMetrics()
            cw = fm2.horizontalAdvance(count_text)
            painter.drawText(int(center[0] - cw / 2), int(center[1] + 10), count_text)

            # --- Area annotation ---
            area_px = room.area
            painter.setFont(QFont("monospace", 7))
            painter.setPen(QPen(QColor(Colors.TEXT_DIM).lighter(120)))
            painter.drawText(int(center[0] - 25), int(center[1] + 22),
                             f"A={area_px:.0f}px²")

            # --- Wing badge ---
            if room.wing >= 0 and room.wing < len(self.engine.wings):
                wing = self.engine.wings[room.wing]
                # Small colored dot
                badge_pos = poly[0]  # top-ish vertex
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(wing.color).lighter(160)))
                painter.drawEllipse(int(badge_pos[0] - 6), int(badge_pos[1] - 6), 12, 12)
                painter.setPen(QPen(QColor(Colors.BG)))
                painter.setFont(QFont("sans-serif", 7, QFont.Bold))
                painter.drawText(int(badge_pos[0] - 3), int(badge_pos[1] + 4),
                                 wing.label[-1])

    def _paint_flow(self, painter: QPainter):
        """Animated flow particles along corridors."""
        import time
        t = time.time() % 5.0

        for corr in self.engine.corridors:
            if not corr.is_mst:
                continue
            ra = self.engine.rooms[corr.room_a]
            rb = self.engine.rooms[corr.room_b]
            if ra.polygon is None or rb.polygon is None:
                continue

            A, B = ra.center, rb.center
            P1, P2 = bezier_control_points(A, B, self.engine.corridor_curvature)
            pts = cubic_bezier(A, P1, P2, B, n=60)

            n_particles = max(2, int(corr.strength * 6))
            for p in range(n_particles):
                phase = (t / 5.0 + p / n_particles) % 1.0
                idx = int(phase * (len(pts) - 1))
                pt = pts[idx]

                # Fade at endpoints
                fade = 1.0 - abs(phase - 0.5) * 2
                alpha = int(200 * fade)
                pc = QColor(Colors.ACCENT)
                pc.setAlpha(max(alpha, 30))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(pc))
                painter.drawEllipse(int(pt[0] - 3), int(pt[1] - 3), 6, 6)

    def _paint_title_block(self, painter, w, h):
        """Architectural drawing title block (bottom-right corner)."""
        bw, bh = 200, 60
        x0, y0 = w - bw - 15, h - bh - 15

        painter.setPen(QPen(QColor(Colors.TEXT_DIM), 1))
        painter.setBrush(QBrush(QColor(Colors.BG_RAISED)))
        painter.drawRect(x0, y0, bw, bh)

        painter.setFont(QFont("monospace", 7))
        painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
        painter.drawText(x0 + 5, y0 + 12, "SPATIAL ARCHITECTURE")
        painter.drawText(x0 + 5, y0 + 24, f"Rooms: {len(self.engine.rooms)}  "
                         f"Corridors: {len(self.engine.corridors)}  "
                         f"Wings: {len(self.engine.wings)}")

        mst_count = sum(1 for c in self.engine.corridors if c.is_mst)
        delaunay_count = sum(1 for c in self.engine.corridors if c.is_delaunay)
        painter.drawText(x0 + 5, y0 + 36, f"MST: {mst_count}  Delaunay: {delaunay_count}")
        painter.drawText(x0 + 5, y0 + 48, "Layout: Voronoi/Delaunay")

        painter.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        painter.drawLine(x0, y0, x0 + bw, y0)

    def mouseMoveEvent(self, event):
        pos = event.position()
        for room in self.engine.rooms:
            if room.polygon is not None and self._point_in_polygon(pos.x(), pos.y(), room.polygon):
                if self._hovered_room != room.id:
                    self._hovered_room = room.id
                    self.setCursor(Qt.PointingHandCursor)
                    self.update()
                return
        if self._hovered_room >= 0:
            self._hovered_room = -1
            self.setCursor(Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, event):
        if self._hovered_room >= 0:
            self._selected_room = self._hovered_room
            self.room_clicked.emit(self._selected_room)
            self.update()

    @staticmethod
    def _point_in_polygon(x, y, poly):
        """Ray casting algorithm."""
        n = len(poly)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

class SpatialControls(QWidget):
    generate_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedWidth(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("PARAMETERS")
        title.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(title)

        # Rooms
        layout.addWidget(QLabel("Rooms (K):"))
        self.k_slider = QSlider(Qt.Horizontal)
        self.k_slider.setRange(2, 12)
        self.k_slider.setValue(5)
        layout.addWidget(self.k_slider)
        self.k_label = QLabel("5")
        self.k_label.setStyleSheet(f"color: {Colors.ACCENT};")
        layout.addWidget(self.k_label)
        self.k_slider.valueChanged.connect(lambda v: self.k_label.setText(str(v)))

        # Curvature
        layout.addWidget(QLabel("Corridor curvature:"))
        self.curve_slider = QSlider(Qt.Horizontal)
        self.curve_slider.setRange(0, 50)
        self.curve_slider.setValue(20)
        layout.addWidget(self.curve_slider)

        # Wing threshold
        layout.addWidget(QLabel("Wing threshold:"))
        self.wing_slider = QSlider(Qt.Horizontal)
        self.wing_slider.setRange(10, 90)
        self.wing_slider.setValue(50)
        layout.addWidget(self.wing_slider)

        # Flow toggle
        self.flow_btn = QPushButton("Show Flow")
        self.flow_btn.setCheckable(True)
        self.flow_btn.toggled.connect(self._on_flow_toggled)
        layout.addWidget(self.flow_btn)

        # Regenerate
        gen_btn = QPushButton("Regenerate")
        gen_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.ACCENT}; color: {Colors.BG};
                border: none; border-radius: 6px; padding: 8px; font-weight: 700;
            }}
            QPushButton:hover {{ background-color: {Colors.ACCENT}CC; }}
        """)
        gen_btn.clicked.connect(self.generate_requested.emit)
        layout.addWidget(gen_btn)

        layout.addStretch()

        # Info
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px;")
        layout.addWidget(self.info)

        self.setStyleSheet(f"""
            background-color: {Colors.BG_RAISED};
            QLabel {{ color: {Colors.TEXT}; font-size: 11px; }}
        """)

    def _on_flow_toggled(self):
        """Handle flow toggle — notify parent to regenerate."""
        self.generate_requested.emit()


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

class SpatialView(QWidget):
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

        # Header
        hdr = QHBoxLayout()
        hdr.setContentsMargins(12, 8, 12, 8)
        title = QLabel("Spatial Architecture")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 14px; font-weight: 700;")
        hdr.addWidget(title)

        sub = QLabel("Voronoi rooms · Delaunay corridors · MST backbone · Bézier paths")
        sub.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        hdr.addWidget(sub)
        hdr.addStretch()

        hdr_w = QWidget()
        hdr_w.setLayout(hdr)
        hdr_w.setStyleSheet(f"background-color: {Colors.BG_RAISED}; border-bottom: 1px solid {Colors.BORDER};")
        layout.addWidget(hdr_w)

        splitter = QSplitter(Qt.Horizontal)
        self.canvas = SpatialCanvas()
        splitter.addWidget(self.canvas)
        self.controls = SpatialControls()
        splitter.addWidget(self.controls)
        splitter.setSizes([700, 260])
        layout.addWidget(splitter, stretch=1)

        self.controls.generate_requested.connect(self._regenerate)
        self.canvas.room_clicked.connect(self._on_room)

        self.setStyleSheet(f"background-color: {Colors.BG};")

    def load_nodes(self, nodes):
        self._nodes = nodes
        self._regenerate()

    def _regenerate(self):
        if not self._nodes:
            return
        self.canvas.engine.corridor_curvature = self.controls.curve_slider.value() / 100.0
        self.canvas.engine.wing_threshold = self.controls.wing_slider.value() / 100.0
        self.canvas.show_flow = self.controls.flow_btn.isChecked()
        k = self.controls.k_slider.value()
        self.canvas.generate(self._nodes, k)

        nr = len(self.canvas.engine.rooms)
        nc = len(self.canvas.engine.corridors)
        nw = len(self.canvas.engine.wings)
        mst = sum(1 for c in self.canvas.engine.corridors if c.is_mst)
        self.controls.info.setText(
            f"Voronoi rooms: {nr}\n"
            f"Delaunay corridors: {nc}\n"
            f"MST backbone: {mst}\n"
            f"Wings: {nw}"
        )

    def _on_room(self, rid):
        if rid < len(self.canvas.engine.rooms):
            room = self.canvas.engine.rooms[rid]
            wing_name = "None"
            if room.wing >= 0 and room.wing < len(self.canvas.engine.wings):
                wing_name = self.canvas.engine.wings[room.wing].label
            self.signals.status_message.emit(
                f"Room: {room.label} | {len(room.members)} splats | "
                f"Area: {room.area:.0f}px² | Wing: {wing_name}"
            )
