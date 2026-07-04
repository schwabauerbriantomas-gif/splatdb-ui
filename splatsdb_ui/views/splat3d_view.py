# SPDX-License-Identifier: GPL-3.0
"""3D Gaussian Splat Explorer — QPainter-based 3D rendering.

Rendering math:
  Projection:    3D → 2D via perspective camera with azimuth/elevation rotation
  Sort order:    back-to-front by camera-space depth (painter's algorithm)
  Splat shape:   Eigendecompose Σ₂D = Q Λ Qᵀ → ellipse semi-axes √λᵢ, angle atan2(q)
  Opacity model: QRadialGradient with 3-zone stops:
                  zone 1 (0–0.3r): full opacity core
                  zone 2 (0.3–0.7r): linear falloff  
                  zone 3 (0.7–1.0r): soft Gaussian tail
  Covariance:    Σ₃D = R · diag(s²) · Rᵀ  →  project Σ₂D = Pᵥ · Σ₃D · Pᵥᵀ

Visual style: "Celestial Splat Field" — same aesthetic as Knowledge Graph.
  Deep space background, radial vignette, star dots, concentric ring halos,
  Bézier connection curves with alpha gradient, glow halos, animated drift.
"""

from __future__ import annotations

import math
import random
import numpy as np
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt, QTimer, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QRadialGradient, QLinearGradient, QPainterPath, QPolygonF,
)

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon

# ---------------------------------------------------------------------------
# Color palette — golden-ratio spaced hues
# ---------------------------------------------------------------------------

PHI = (1 + math.sqrt(5)) / 2

def _palette_color(i: int) -> QColor:
    hue = (i / PHI) % 1.0
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(hue, 0.55, 0.85)
    return QColor(int(r * 255), int(g * 255), int(b * 255))

def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
    )


# ---------------------------------------------------------------------------
# 3D Camera — perspective projection with rotation
# ---------------------------------------------------------------------------

class Camera3D:
    """Simple perspective camera with azimuth/elevation rotation."""

    def __init__(self):
        self.azimuth = 0.45    # radians
        self.elevation = 0.35
        self.distance = 45.0
        self.fov = 55.0        # degrees
        self.pan_x = 0.0
        self.pan_y = 0.0

    def project(self, point3d: np.ndarray, screen_w: int, screen_h: int) -> tuple[float, float, float]:
        """Project 3D point to 2D screen coords. Returns (sx, sy, depth)."""
        ca, sa = math.cos(self.azimuth), math.sin(self.azimuth)
        ce, se = math.cos(self.elevation), math.sin(self.elevation)

        x, y, z = point3d

        # Azimuth rotation (around Z axis)
        x1 = x * ca + z * sa
        z1 = -x * sa + z * ca
        y1 = y

        # Elevation rotation (around X axis)
        y2 = y1 * ce - z1 * se
        z2 = y1 * se + z1 * ce
        x2 = x1

        depth = z2

        # Perspective divide
        d = self.distance
        denom = max(d - depth, 0.1)
        scale = d / denom

        fov_scale = screen_w / (2 * math.tan(math.radians(self.fov / 2)))

        sx = screen_w / 2 + (x2 + self.pan_x) * scale * fov_scale / d
        sy = screen_h / 2 - (y2 + self.pan_y) * scale * fov_scale / d

        return sx, sy, depth, scale

    def project_covariance_2d(self, sigma_3d: np.ndarray) -> tuple[float, float, float]:
        """Project 3D covariance to 2D ellipse parameters.

        Returns (semi_a, semi_b, angle_deg) for the projected ellipse.
        Σ₂D = Rv · Σ₃D · Rvᵀ  → eigendecompose → semi-axes √λᵢ
        """
        ca, sa = math.cos(self.azimuth), math.sin(self.azimuth)
        ce, se = math.cos(self.elevation), math.sin(self.elevation)

        # View rotation matrix (3x3 top-left)
        Rz = np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]])
        Rx = np.array([[1, 0, 0], [0, ce, -se], [0, se, ce]])
        Rv = Rx @ Rz

        view_sigma = Rv @ sigma_3d @ Rv.T
        sigma_2d = view_sigma[:2, :2]

        try:
            eigvals, eigvecs = np.linalg.eigh(sigma_2d)
            eigvals = np.maximum(eigvals, 1e-6)
        except:
            eigvals = np.array([1.0, 1.0])
            eigvecs = np.eye(2)

        semi_a = math.sqrt(eigvals[1])
        semi_b = math.sqrt(eigvals[0])
        angle = math.degrees(math.atan2(eigvecs[1, 1], eigvecs[0, 1]))

        return semi_a, semi_b, angle


