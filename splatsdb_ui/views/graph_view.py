# SPDX-License-Identifier: GPL-3.0
"""Knowledge Graph View — Force-Directed Celestial Network visualization.

Mathematical foundations:
  Fruchterman-Reingold force-directed layout:
    Repulsive:  F_r = k_r / d²        (Coulomb inverse-square)
    Attractive: F_a = k_a · d² / L    (Hooke quadratic, L = rest length)
    Gravity:    F_g = -k_g · r        (harmonic pull toward center of mass)
    Damping:    v(t+1) = 0.85·v(t) + F(t)/m

  Edge bundling via angular bisector offset:
    ctrl = midpoint + perp · offset
    where offset = f(angle_diff, edge_weight)

  Node sizing:  radius ∝ degree^0.5  (square-root scaling)
  Edge width:   proportional to weight^0.7

Visual style — "Celestial Network":
  Deep space vignette background, golden-ratio palette node halos,
  quadratic Bézier edges with alpha gradients, animated drift.
"""

from __future__ import annotations

import math
import colorsys
from collections import defaultdict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSplitter, QSizePolicy, QCheckBox,
)
from PySide6.QtCore import Signal, Qt, QTimer, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QPainterPath, QRadialGradient,
)

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon

PHI = (1 + math.sqrt(5)) / 2  # Golden ratio ≈ 1.618

# ---------------------------------------------------------------------------
# Golden-ratio palette
# ---------------------------------------------------------------------------

_PALETTE = [
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


def _node_color(idx: int) -> QColor:
    """Generate color via golden-ratio hue spacing."""
    hue = (idx * (1.0 / PHI)) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.65, 0.88)
    return QColor(int(r * 255), int(g * 255), int(b * 255))


def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    """Linear interpolation between two colors."""
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
    )


# ---------------------------------------------------------------------------
# Graph data structures
# ---------------------------------------------------------------------------

class GraphNode:
    """A single node in the force-directed graph."""
    __slots__ = ('id', 'label', 'category', 'x', 'y', 'vx', 'vy',
                 'fx', 'fy', 'degree', 'radius', 'color', 'connections',
                 'mass', 'phase', 'original_idx')

    def __init__(self, nid: str, label: str, category: str = "",
                 color_idx: int = 0, original_idx: int = 0):
        self.id = nid
        self.label = label
        self.category = category
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.fx = 0.0
        self.fy = 0.0
        self.degree = 0
        self.radius = 8.0
        self.color = _node_color(color_idx)
        self.connections: list[dict] = []
        self.mass = 1.0
        self.phase = 0.0  # animation phase offset
        self.original_idx = original_idx


class GraphEdge:
    """An edge between two graph nodes."""
    __slots__ = ('source_idx', 'target_idx', 'weight', 'score',
                 'ctrl_x', 'ctrl_y')

    def __init__(self, src: int, tgt: int, weight: float = 1.0,
                 score: float = 0.0):
        self.source_idx = src
        self.target_idx = tgt
        self.weight = weight
        self.score = score
        self.ctrl_x = 0.0  # Bézier control point x
        self.ctrl_y = 0.0  # Bézier control point y


# ---------------------------------------------------------------------------
# Force-directed layout engine
# ---------------------------------------------------------------------------