# ---------------------------------------------------------------------------
# Splat data
# ---------------------------------------------------------------------------

class SplatData:
    """Per-splat data for rendering."""

    def __init__(self, idx, position, color, scale, rotation, opacity, node_data):
        self.idx = idx
        self.position = np.array(position, dtype=np.float32)  # 3D
        self.color = color          # QColor
        self.scale = np.array(scale, dtype=np.float32)         # 3D
        self._original_scale = np.array(scale, dtype=np.float32)  # preserve for slider re-scaling
        self.rotation = rotation    # 3x3 matrix
        self.opacity = opacity      # 0–1
        self.node_data = node_data  # original node dict

        # Pre-compute 3D covariance
        S2 = np.diag(self.scale ** 2)
        self.sigma_3d = self.rotation @ S2 @ self.rotation.T

        # Screen coords (updated each frame)
        self.sx = 0.0
        self.sy = 0.0
        self.depth = 0.0
        self.proj_scale = 1.0
        self.semi_a = 0.0
        self.semi_b = 0.0
        self.angle = 0.0

        # Animation
        self.phase = random.uniform(0, math.tau)


# ---------------------------------------------------------------------------
# 3D Splat Canvas — QPainter-based rendering
# ---------------------------------------------------------------------------

class Splat3DCanvas(QWidget):
    """3D Gaussian splat explorer with QPainter rendering.

    Interactive controls:
      Left-drag: rotate camera (azimuth + elevation)
      Shift+Left-drag: pan
      Scroll: zoom
      Double-click / right-click: select splat
    """

    node_clicked = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(600, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self.camera = Camera3D()
        self._splats: list[SplatData] = []
        self._node_map: dict[str, int] = {}  # id → index
        self._connections: list[tuple[int, int, float]] = []
        self._conn_mode = "Nearest 5"

        self._hovered = -1
        self._selected = -1
        self._drag_start = None
        self._pan_start = None

        # Animation
        self._anim_time = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 FPS

        # Deterministic star field
        self._stars = []
        rng = random.Random(42)
        for _ in range(120):
            self._stars.append((
                rng.random(), rng.random(),
                rng.randint(10, 35), rng.uniform(0.5, 1.5)
            ))

    def load_nodes(self, nodes: list[dict]):
        """Load nodes and build splat data."""
        self._splats.clear()
        self._connections.clear()
        self._node_map.clear()
        self._hovered = -1
        self._selected = -1

        n = len(nodes)
        positions = []

        for i, node in enumerate(nodes):
            if "position" in node and len(node["position"]) >= 3:
                pos = node["position"][:3]
            elif "vector" in node and len(node["vector"]) >= 3:
                pos = node["vector"][:3]
            else:
                pos = [random.uniform(-10, 10) for _ in range(3)]
            positions.append(pos)

        mat = np.array(positions, dtype=np.float32)
        for dim in range(3):
            col = mat[:, dim]
            mn, mx = col.min(), col.max()
            if mx > mn:
                mat[:, dim] = (col - mn) / (mx - mn) * 25 - 12.5

        for i, node in enumerate(nodes):
            color = _palette_color(i)
            base_scale = 1.2
            frac = (i * 0.618) % 1.0
            scale = [
                base_scale * (0.8 + 0.5 * frac),
                base_scale * (0.8 + 0.5 * (1 - frac)),
                base_scale * (0.6 + 0.4 * random.random()),
            ]

            golden_angle = math.pi * (3 - math.sqrt(5))
            theta = golden_angle * i
            phi = math.acos(1 - 2 * (i + 0.5) / max(n, 1))

            cx, sx = math.cos(theta), math.sin(theta)
            cy, sy = math.cos(phi), math.sin(phi)
            Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
            Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            rot = Ry @ Rx

            opacity = node.get("opacity", 0.95)
            splat = SplatData(i, mat[i], color, scale, rot, opacity, node)
            self._splats.append(splat)
            self._node_map[node["id"]] = i

        # Build connections
        id_to_idx = {n["id"]: i for i, n in enumerate(nodes)}
        seen = set()
        for i, node in enumerate(nodes):
            for conn in node.get("connections", []):
                j = id_to_idx.get(conn.get("id"))
                if j is None or j <= i:
                    continue
                edge = (i, j)
                if edge not in seen:
                    seen.add(edge)
                    score = conn.get("score", 0.5)
                    self._connections.append((i, j, score))

        self.update()

    def set_connection_mode(self, mode: str):
        self._conn_mode = mode
        self.update()

    def set_splat_size(self, multiplier: float):
        for s in self._splats:
            # Always recompute from original scale to prevent progressive degradation
            ratio = s._original_scale / (s._original_scale.max() + 0.01)
            s.scale = ratio * multiplier
            S2 = np.diag(s.scale ** 2)
            s.sigma_3d = s.rotation @ S2 @ s.rotation.T
        self.update()

    def set_opacity(self, value: float):
        for s in self._splats:
            s.opacity = value
        self.update()

    # --- Animation ---

    def _tick(self):
        self._anim_time += 0.033
        self.update()

    # --- Rendering ---

    def paintEvent(self, event):
        if not self._splats:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        self._paint_background(painter, w, h)

        # Update screen coords for all splats
        for s in self._splats:
            # Add gentle drift
            drift = np.array([
                math.sin(self._anim_time * 0.4 + s.phase) * 0.15,
                math.cos(self._anim_time * 0.3 + s.phase * 1.3) * 0.15,
                math.sin(self._anim_time * 0.5 + s.phase * 0.7) * 0.1,
            ])
            pos = s.position + drift
            sx, sy, depth, pscale = self.camera.project(pos, w, h)
            s.sx, s.sy, s.depth, s.proj_scale = sx, sy, depth, pscale

            # Project covariance
            semi_a, semi_b, angle = self.camera.project_covariance_2d(s.sigma_3d)
            s.semi_a = semi_a * pscale * (w / 40)
            s.semi_b = semi_b * pscale * (w / 40)
            s.angle = angle

        # Sort back-to-front
        sorted_indices = sorted(range(len(self._splats)), key=lambda i: self._splats[i].depth)

        # Draw connections behind splats
        self._paint_connections(painter)

        # Draw splats in depth order
        for i in sorted_indices:
            self._paint_splat(painter, self._splats[i])

        # Selection ring
        if 0 <= self._selected < len(self._splats):
            self._paint_selection(painter, self._splats[self._selected])

        # Info overlay
        self._paint_info(painter, w, h)

        painter.end()

    def _paint_background(self, painter: QPainter, w: int, h: int):
        """Deep space background — same style as Knowledge Graph."""
        painter.fillRect(0, 0, w, h, QColor(Colors.BG))

        # Radial vignette
        vignette = QRadialGradient(w / 2, h / 2, max(w, h) * 0.7)
        vignette.setColorAt(0.0, QColor(15, 17, 23, 0))
        vignette.setColorAt(0.5, QColor(15, 17, 23, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 140))
        painter.fillRect(0, 0, w, h, vignette)

        # Star dots
        painter.setPen(Qt.NoPen)
        for rx, ry, alpha, size in self._stars:
            # Twinkle
            a = int(alpha * (0.7 + 0.3 * math.sin(self._anim_time * 0.5 + rx * 100)))
            painter.setBrush(QBrush(QColor(255, 255, 255, a)))
            painter.drawEllipse(QPointF(rx * w, ry * h), size, size)

        # Subtle grid (perspective-like)
        painter.setPen(QPen(QColor(255, 255, 255, 6), 0.5))
        for x in range(0, w, 50):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, 50):
            painter.drawLine(0, y, w, y)

        # Axis indicators (bottom-left)
        self._paint_axes(painter, w, h)

    def _paint_axes(self, painter: QPainter, w: int, h: int):
        """3D axis indicator in corner."""
        origin_x, origin_y = 60, h - 60
        length = 35

        for axis, color, label in [
            (np.array([1, 0, 0]), "#ef4444", "X"),
            (np.array([0, 1, 0]), "#22c55e", "Y"),
            (np.array([0, 0, 1]), "#3b82f6", "Z"),
        ]:
            ca, sa = math.cos(self.camera.azimuth), math.sin(self.camera.azimuth)
            ce, se = math.cos(self.camera.elevation), math.sin(self.camera.elevation)

            x, y, z = axis
            x1 = x * ca + z * sa
            z1 = -x * sa + z * ca
            y2 = y * ce - z1 * se

            ex = origin_x + x1 * length
            ey = origin_y - y2 * length

            painter.setPen(QPen(QColor(color), 2))
            painter.drawLine(QPointF(origin_x, origin_y), QPointF(ex, ey))
            painter.setFont(QFont("monospace", 8, QFont.Bold))
            painter.drawText(int(ex + 3), int(ey - 3), label)

    def _paint_connections(self, painter: QPainter):
        """Draw connections as alpha-gradient Bézier curves."""
        if not self._splats:
            return

        hovered = self._hovered
        selected = self._selected
        active = hovered if hovered >= 0 else selected

        neighbor_set = set()
        if active >= 0:
            for i, j, _ in self._connections:
                if i == active:
                    neighbor_set.add(j)
                elif j == active:
                    neighbor_set.add(i)

        for ci, (i, j, weight) in enumerate(self._connections):
            if i >= len(self._splats) or j >= len(self._splats):
                continue

            si, sj = self._splats[i], self._splats[j]

            is_highlighted = active >= 0 and (i == active or j == active)
            is_dim = active >= 0 and not is_highlighted

            # Filter by mode
            if self._conn_mode == "None":
                continue
            elif self._conn_mode == "Nearest 5":
                if not is_highlighted and weight < 0.6:
                    continue
            elif self._conn_mode == "Nearest 10":
                if not is_highlighted and weight < 0.4:
                    continue
            elif self._conn_mode == "Above threshold":
                if weight < 0.7:
                    continue
            elif self._conn_mode == "All":
                pass  # draw everything

            # Draw segmented alpha-gradient curve
            ax, ay = si.sx, si.sy
            bx, by = sj.sx, sj.sy

            # Control point — perpendicular offset for curvature
            mx, my = (ax + bx) / 2, (ay + by) / 2
            dx, dy = bx - ax, by - ay
            length = math.sqrt(dx * dx + dy * dy + 0.01)
            perp_x, perp_y = -dy / length, dx / length
            offset = weight * 12
            cx_pt = mx + perp_x * offset
            cy_pt = my + perp_y * offset

            # Color blend
            blend = _lerp_color(si.color, sj.color, 0.5)

            if is_dim:
                alpha_base = 12
            elif is_highlighted:
                alpha_base = int(60 + weight * 160)
            else:
                alpha_base = int(20 + weight * 50)

            base_width = 1.0 + weight ** 0.7 * 2.5
            if is_highlighted:
                base_width *= 1.4

            # Draw segmented with alpha gradient
            n_seg = 10
            prev_x, prev_y = ax, ay
            for seg in range(1, n_seg + 1):
                t = seg / n_seg
                px = (1 - t) ** 2 * ax + 2 * (1 - t) * t * cx_pt + t ** 2 * bx
                py = (1 - t) ** 2 * ay + 2 * (1 - t) * t * cy_pt + t ** 2 * by

                # Alpha: strongest at endpoints, lightest at midpoint
                alpha_t = 1.0 - 0.45 * (1.0 - abs(2 * t - 1))
                seg_alpha = max(5, int(alpha_base * alpha_t))

                pen_color = QColor(blend)
                pen_color.setAlpha(seg_alpha)
                painter.setPen(QPen(pen_color, base_width * alpha_t, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(prev_x, prev_y), QPointF(px, py))
                prev_x, prev_y = px, py

    def _paint_splat(self, painter: QPainter, splat: SplatData):
        """Draw a single Gaussian splat with glow + opaque core."""
        idx = splat.idx
        is_hovered = idx == self._hovered
        is_selected = idx == self._selected
        is_neighbor = False
        active = self._hovered if self._hovered >= 0 else self._selected
        if active >= 0:
            for i, j, _ in self._connections:
                if (i == active and j == idx) or (i == idx and j == active):
                    is_neighbor = True
                    break

        sx, sy = splat.sx, splat.sy
        sa, sb = splat.semi_a, splat.semi_b
        angle = splat.angle

        # Skip off-screen splats
        w, h = self.width(), self.height()
        if sx < -100 or sx > w + 100 or sy < -100 or sy > h + 100:
            return

        base = QColor(splat.color)

        # Glow radius multiplier
        glow_mult = 2.8 if is_hovered or is_selected else (2.2 if is_neighbor else 1.8)
        glow_sa = sa * glow_mult
        glow_sb = sb * glow_mult

        # --- Layer 1: Outer glow halo ---
        opacity = splat.opacity

        painter.save()
        painter.translate(sx, sy)
        painter.rotate(angle)

        glow_r = max(glow_sa, glow_sb)
        glow = QRadialGradient(QPointF(0, 0), glow_r)
        if is_hovered or is_selected:
            ga_in, ga_mid = 90, 35
        elif is_neighbor:
            ga_in, ga_mid = 55, 18
        else:
            ga_in, ga_mid = 30, 10

        c_in = QColor(base); c_in.setAlpha(int(ga_in * opacity))
        c_mid = QColor(base); c_mid.setAlpha(int(ga_mid * opacity))
        c_out = QColor(base); c_out.setAlpha(0)
        glow.setColorAt(0.0, c_in)
        glow.setColorAt(0.4, c_mid)
        glow.setColorAt(1.0, c_out)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.scale(1.0, glow_sb / max(glow_sa, 1))
        painter.drawEllipse(QPointF(0, 0), glow_sa, glow_sa)
        painter.restore()

        # --- Layer 2: Concentric ring halos ---
        n_rings = 3 if is_hovered or is_selected else 2
        for ring in range(n_rings, 0, -1):
            ring_sa = sa + ring * (3 + sa * 0.1)
            ring_sb = sb + ring * (3 + sb * 0.1)
            ring_alpha = int(50 / (ring + 0.5))
            if is_hovered or is_selected:
                ring_alpha = int(ring_alpha * 2.5)

            rc = QColor(base); rc.setAlpha(min(int(ring_alpha * opacity), 200))
            painter.setPen(QPen(rc, 1.0))
            painter.setBrush(Qt.NoBrush)
            painter.save()
            painter.translate(sx, sy)
            painter.rotate(angle)
            painter.scale(1.0, ring_sb / max(ring_sa, 1))
            painter.drawEllipse(QPointF(0, 0), ring_sa, ring_sa)
            painter.restore()

        # --- Layer 3: Opaque core splat ---
        painter.save()
        painter.translate(sx, sy)
        painter.rotate(angle)

        core_r = max(sa, sb)
        core = QRadialGradient(QPointF(0, 0), core_r)

        if is_hovered or is_selected:
            ci_color = QColor(base).lighter(155)
            ci_alpha = 255
        elif is_neighbor:
            ci_color = QColor(base).lighter(130)
            ci_alpha = 235
        else:
            ci_color = QColor(base).lighter(115)
            ci_alpha = 220

        ci_color.setAlpha(int(ci_alpha * opacity))

        mid_color = QColor(base).lighter(105)
        mid_color.setAlpha(int(180 * opacity))

        edge_color = QColor(base).darker(140)
        edge_color.setAlpha(int(100 * opacity))

        far_color = QColor(base).darker(180)
        far_color.setAlpha(int(30 * opacity))

        outer_color = QColor(base).darker(200)
        outer_color.setAlpha(0)

        core.setColorAt(0.0, ci_color)
        core.setColorAt(0.3, mid_color)
        core.setColorAt(0.65, edge_color)
        core.setColorAt(0.88, far_color)
        core.setColorAt(1.0, outer_color)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(core))
        painter.scale(1.0, sb / max(sa, 1))
        painter.drawEllipse(QPointF(0, 0), sa, sa)
        painter.restore()

        # --- Border ---
        border_alpha = 200 if is_hovered or is_selected else 100
        border_color = QColor(base).lighter(150 if is_hovered or is_selected else 120)
        border_color.setAlpha(int(border_alpha * opacity))
        border_w = 2.0 if is_selected else (1.5 if is_hovered else 0.8)
        painter.setPen(QPen(border_color, border_w))
        painter.setBrush(Qt.NoBrush)
        painter.save()
        painter.translate(sx, sy)
        painter.rotate(angle)
        painter.scale(1.0, sb / max(sa, 1))
        painter.drawEllipse(QPointF(0, 0), sa, sa)
        painter.restore()

        # --- Label on hover/select ---
        if is_hovered or is_selected:
            meta = splat.node_data.get("metadata", {})
            label = meta.get("label", splat.node_data.get("id", ""))
            if label:
                font_size = 10
                painter.setFont(QFont("sans-serif", font_size, QFont.Medium))
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(label)

                lx = sx - tw / 2
                ly = sy + max(sa, sb) + 14

                bg = QColor(Colors.BG_RAISED); bg.setAlpha(200)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(bg))
                painter.drawRoundedRect(int(lx - 4), int(ly - fm.height() + 2),
                                        tw + 8, fm.height() + 4, 4, 4)

                painter.setPen(QPen(QColor(Colors.TEXT)))
                painter.drawText(int(lx), int(ly + 2), label)

    def _paint_selection(self, painter: QPainter, splat: SplatData):
        """Dashed ring around selected splat."""
        sx, sy = splat.sx, splat.sy
        sa, sb = splat.semi_a * 1.3, splat.semi_b * 1.3

        pen = QPen(QColor(Colors.ACCENT), 2.5, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.save()
        painter.translate(sx, sy)
        painter.rotate(splat.angle)
        painter.scale(1.0, sb / max(sa, 1))
        painter.drawEllipse(QPointF(0, 0), sa, sa)
        painter.restore()

    def _paint_info(self, painter: QPainter, w: int, h: int):
        """Info overlay — bottom-right title block."""
        bw, bh = 200, 60
        x0, y0 = w - bw - 10, h - bh - 10

        painter.setPen(Qt.NoPen)
        bg = QColor(Colors.BG_RAISED); bg.setAlpha(190)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(x0, y0, bw, bh, 6, 6)

        painter.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        painter.drawLine(x0, y0, x0 + bw, y0)

        painter.setFont(QFont("monospace", 7))
        painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
        n_splats = len(self._splats)
        n_conns = len(self._connections)
        painter.drawText(x0 + 6, y0 + 15, "GAUSSIAN SPLAT EXPLORER")
        painter.drawText(x0 + 6, y0 + 28, f"Splats: {n_splats}  Connections: {n_conns}")
        painter.drawText(x0 + 6, y0 + 41, f"Camera: az={math.degrees(self.camera.azimuth):.0f}° "
                            f"el={math.degrees(self.camera.elevation):.0f}°")
        painter.drawText(x0 + 6, y0 + 54, f"Projection: perspective {self.camera.fov:.0f}° FOV")

    # --- Mouse interaction ---

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.modifiers() & Qt.ShiftModifier:
                self._pan_start = (event.position().x(), event.position().y())
            else:
                self._drag_start = (event.position().x(), event.position().y())
        elif event.button() == Qt.RightButton:
            self._select_at(event.position())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._select_at(event.position())

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag_start and not (event.modifiers() & Qt.ShiftModifier):
            dx = pos.x() - self._drag_start[0]
            dy = pos.y() - self._drag_start[1]
            self.camera.azimuth += dx * 0.005
            self.camera.elevation += dy * 0.005
            self.camera.elevation = max(-math.pi / 2 + 0.1, min(math.pi / 2 - 0.1, self.camera.elevation))
            self._drag_start = (pos.x(), pos.y())
            self.update()
        elif self._pan_start and (event.modifiers() & Qt.ShiftModifier):
            dx = pos.x() - self._pan_start[0]
            dy = pos.y() - self._pan_start[1]
            scale = 35 / max(self.width(), self.height())
            self.camera.pan_x += dx * scale
            self.camera.pan_y -= dy * scale
            self._pan_start = (pos.x(), pos.y())
            self.update()
        else:
            self._hover_at(pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = None
            self._pan_start = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.camera.distance *= 0.93 if delta > 0 else 1.07
        self.camera.distance = max(10, min(self.camera.distance, 200))
        self.update()

    def _hover_at(self, pos):
        best, best_d = -1, 35
        for s in self._splats:
            d = math.sqrt((pos.x() - s.sx) ** 2 + (pos.y() - s.sy) ** 2)
            hit_r = max(s.semi_a, s.semi_b) * 0.6
            if d < hit_r and d < best_d:
                best_d = d
                best = s.idx
        if best != self._hovered:
            self._hovered = best
            self.setCursor(Qt.PointingHandCursor if best >= 0 else Qt.ArrowCursor)
            self.update()

    def _select_at(self, pos):
        best, best_d = -1, 50
        for s in self._splats:
            d = math.sqrt((pos.x() - s.sx) ** 2 + (pos.y() - s.sy) ** 2)
            hit_r = max(s.semi_a, s.semi_b) * 0.8
            if d < hit_r and d < best_d:
                best_d = d
                best = s.idx
        if best >= 0:
            self._selected = best
            nid = self._splats[best].node_data.get("id", "")
            self.node_clicked.emit(nid)
            self.update()


# ---------------------------------------------------------------------------
# Splat3D View — main widget
# ---------------------------------------------------------------------------

class Splat3DView(QWidget):
    """Gaussian Splat Explorer — 3D perspective rendering."""

    node_selected = Signal(str)
    node_hovered = Signal(str)
    connection_clicked = Signal(str, str)

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

        title = QLabel("Gaussian Splat Explorer")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 14px; font-weight: 700;")
        tb.addWidget(title)

        sub = QLabel("3D Perspective · Mahalanobis Ellipsoids")
        sub.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px;")
        tb.addWidget(sub)

        tb.addStretch()

        tb.addWidget(QLabel("Splat size:"))
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(3, 40)
        self.size_slider.setValue(14)
        self.size_slider.setFixedWidth(90)
        self.size_slider.valueChanged.connect(self._on_size)
        tb.addWidget(self.size_slider)

        tb.addWidget(QLabel("Opacity:"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(95)
        self.opacity_slider.setFixedWidth(80)
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        tb.addWidget(self.opacity_slider)

        tb.addWidget(QLabel("Connections:"))
        self.conn_combo = QComboBox()
        self.conn_combo.addItems(["All", "Nearest 5", "Nearest 10", "Above threshold", "None"])
        self.conn_combo.setCurrentText("Nearest 5")
        self.conn_combo.currentTextChanged.connect(self._on_conn_mode)
        tb.addWidget(self.conn_combo)

        reset_btn = QPushButton("Reset View")
        reset_btn.setIcon(icon("refresh", Colors.TEXT))
        reset_btn.clicked.connect(self._reset_camera)
        tb.addWidget(reset_btn)

        tb_w = QWidget()
        tb_w.setLayout(tb)
        tb_w.setStyleSheet(
            f"background-color: {Colors.BG_RAISED}; border-bottom: 1px solid {Colors.BORDER};"
        )
        layout.addWidget(tb_w)

        # Canvas
        self.canvas = Splat3DCanvas()
        self.canvas.node_clicked.connect(self._on_select)
        layout.addWidget(self.canvas, stretch=1)

        # Info bar
        self.info_bar = QLabel(
            "Drag: rotate · Shift+Drag: pan · Scroll: zoom · "
            "Double-click/right-click: select"
        )
        self.info_bar.setStyleSheet(f"""
            color: {Colors.TEXT_DIM}; font-size: 11px; padding: 6px 12px;
            background-color: {Colors.BG_RAISED}; border-top: 1px solid {Colors.BORDER};
        """)
        layout.addWidget(self.info_bar)
        self.setStyleSheet(f"background-color: {Colors.BG};")

    def load_nodes(self, nodes: list[dict]):
        self.canvas.load_nodes(nodes)
        self._nodes = {n["id"]: n for n in nodes}
        nc = len(self.canvas._connections)
        self.info_bar.setText(
            f"{len(nodes)} Gaussian splats · {nc} connections · "
            f"Drag: rotate · Shift+Drag: pan · Scroll: zoom"
        )

    def select_node(self, node_id: str):
        idx = self.canvas._node_map.get(node_id)
        if idx is not None:
            self.canvas._selected = idx
            self.canvas.update()

    def _on_select(self, node_id: str):
        self.node_selected.emit(node_id)
        idx = self.canvas._node_map.get(node_id, -1)
        if idx >= 0:
            s = self.canvas._splats[idx]
            meta = s.node_data.get("metadata", {})
            label = meta.get("label", node_id)
            self.info_bar.setText(
                f"Selected: {label} · {len(s.node_data.get('connections', []))} connections · "
                f"Σ = R·diag(s²)·Rᵀ"
            )

    def _on_size(self, val):
        self.canvas.set_splat_size(val / 10.0)

    def _on_opacity(self, val):
        self.canvas.set_opacity(val / 100.0)

    def _on_conn_mode(self, mode):
        self.canvas.set_connection_mode(mode)

    def _reset_camera(self):
        self.canvas.camera = Camera3D()
        self.canvas.update()