class ForceLayoutEngine:
    """Fruchterman-Reingold variant with gravity and damping."""

    def __init__(self):
        self.nodes: list[GraphNode] = []
        self.edges: list[GraphEdge] = []

        # Physics parameters
        self.k_repulsion = 8000.0   # Coulomb constant k_r
        self.k_attraction = 0.005   # Hooke constant k_a
        self.k_gravity = 0.02       # Gravity constant k_g
        self.rest_length = 120.0    # Equilibrium distance L
        self.damping = 0.85         # Velocity decay
        self.temperature = 1.0      # Simulated annealing temperature
        self.min_temperature = 0.01
        self.cooling_rate = 0.995

        # Canvas dimensions for layout
        self.width = 800
        self.height = 600
        self.iteration = 0
        self.max_iterations = 500
        self.settled = False

    def build_graph(self, raw_nodes: list[dict]):
        """Build graph from raw node data with connections."""
        # Build index mapping: node id -> sequential index
        id_to_idx: dict[str, int] = {}
        self.nodes = []

        for i, n in enumerate(raw_nodes):
            nid = n.get("id", str(i))
            meta = n.get("metadata", {})
            label = meta.get("label", nid[:24])
            category = meta.get("category", "")
            id_to_idx[nid] = i

            node = GraphNode(nid, label, category, color_idx=i,
                             original_idx=i)
            node.connections = n.get("connections", [])
            self.nodes.append(node)

        # Build edges from connections
        self.edges = []
        seen_edges: set[tuple[int, int]] = set()

        for i, n in enumerate(raw_nodes):
            for conn in n.get("connections", []):
                target_id = conn.get("id", "")
                j = id_to_idx.get(target_id)
                if j is None:
                    continue

                # Avoid duplicate edges (undirected)
                key = (min(i, j), max(i, j))
                if key in seen_edges:
                    continue
                seen_edges.add(key)

                score = conn.get("score", 0.5)
                distance = conn.get("distance", 1.0)
                weight = score * max(1.0 - distance, 0.1)

                edge = GraphEdge(i, j, weight, score)
                self.edges.append(edge)

                # Update degree
                self.nodes[i].degree += 1
                self.nodes[j].degree += 1

        # Compute node properties
        max_degree = max((n.degree for n in self.nodes), default=1) or 1
        for node in self.nodes:
            # Square root scaling: radius ∝ degree^0.5
            node.radius = 6.0 + 14.0 * math.sqrt(node.degree / max_degree)
            node.mass = 0.5 + node.degree * 0.3
            node.phase = hash(node.id) % 1000 / 1000.0 * 2 * math.pi

    def initialize_positions(self, layout: str = "force"):
        """Set initial positions based on layout type."""
        n = len(self.nodes)
        if n == 0:
            return

        cx = self.width / 2
        cy = self.height / 2

        if layout == "circular":
            for i, node in enumerate(self.nodes):
                angle = 2 * math.pi * i / n
                r = min(self.width, self.height) * 0.35
                node.x = cx + r * math.cos(angle)
                node.y = cy + r * math.sin(angle)

        elif layout == "hierarchical":
            # Sort by degree (highest at top)
            sorted_indices = sorted(range(n),
                                    key=lambda i: self.nodes[i].degree,
                                    reverse=True)
            levels = max(3, int(math.sqrt(n)))
            per_level = max(1, n // levels)
            for rank, idx in enumerate(sorted_indices):
                level = rank // per_level
                pos_in_level = rank % per_level
                count_in_level = min(per_level, n - level * per_level)
                x_spacing = self.width / (count_in_level + 1)
                y_spacing = self.height / (levels + 1)
                self.nodes[idx].x = x_spacing * (pos_in_level + 1)
                self.nodes[idx].y = y_spacing * (level + 1)

        elif layout == "random":
            margin = 80
            import random
            for node in self.nodes:
                node.x = margin + random.random() * (self.width - 2 * margin)
                node.y = margin + random.random() * (self.height - 2 * margin)

        else:  # force — random init, then simulate
            margin = 80
            import random
            for node in self.nodes:
                node.x = cx + (random.random() - 0.5) * (self.width - 2 * margin)
                node.y = cy + (random.random() - 0.5) * (self.height - 2 * margin)

        # Reset velocities and temperature
        for node in self.nodes:
            node.vx = 0.0
            node.vy = 0.0
        self.temperature = 1.0
        self.iteration = 0
        self.settled = False

    def step(self) -> bool:
        """Perform one simulation step. Returns True if still moving."""
        if self.settled or len(self.nodes) < 2:
            return False

        n = len(self.nodes)
        cx = self.width / 2
        cy = self.height / 2

        # Reset forces
        for node in self.nodes:
            node.fx = 0.0
            node.fy = 0.0

        # --- Repulsive forces: F_r = k_r / d² ---
        for i in range(n):
            ni = self.nodes[i]
            for j in range(i + 1, n):
                nj = self.nodes[j]
                dx = ni.x - nj.x
                dy = ni.y - nj.y
                d2 = dx * dx + dy * dy
                d = math.sqrt(d2) if d2 > 0 else 0.1
                if d < 1.0:
                    d = 1.0
                    d2 = 1.0

                # F_r = k_r / d², direction = along displacement
                force = self.k_repulsion / d2
                fx = force * dx / d
                fy = force * dy / d

                ni.fx += fx
                ni.fy += fy
                nj.fx -= fx
                nj.fy -= fy

        # --- Attractive forces: F_a = k_a · d² / L ---
        for edge in self.edges:
            ni = self.nodes[edge.source_idx]
            nj = self.nodes[edge.target_idx]
            dx = nj.x - ni.x
            dy = nj.y - ni.y
            d = math.sqrt(dx * dx + dy * dy)
            if d < 0.1:
                d = 0.1

            # F_a = k_a · d² / L (Hooke's quadratic)
            force = self.k_attraction * d * d / self.rest_length * edge.weight
            fx = force * dx / d
            fy = force * dy / d

            ni.fx += fx
            ni.fy += fy
            nj.fx -= fx
            nj.fy -= fy

        # --- Gravity: F_g = -k_g · r ---
        for node in self.nodes:
            dx = node.x - cx
            dy = node.y - cy
            node.fx -= self.k_gravity * dx
            node.fy -= self.k_gravity * dy

        # --- Apply forces with damping ---
        max_displacement = 0
        for node in self.nodes:
            # v(t+1) = 0.85 · v(t) + F(t)/m
            node.vx = self.damping * node.vx + node.fx / node.mass
            node.vy = self.damping * node.vy + node.fy / node.mass

            # Limit displacement by temperature
            speed = math.sqrt(node.vx ** 2 + node.vy ** 2)
            max_speed = 50.0 * self.temperature
            if speed > max_speed and speed > 0:
                node.vx = node.vx / speed * max_speed
                node.vy = node.vy / speed * max_speed

            node.x += node.vx
            node.y += node.vy

            # Keep within bounds with soft margin
            margin = 40
            node.x = max(margin, min(self.width - margin, node.x))
            node.y = max(margin, min(self.height - margin, node.y))

            disp = abs(node.vx) + abs(node.vy)
            if disp > max_displacement:
                max_displacement = disp

        # Cool down
        self.temperature *= self.cooling_rate
        self.iteration += 1

        if self.iteration >= self.max_iterations or self.temperature < self.min_temperature:
            self.settled = True
            return False

        return True

    def compute_edge_bundling(self):
        """Compute Bézier control points for edge bundling.

        For edges sharing endpoints, offset control points using angular
        bisector: ctrl = midpoint + perp · offset
        where offset = f(angle_diff, edge_weight)
        """
        # Group edges by (source, target) pair to detect parallel edges
        endpoint_edges: dict[tuple[int, int], list[int]] = defaultdict(list)
        for ei, edge in enumerate(self.edges):
            key = (min(edge.source_idx, edge.target_idx),
                   max(edge.source_idx, edge.target_idx))
            endpoint_edges[key].append(ei)

        for key, edge_indices in endpoint_edges.items():
            if len(edge_indices) == 1:
                # Single edge — slight curve for aesthetics
                ei = edge_indices[0]
                edge = self.edges[ei]
                ni = self.nodes[edge.source_idx]
                nj = self.nodes[edge.target_idx]
                mx = (ni.x + nj.x) / 2
                my = (ni.y + nj.y) / 2
                dx = nj.x - ni.x
                dy = nj.y - ni.y
                d = math.sqrt(dx * dx + dy * dy) or 1.0
                # Perpendicular offset proportional to distance
                offset = d * 0.08
                edge.ctrl_x = mx + (-dy / d) * offset
                edge.ctrl_y = my + (dx / d) * offset
            else:
                # Multiple edges — spread with angular bisector offsets
                ni = self.nodes[self.edges[edge_indices[0]].source_idx]
                nj = self.nodes[self.edges[edge_indices[0]].target_idx]
                mx = (ni.x + nj.x) / 2
                my = (ni.y + nj.y) / 2
                dx = nj.x - ni.x
                dy = nj.y - ni.y
                d = math.sqrt(dx * dx + dy * dy) or 1.0
                perp_x = -dy / d
                perp_y = dx / d

                n_edges = len(edge_indices)
                spread = d * 0.15  # Total spread distance

                for rank, ei in enumerate(edge_indices):
                    edge = self.edges[ei]
                    # Offset by rank position (centered around 0)
                    if n_edges > 1:
                        t = (rank / (n_edges - 1)) - 0.5  # [-0.5, 0.5]
                    else:
                        t = 0
                    offset = t * spread * 2
                    edge.ctrl_x = mx + perp_x * offset
                    edge.ctrl_y = my + perp_y * offset

    def run_to_convergence(self, max_steps: int = 300):
        """Run simulation until convergence or max_steps."""
        for _ in range(max_steps):
            if not self.step():
                break
        self.compute_edge_bundling()


# ---------------------------------------------------------------------------
# Canvas — celestial network renderer
# ---------------------------------------------------------------------------

class GraphCanvas(QWidget):
    """QPainter canvas for the force-directed knowledge graph."""

    node_clicked = Signal(str)   # emits node id
    node_hovered = Signal(str)   # emits node id

    def __init__(self):
        super().__init__()
        self.setMinimumSize(600, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self.engine = ForceLayoutEngine()
        self._hovered_node: int = -1
        self._selected_node: int = -1
        self._animating = True
        self._show_bundling = True
        self._anim_time = 0.0

        # Animation timer for gentle floating
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 FPS

        # Node data for tooltip
        self._node_data: list[dict] = []

        # Pre-generate star field positions (avoid re-seeding RNG every frame)
        import random
        rng = random.Random(42)
        self._stars = [(rng.randint(0, 2000), rng.randint(0, 2000), rng.randint(8, 30))
                       for _ in range(80)]

    def set_nodes(self, nodes: list[dict], layout: str = "force"):
        """Load nodes and build the graph."""
        self._node_data = nodes
        self.engine.width = max(self.width(), 800)
        self.engine.height = max(self.height(), 600)
        self.engine.build_graph(nodes)
        self.engine.initialize_positions(layout)

        if layout == "force":
            self.engine.run_to_convergence()
        else:
            self.engine.compute_edge_bundling()

        self._hovered_node = -1
        self._selected_node = -1
        self.update()

    def set_physics(self, kr: float, ka: float, kg: float):
        """Update physics parameters and re-simulate."""
        self.engine.k_repulsion = kr
        self.engine.k_attraction = ka
        self.engine.k_gravity = kg
        self.engine.width = max(self.width(), 800)
        self.engine.height = max(self.height(), 600)
        self.engine.initialize_positions("force")
        self.engine.run_to_convergence()
        self.update()

    def set_layout(self, layout: str):
        """Switch to a different layout."""
        self.engine.width = max(self.width(), 800)
        self.engine.height = max(self.height(), 600)
        self.engine.initialize_positions(layout)
        if layout == "force":
            self.engine.run_to_convergence()
        else:
            self.engine.compute_edge_bundling()
        self.update()

    def set_animating(self, on: bool):
        self._animating = on

    def set_bundling(self, on: bool):
        self._show_bundling = on
        self.engine.compute_edge_bundling()
        self.update()

    def _tick(self):
        """Animation tick — gentle floating oscillation."""
        if self._animating and self.engine.nodes:
            self._anim_time += 0.033
            self.update()

    # --- Rendering ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        self._paint_background(painter, w, h)
        self._paint_edges(painter)
        self._paint_nodes(painter, w, h)
        self._paint_info(painter, w, h)

        painter.end()

    def _paint_background(self, painter: QPainter, w: int, h: int):
        """Deep space background with radial vignette."""
        # Base fill
        painter.fillRect(0, 0, w, h, QColor(Colors.BG))

        # Radial vignette — darker at edges
        vignette = QRadialGradient(w / 2, h / 2, max(w, h) * 0.7)
        vignette.setColorAt(0.0, QColor(15, 17, 23, 0))
        vignette.setColorAt(0.6, QColor(15, 17, 23, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 120))
        painter.fillRect(0, 0, w, h, vignette)

        # Subtle star-like dots (positions cached in __init__)
        painter.setPen(Qt.NoPen)
        for sx, sy, alpha in self._stars:
            # Clamp to current widget size
            sx = sx % w if w > 0 else 0
            sy = sy % h if h > 0 else 0
            painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
            painter.drawEllipse(sx, sy, 1, 1)

        # Fine grid (very subtle)
        painter.setPen(QPen(QColor(255, 255, 255, 5), 0.5))
        for x in range(0, w, 40):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, 40):
            painter.drawLine(0, y, w, y)

    def _paint_edges(self, painter: QPainter):
        """Draw edges as quadratic Bézier curves with alpha gradients."""
        nodes = self.engine.nodes
        if not nodes:
            return

        hovered = self._hovered_node
        selected = self._selected_node

        # Determine which edges are highlighted
        highlight_set: set[int] = set()
        if hovered >= 0 or selected >= 0:
            active = hovered if hovered >= 0 else selected
            for ei, edge in enumerate(self.engine.edges):
                if edge.source_idx == active or edge.target_idx == active:
                    highlight_set.add(ei)

        for ei, edge in enumerate(self.engine.edges):
            if edge.source_idx >= len(nodes) or edge.target_idx >= len(nodes):
                continue

            ni = nodes[edge.source_idx]
            nj = nodes[edge.target_idx]

            is_highlighted = ei in highlight_set
            is_dim = (hovered >= 0 or selected >= 0) and not is_highlighted

            # Animated positions (gentle drift)
            ax, ay = self._animated_pos(ni)
            bx, by = self._animated_pos(nj)

            # Control point
            if self._show_bundling:
                cx = edge.ctrl_x
                cy = edge.ctrl_y
                # Animate control point too
                t_off = math.sin(self._anim_time * 0.5 + edge.weight * 10) * 2
                cx += t_off
                cy += t_off
            else:
                cx = (ax + bx) / 2
                cy = (ay + by) / 2

            # Edge width: proportional to weight^0.7
            base_width = 1.0 + edge.weight ** 0.7 * 3.0
            if is_highlighted:
                base_width *= 1.5

            # Color: blend of source and target node colors
            blend = _lerp_color(ni.color, nj.color, 0.5)

            if is_dim:
                alpha = 15
            elif is_highlighted:
                alpha = int(80 + edge.weight * 140)
            else:
                alpha = int(25 + edge.weight * 60)

            # Draw with alpha gradient (stronger at endpoints, lighter at mid)
            # Use QLinearGradient along the edge for the alpha fade
            # Since Bézier curves can't directly use gradients along path,
            # we draw multiple segments with varying alpha
            n_seg = 12
            prev_x, prev_y = ax, ay
            for seg in range(1, n_seg + 1):
                t = seg / n_seg
                # Quadratic Bézier: B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
                px = (1 - t) ** 2 * ax + 2 * (1 - t) * t * cx + t ** 2 * bx
                py = (1 - t) ** 2 * ay + 2 * (1 - t) * t * cy + t ** 2 * by

                # Alpha: strongest at endpoints, lightest at midpoint
                # Parabolic: peaks at t=0 and t=1, min at t=0.5
                alpha_t = 1.0 - 0.5 * (1.0 - abs(2 * t - 1))
                seg_alpha = int(alpha * alpha_t)

                pen_color = QColor(blend)
                pen_color.setAlpha(max(5, seg_alpha))
                painter.setPen(QPen(pen_color, base_width * alpha_t,
                                    Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(prev_x, prev_y), QPointF(px, py))
                prev_x, prev_y = px, py

    def _paint_nodes(self, painter: QPainter, w: int, h: int):
        """Draw nodes with concentric ring halos and glow."""
        nodes = self.engine.nodes
        if not nodes:
            return

        hovered = self._hovered_node
        selected = self._selected_node

        # Determine neighbor set for hover glow
        neighbor_set: set[int] = set()
        if hovered >= 0:
            for edge in self.engine.edges:
                if edge.source_idx == hovered:
                    neighbor_set.add(edge.target_idx)
                elif edge.target_idx == hovered:
                    neighbor_set.add(edge.source_idx)

        for i, node in enumerate(nodes):
            ax, ay = self._animated_pos(node)

            is_hovered = i == hovered
            is_selected = i == selected
            is_neighbor = i in neighbor_set

            r = node.radius

            # --- Outer glow (QRadialGradient) ---
            glow_radius = r * (3.0 if is_hovered or is_selected else
                               (2.2 if is_neighbor else 1.8))
            glow = QRadialGradient(ax, ay, glow_radius)

            base_color = QColor(node.color)
            if is_hovered or is_selected:
                glow_alpha_inner = 100
                glow_alpha_mid = 40
            elif is_neighbor:
                glow_alpha_inner = 60
                glow_alpha_mid = 20
            else:
                glow_alpha_inner = 35
                glow_alpha_mid = 10

            c_inner = QColor(base_color)
            c_inner.setAlpha(glow_alpha_inner)
            c_mid = QColor(base_color)
            c_mid.setAlpha(glow_alpha_mid)
            c_outer = QColor(base_color)
            c_outer.setAlpha(0)

            glow.setColorAt(0.0, c_inner)
            glow.setColorAt(0.4, c_mid)
            glow.setColorAt(1.0, c_outer)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(ax, ay), glow_radius, glow_radius)

            # --- Concentric ring halos (2-3 rings) ---
            n_rings = 3 if node.degree >= 4 else (2 if node.degree >= 2 else 1)
            for ring in range(n_rings, 0, -1):
                ring_r = r + ring * (4 + r * 0.15)
                ring_color = QColor(node.color)
                ring_alpha = int(40 / (ring + 0.5))
                if is_hovered or is_selected:
                    ring_alpha = int(ring_alpha * 2.0)
                elif is_neighbor:
                    ring_alpha = int(ring_alpha * 1.4)
                ring_color.setAlpha(min(ring_alpha, 200))
                painter.setPen(QPen(ring_color, 1.0))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(ax, ay), ring_r, ring_r)

            # --- Core node ---
            core_grad = QRadialGradient(ax - r * 0.2, ay - r * 0.2, r * 1.2)

            if is_hovered or is_selected:
                core_inner = QColor(base_color).lighter(160)
                core_inner.setAlpha(240)
            elif is_neighbor:
                core_inner = QColor(base_color).lighter(130)
                core_inner.setAlpha(200)
            else:
                core_inner = QColor(base_color).lighter(115)
                core_inner.setAlpha(180)

            core_outer = QColor(base_color).darker(130)
            core_outer.setAlpha(120)

            core_grad.setColorAt(0.0, core_inner)
            core_grad.setColorAt(0.7, core_outer)
            core_grad.setColorAt(1.0, QColor(base_color).darker(200))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(core_grad))
            painter.drawEllipse(QPointF(ax, ay), r, r)

            # --- Border ---
            border_alpha = 200 if is_hovered or is_selected else 120
            border_color = QColor(base_color).lighter(
                160 if is_hovered or is_selected else 130)
            border_color.setAlpha(border_alpha)
            border_w = 2.0 if is_selected else (1.5 if is_hovered else 1.0)
            painter.setPen(QPen(border_color, border_w))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(ax, ay), r, r)

            # --- Label ---
            if r >= 6 and (is_hovered or is_selected or
                           node.degree >= 2 or len(nodes) <= 40):
                label = node.label[:16]
                font_size = max(7, min(11, int(r * 0.7)))
                painter.setFont(QFont("sans-serif", font_size, QFont.Medium))

                # Label background
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(label)
                th = fm.height()
                lx = ax - tw / 2
                ly = ay + r + 4

                bg = QColor(Colors.BG)
                bg.setAlpha(160)
                painter.fillRect(int(lx - 3), int(ly - th + 2),
                                 tw + 6, th + 2, bg)

                text_color = QColor(Colors.TEXT) if (
                    is_hovered or is_selected) else QColor(Colors.TEXT_DIM)
                painter.setPen(QPen(text_color))
                painter.drawText(int(lx), int(ly + 2), label)

    def _paint_info(self, painter: QPainter, w: int, h: int):
        """Draw info overlay — bottom-right title block."""
        bw, bh = 180, 48
        x0, y0 = w - bw - 10, h - bh - 10

        painter.setPen(Qt.NoPen)
        bg = QColor(Colors.BG_RAISED)
        bg.setAlpha(180)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(x0, y0, bw, bh, 6, 6)

        painter.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        painter.drawLine(x0, y0, x0 + bw, y0)

        painter.setFont(QFont("monospace", 7))
        painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
        n_nodes = len(self.engine.nodes)
        n_edges = len(self.engine.edges)
        painter.drawText(x0 + 6, y0 + 15, "KNOWLEDGE GRAPH")
        painter.drawText(x0 + 6, y0 + 28,
                         f"Nodes: {n_nodes}  Edges: {n_edges}")
        painter.drawText(x0 + 6, y0 + 40,
                         f"Layout: {'settled' if self.engine.settled else 'simulating'}")

    def _animated_pos(self, node: GraphNode) -> tuple[float, float]:
        """Get animated position with gentle floating drift."""
        if self._animating:
            drift_x = math.sin(self._anim_time * 0.8 + node.phase) * 1.5
            drift_y = math.cos(self._anim_time * 0.6 + node.phase * 1.3) * 1.5
            return node.x + drift_x, node.y + drift_y
        return node.x, node.y

    # --- Mouse interaction ---

    def mouseMoveEvent(self, event):
        nodes = self.engine.nodes
        if not nodes:
            return

        pos = event.position()
        mx, my = pos.x(), pos.y()

        closest = -1
        min_d = float('inf')

        for i, node in enumerate(nodes):
            ax, ay = self._animated_pos(node)
            dx = mx - ax
            dy = my - ay
            d = math.sqrt(dx * dx + dy * dy)
            hit_r = node.radius + 8  # Generous hit area
            if d < hit_r and d < min_d:
                min_d = d
                closest = i

        if closest != self._hovered_node:
            self._hovered_node = closest
            if closest >= 0:
                self.setCursor(Qt.PointingHandCursor)
                self.node_hovered.emit(nodes[closest].id)
            else:
                self.setCursor(Qt.ArrowCursor)
            self.update()

    def mousePressEvent(self, event):
        if self._hovered_node >= 0:
            self._selected_node = self._hovered_node
            node = self.engine.nodes[self._selected_node]
            self.node_clicked.emit(node.id)
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.engine.nodes:
            # Scale positions to new size
            old_w = self.engine.width
            old_h = self.engine.height
            new_w = max(self.width(), 200)
            new_h = max(self.height(), 200)

            if old_w > 0 and old_h > 0:
                sx = new_w / old_w
                sy = new_h / old_h
                for node in self.engine.nodes:
                    node.x *= sx
                    node.y *= sy

            self.engine.width = new_w
            self.engine.height = new_h
            self.engine.compute_edge_bundling()


# ---------------------------------------------------------------------------
# Controls panel
# ---------------------------------------------------------------------------

class GraphControls(QWidget):
    """Side panel with graph layout controls."""

    generate_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedWidth(260)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title
        title = QLabel("GRAPH CONTROLS")
        title.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1px;"
        )
        layout.addWidget(title)

        # Layout selector
        layout.addWidget(QLabel("Layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["Force-directed", "Circular",
                                     "Hierarchical", "Random"])
        layout.addWidget(self.layout_combo)

        # Separator
        sep = QLabel("─" * 30)
        sep.setStyleSheet(f"color: {Colors.BORDER};")
        layout.addWidget(sep)

        # Repulsion slider (k_r)
        layout.addWidget(QLabel("Repulsion (k_r):"))
        self.kr_slider = QSlider(Qt.Horizontal)
        self.kr_slider.setRange(100, 30000)
        self.kr_slider.setValue(8000)
        layout.addWidget(self.kr_slider)
        self.kr_label = QLabel("8000")
        self.kr_label.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 10px;")
        layout.addWidget(self.kr_label)
        self.kr_slider.valueChanged.connect(
            lambda v: self.kr_label.setText(str(v)))

        # Attraction slider (k_a)
        layout.addWidget(QLabel("Attraction (k_a):"))
        self.ka_slider = QSlider(Qt.Horizontal)
        self.ka_slider.setRange(1, 200)
        self.ka_slider.setValue(5)
        layout.addWidget(self.ka_slider)
        self.ka_label = QLabel("0.005")
        self.ka_label.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 10px;")
        layout.addWidget(self.ka_label)
        self.ka_slider.valueChanged.connect(
            lambda v: self.ka_label.setText(f"{v / 1000:.3f}"))

        # Gravity slider (k_g)
        layout.addWidget(QLabel("Gravity (k_g):"))
        self.kg_slider = QSlider(Qt.Horizontal)
        self.kg_slider.setRange(1, 200)
        self.kg_slider.setValue(20)
        layout.addWidget(self.kg_slider)
        self.kg_label = QLabel("0.020")
        self.kg_label.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 10px;")
        layout.addWidget(self.kg_label)
        self.kg_slider.valueChanged.connect(
            lambda v: self.kg_label.setText(f"{v / 1000:.3f}"))

        # Separator
        sep2 = QLabel("─" * 30)
        sep2.setStyleSheet(f"color: {Colors.BORDER};")
        layout.addWidget(sep2)

        # Edge bundling toggle
        self.bundle_check = QCheckBox("Edge bundling")
        self.bundle_check.setChecked(True)
        layout.addWidget(self.bundle_check)

        # Animate toggle
        self.animate_check = QCheckBox("Animate")
        self.animate_check.setChecked(True)
        layout.addWidget(self.animate_check)

        # Separator
        sep3 = QLabel("─" * 30)
        sep3.setStyleSheet(f"color: {Colors.BORDER};")
        layout.addWidget(sep3)

        # Regenerate button
        gen_btn = QPushButton("  Regenerate")
        gen_btn.setIcon(icon("refresh", Colors.BG))
        gen_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.ACCENT}; color: {Colors.BG};
                border: none; border-radius: 6px; padding: 8px;
                font-weight: 700; font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Colors.ACCENT_BRIGHT};
            }}
        """)
        gen_btn.clicked.connect(self.generate_requested.emit)
        layout.addWidget(gen_btn)

        layout.addStretch()

        # Info block
        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 10px; padding: 8px;"
        )
        layout.addWidget(self.info)

        # Apply dark theme styling
        self.setStyleSheet(f"""
            background-color: {Colors.BG_RAISED};
            QLabel {{ color: {Colors.TEXT}; font-size: 11px; }}
        """)

    def get_layout_name(self) -> str:
        mapping = {
            "Force-directed": "force",
            "Circular": "circular",
            "Hierarchical": "hierarchical",
            "Random": "random",
        }
        return mapping.get(self.layout_combo.currentText(), "force")


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

class GraphView(QWidget):
    """Knowledge Graph view — composes canvas + controls in QSplitter."""

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

        # Header bar
        hdr = QHBoxLayout()
        hdr.setContentsMargins(12, 8, 12, 8)

        title = QLabel("Knowledge Graph")
        title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: 14px; font-weight: 700;"
        )
        hdr.addWidget(title)

        sub = QLabel(
            "Force-directed · Fruchterman-Reingold · "
            "Bézier edges · Celestial network"
        )
        sub.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        hdr.addWidget(sub)
        hdr.addStretch()

        hdr_w = QWidget()
        hdr_w.setLayout(hdr)
        hdr_w.setStyleSheet(
            f"background-color: {Colors.BG_RAISED}; "
            f"border-bottom: 1px solid {Colors.BORDER};"
        )
        layout.addWidget(hdr_w)

        # Main splitter: canvas left, controls right
        splitter = QSplitter(Qt.Horizontal)

        self.canvas = GraphCanvas()
        splitter.addWidget(self.canvas)

        self.controls = GraphControls()
        splitter.addWidget(self.controls)

        splitter.setSizes([700, 260])
        layout.addWidget(splitter, stretch=1)

        # Connect signals
        self.controls.generate_requested.connect(self._regenerate)
        self.controls.layout_combo.currentTextChanged.connect(
            self._on_layout_changed)
        self.controls.bundle_check.toggled.connect(self.canvas.set_bundling)
        self.controls.animate_check.toggled.connect(self.canvas.set_animating)

        self.canvas.node_clicked.connect(self._on_node_clicked)
        self.canvas.node_hovered.connect(self._on_node_hovered)

        self.setStyleSheet(f"background-color: {Colors.BG};")

    def load_nodes(self, nodes: list[dict]):
        """Build the graph from node connections."""
        self._nodes = nodes
        self._regenerate()

    def _regenerate(self):
        if not self._nodes:
            return

        layout = self.controls.get_layout_name()

        # If force-directed, apply current physics params
        if layout == "force":
            kr = self.controls.kr_slider.value()
            ka = self.controls.ka_slider.value() / 1000.0
            kg = self.controls.kg_slider.value() / 1000.0
            self.canvas.engine.k_repulsion = kr
            self.canvas.engine.k_attraction = ka
            self.canvas.engine.k_gravity = kg

        self.canvas.set_nodes(self._nodes, layout)

        # Update info panel
        n_nodes = len(self.canvas.engine.nodes)
        n_edges = len(self.canvas.engine.edges)
        max_deg = max((n.degree for n in self.canvas.engine.nodes), default=0)
        avg_deg = sum(n.degree for n in self.canvas.engine.nodes) / max(n_nodes, 1)
        density = (2 * n_edges) / max(n_nodes * (n_nodes - 1), 1)

        self.controls.info.setText(
            f"Nodes: {n_nodes}\n"
            f"Edges: {n_edges}\n"
            f"Max degree: {max_deg}\n"
            f"Avg degree: {avg_deg:.1f}\n"
            f"Density: {density:.4f}\n"
            f"{'Settled' if self.canvas.engine.settled else 'Running...'}"
        )

    def _on_layout_changed(self, text: str):
        if not self._nodes:
            return
        self._regenerate()

    def _on_node_clicked(self, node_id: str):
        """Handle node click — emit status message."""
        # Find node info
        for node in self.canvas.engine.nodes:
            if node.id == node_id:
                self.signals.status_message.emit(
                    f"Node: {node.label} | "
                    f"Degree: {node.degree} | "
                    f"Category: {node.category or 'unknown'}"
                )
                break

    def _on_node_hovered(self, node_id: str):
        """Handle node hover."""
        for node in self.canvas.engine.nodes:
            if node.id == node_id:
                # Could emit tooltip info
                break

    def get_params(self) -> list:
        return [
            {"name": "max_neighbors", "label": "Max Neighbors",
             "type": "spin", "min": 1, "max": 256, "default": 50},
            {"name": "traverse_depth", "label": "Traverse Depth",
             "type": "spin", "min": 1, "max": 20, "default": 3},
        ]
