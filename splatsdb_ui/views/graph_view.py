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
  Edge width:   proportional to weight^0.5 (thin for weak, thick for strong)
  Edge color:   source node category color (75/25 blend toward target)
  Edge labels:  hover-only tooltip showing relation type, weight, and score

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
    QMenu, QLineEdit, QToolTip,
)
from PySide6.QtCore import Signal, Qt, QTimer, QPointF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QPainterPath, QRadialGradient, QLinearGradient,
    QAction, QTextOption,
)
from PySide6.QtCore import QRectF, Property

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon

PHI = (1 + math.sqrt(5)) / 2  # Golden ratio ≈ 1.618

# ---------------------------------------------------------------------------
# Golden-ratio palette — used as fallback / category colors
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


def _palette_color(idx: int) -> QColor:
    """Return a QColor from the fixed palette (wraps around)."""
    r, g, b = _PALETTE[idx % len(_PALETTE)]
    return QColor(r, g, b)


def _node_color(idx: int) -> QColor:
    """Generate color via golden-ratio hue spacing."""
    hue = (idx * (1.0 / PHI)) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.65, 0.88)
    return QColor(int(r * 255), int(g * 255), int(b * 255))


# ---------------------------------------------------------------------------
# Graph data structures
# ---------------------------------------------------------------------------

class GraphNode:
    """A single node in the force-directed graph."""
    __slots__ = ('id', 'label', 'category', 'x', 'y', 'vx', 'vy',
                 'fx', 'fy', 'degree', 'radius', 'color', 'connections',
                 'mass', 'phase', 'original_idx', 'pinned', 'hidden')

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
        self.pinned = False  # if True, position is locked
        self.hidden = False  # if True, node is not rendered


class GraphEdge:
    """An edge between two graph nodes."""
    __slots__ = ('source_idx', 'target_idx', 'weight', 'score',
                 'ctrl_x', 'ctrl_y', 'relation_type')

    def __init__(self, src: int, tgt: int, weight: float = 1.0,
                 score: float = 0.0, relation_type: str = ""):
        self.source_idx = src
        self.target_idx = tgt
        self.weight = weight
        self.score = score
        self.ctrl_x = 0.0  # Bézier control point x
        self.ctrl_y = 0.0  # Bézier control point y
        self.relation_type = relation_type


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
                relation_type = conn.get("relation", conn.get("type", ""))

                edge = GraphEdge(i, j, weight, score, relation_type)
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
            # Pinned nodes don't move
            if node.pinned:
                node.vx = 0.0
                node.vy = 0.0
                continue

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
                total_weight = sum(self.edges[ei].weight for ei in edge_indices)
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
    node_navigate = Signal(str)  # emits node id — navigate to this node
    node_inspect = Signal(str)   # emits node id — inspect details

    def __init__(self):
        super().__init__()
        self.setMinimumSize(600, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.engine = ForceLayoutEngine()
        self._hovered_node: int = -1
        self._selected_node: int = -1
        self._hovered_edge: int = -1
        self._animating = True
        self._show_bundling = True
        self._show_edge_labels = True
        self._anim_time = 0.0

        # Search / filter state
        self._search_text: str = ""
        self._search_matches: set[int] = set()

        # Right-click context menu position tracking
        self._context_menu_node: int = -1

        # --- Zoom / Pan with smooth animation + momentum ---
        self._zoom = 1.0
        self._target_zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._target_pan_x = 0.0
        self._target_pan_y = 0.0
        self._panning = False
        self._pan_start_x = 0.0
        self._pan_start_y = 0.0
        self._pan_start_offset_x = 0.0
        self._pan_start_offset_y = 0.0
        # Momentum (inertia) for pan
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._last_pan_x = 0.0
        self._last_pan_y = 0.0
        self._momentum_active = False

        # Viewport culling cache
        self._visible_node_indices: list[int] = []
        self._visible_edge_indices: list[int] = []

        # Animation timer for gentle floating + smooth zoom/pan
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 FPS

        # Node data for tooltip
        self._node_data: list[dict] = []

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
        self._hovered_edge = -1
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

    def set_search_filter(self, text: str):
        """Set search text; nodes matching by label/id/category are highlighted."""
        self._search_text = text.strip().lower()
        self._search_matches.clear()
        if self._search_text:
            for i, node in enumerate(self.engine.nodes):
                if (self._search_text in node.label.lower() or
                        self._search_text in node.id.lower() or
                        self._search_text in node.category.lower()):
                    self._search_matches.add(i)
        self.update()

    def set_edge_labels(self, on: bool):
        self._show_edge_labels = on
        self.update()

    def _find_edge_at(self, pos_x: float, pos_y: float) -> int:
        """Find the edge index closest to the given canvas position, or -1.

        Uses point-to-quadratic-Bézier distance with adaptive sampling.
        """
        nodes = self.engine.nodes
        best_ei = -1
        best_d = float('inf')
        hit_threshold = 8.0  # pixels

        for ei, edge in enumerate(self.engine.edges):
            if edge.source_idx >= len(nodes) or edge.target_idx >= len(nodes):
                continue
            ni = nodes[edge.source_idx]
            nj = nodes[edge.target_idx]
            if ni.hidden or nj.hidden:
                continue

            ax, ay = self._animated_pos(ni)
            bx, by = self._animated_pos(nj)

            # Control point
            if self._show_bundling:
                cx = edge.ctrl_x
                cy = edge.ctrl_y
                t_off = math.sin(self._anim_time * 0.5 + edge.weight * 10) * 2
                cx += t_off
                cy += t_off
            else:
                cx = (ax + bx) / 2
                cy = (ay + by) / 2

            # Sample points along Bézier and check distance
            n_samples = 16
            for s in range(n_samples + 1):
                t = s / n_samples
                inv = 1.0 - t
                px = inv * inv * ax + 2 * inv * t * cx + t * t * bx
                py = inv * inv * ay + 2 * inv * t * cy + t * t * by
                dx = pos_x - px
                dy = pos_y - py
                d = math.sqrt(dx * dx + dy * dy)
                if d < best_d:
                    best_d = d
                    best_ei = ei

        if best_d <= hit_threshold:
            return best_ei
        return -1

    def _find_node_at(self, pos_x: float, pos_y: float) -> int:
        """Find the node index at the given canvas position, or -1."""
        nodes = self.engine.nodes
        closest = -1
        min_d = float('inf')
        for i, node in enumerate(nodes):
            if node.hidden:
                continue
            ax, ay = self._animated_pos(node)
            dx = pos_x - ax
            dy = pos_y - ay
            d = math.sqrt(dx * dx + dy * dy)
            hit_r = node.radius + 8
            if d < hit_r and d < min_d:
                min_d = d
                closest = i
        return closest

    def _show_context_menu(self, pos):
        """Show right-click context menu on a node."""
        idx = self._find_node_at(pos.x(), pos.y())
        if idx < 0:
            return

        self._context_menu_node = idx
        node = self.engine.nodes[idx]
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Colors.BG_RAISED};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 24px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {Colors.ACCENT};
                color: {Colors.BG};
            }}
            QMenu::separator {{
                height: 1px;
                background: {Colors.BORDER};
                margin: 4px 8px;
            }}
        """)

        # Navigate
        act_navigate = menu.addAction("🔗  Navigate")
        act_navigate.triggered.connect(self._ctx_navigate)

        # Inspect
        act_inspect = menu.addAction("🔍  Inspect")
        act_inspect.triggered.connect(self._ctx_inspect)

        menu.addSeparator()

        # Color by group — recolor all nodes sharing this node's category
        act_color = menu.addAction("🎨  Color by Group")
        act_color.triggered.connect(self._ctx_color_by_group)

        menu.addSeparator()

        # Hide
        act_hide = menu.addAction("👁‍🗨  Hide Node")
        act_hide.triggered.connect(self._ctx_hide)

        # Pin / Unpin
        if node.pinned:
            act_pin = menu.addAction("📌  Unpin Node")
        else:
            act_pin = menu.addAction("📌  Pin Node")
        act_pin.triggered.connect(self._ctx_toggle_pin)

        menu.exec(self.mapToGlobal(pos))

    def _ctx_navigate(self):
        idx = self._context_menu_node
        if 0 <= idx < len(self.engine.nodes):
            self.node_navigate.emit(self.engine.nodes[idx].id)
            self._selected_node = idx
            self.update()

    def _ctx_inspect(self):
        idx = self._context_menu_node
        if 0 <= idx < len(self.engine.nodes):
            self.node_inspect.emit(self.engine.nodes[idx].id)

    def _ctx_color_by_group(self):
        """Recolor all nodes that share the same category as the context node."""
        idx = self._context_menu_node
        if idx < 0 or idx >= len(self.engine.nodes):
            return
        target_cat = self.engine.nodes[idx].category
        if not target_cat:
            return
        # Pick a distinct color for this category
        cat_indices = [i for i, n in enumerate(self.engine.nodes)
                       if n.category == target_cat]
        base_color = _palette_color(hash(target_cat) % len(_PALETTE))
        for i in cat_indices:
            self.engine.nodes[i].color = QColor(base_color)
        self.update()

    def _ctx_hide(self):
        idx = self._context_menu_node
        if 0 <= idx < len(self.engine.nodes):
            self.engine.nodes[idx].hidden = True
            if self._selected_node == idx:
                self._selected_node = -1
            if self._hovered_node == idx:
                self._hovered_node = -1
            self.update()

    def _ctx_toggle_pin(self):
        idx = self._context_menu_node
        if 0 <= idx < len(self.engine.nodes):
            node = self.engine.nodes[idx]
            node.pinned = not node.pinned
            # Zero velocity when pinning
            if node.pinned:
                node.vx = 0.0
                node.vy = 0.0

    def _tick(self):
        """Animation tick — gentle floating oscillation + smooth zoom/pan."""
        if self._animating and self.engine.nodes:
            self._anim_time += 0.033

        # Smooth zoom interpolation (exponential ease)
        zoom_diff = self._target_zoom - self._zoom
        if abs(zoom_diff) > 0.002:
            self._zoom += zoom_diff * 0.18
        else:
            self._zoom = self._target_zoom

        # Smooth pan interpolation with momentum
        if self._momentum_active and not self._panning:
            self._vel_x *= 0.92  # Friction
            self._vel_y *= 0.92
            self._target_pan_x += self._vel_x
            self._target_pan_y += self._vel_y
            if abs(self._vel_x) < 0.1 and abs(self._vel_y) < 0.1:
                self._momentum_active = False

        pan_dx = self._target_pan_x - self._pan_x
        pan_dy = self._target_pan_y - self._pan_y
        if abs(pan_dx) > 0.5 or abs(pan_dy) > 0.5:
            self._pan_x += pan_dx * 0.2
            self._pan_y += pan_dy * 0.2
        else:
            self._pan_x = self._target_pan_x
            self._pan_y = self._target_pan_y

        self.update()

    # --- Rendering ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        self._paint_background(painter, w, h)

        # Apply zoom / pan transform for all graph content
        painter.save()
        painter.translate(w / 2.0 + self._pan_x, h / 2.0 + self._pan_y)
        painter.scale(self._zoom, self._zoom)
        painter.translate(-w / 2.0, -h / 2.0)

        # Viewport culling: compute visible bounds in layout coordinates
        self._compute_visible_set(w, h)

        self._paint_edges(painter)
        self._paint_edge_particles(painter)
        self._paint_hovered_edge_label(painter)
        self._paint_nodes(painter, w, h)

        painter.restore()

        # Minimap and info are drawn in screen coordinates (unzoomed)
        self._paint_minimap(painter, w, h)
        self._paint_info(painter, w, h)

        painter.end()

    def _compute_visible_set(self, w: int, h: int):
        """Compute which nodes/edges are visible in the current viewport."""
        inv_zoom = 1.0 / max(self._zoom, 0.01)
        margin = 60  # extra margin for node radius + glow
        # Visible rect in layout coordinates
        vx_min = (0 - w / 2.0 - self._pan_x) * inv_zoom + w / 2.0 - margin
        vy_min = (0 - h / 2.0 - self._pan_y) * inv_zoom + h / 2.0 - margin
        vx_max = (w - w / 2.0 - self._pan_x) * inv_zoom + w / 2.0 + margin
        vy_max = (h - h / 2.0 - self._pan_y) * inv_zoom + h / 2.0 + margin

        self._visible_node_indices = []
        for i, node in enumerate(self.engine.nodes):
            if node.hidden:
                continue
            ax, ay = self._animated_pos(node)
            r = node.radius
            if (ax - r < vx_max and ax + r > vx_min and
                    ay - r < vy_max and ay + r > vy_min):
                self._visible_node_indices.append(i)

        visible_set = set(self._visible_node_indices)
        self._visible_edge_indices = []
        for ei, edge in enumerate(self.engine.edges):
            if (edge.source_idx in visible_set or
                    edge.target_idx in visible_set):
                self._visible_edge_indices.append(ei)

    def _paint_background(self, painter: QPainter, w: int, h: int):
        """Deep space background with nebula clouds, twinkling stars, and grid."""
        import random

        # Base fill
        painter.fillRect(0, 0, w, h, QColor(Colors.BG))

        # --- Nebula clouds (large semi-transparent radial gradients) ---
        painter.setPen(Qt.NoPen)
        nebula_specs = [
            # (seed, cx_ratio, cy_ratio, r_ratio, r, g, b, peak_alpha)
            (101, 0.20, 0.30, 0.35, 80, 40, 120, 18),   # Deep purple (upper-left)
            (102, 0.75, 0.25, 0.30, 20, 80, 100, 14),   # Teal (upper-right)
            (103, 0.50, 0.70, 0.40, 120, 40, 80, 16),   # Magenta (lower-center)
            (104, 0.85, 0.75, 0.25, 40, 60, 100, 12),   # Indigo (lower-right)
            (105, 0.15, 0.80, 0.28, 20, 100, 80, 10),   # Sea-green (lower-left)
        ]
        for _seed, cx_r, cy_r, rr, nr, ng, nb, peak_a in nebula_specs:
            cx = w * cx_r
            cy = h * cy_r
            radius = max(w, h) * rr
            neb = QRadialGradient(cx, cy, radius)
            neb.setColorAt(0.0, QColor(nr, ng, nb, peak_a))
            neb.setColorAt(0.4, QColor(nr, ng, nb, peak_a // 2))
            neb.setColorAt(0.7, QColor(nr, ng, nb, peak_a // 4))
            neb.setColorAt(1.0, QColor(nr, ng, nb, 0))
            painter.setBrush(QBrush(neb))
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Radial vignette — darker at edges
        vignette = QRadialGradient(w / 2, h / 2, max(w, h) * 0.7)
        vignette.setColorAt(0.0, QColor(15, 17, 23, 0))
        vignette.setColorAt(0.6, QColor(15, 17, 23, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 120))
        painter.fillRect(0, 0, w, h, vignette)

        # --- Twinkling star-like dots ---
        rng = random.Random(42)  # Deterministic stars
        painter.setPen(Qt.NoPen)
        t = self._anim_time
        for _ in range(120):
            sx = rng.randint(0, max(w, 1))
            sy = rng.randint(0, max(h, 1))
            base_alpha = rng.randint(8, 35)
            # Each star gets a unique twinkle phase and speed
            phase = rng.uniform(0, 2 * math.pi)
            speed = rng.uniform(0.5, 2.5)
            # Sinusoidal twinkle: oscillate alpha ±50% around base
            twinkle = math.sin(t * speed + phase)
            alpha = int(base_alpha * (1.0 + 0.5 * twinkle))
            alpha = max(2, min(70, alpha))
            # Vary size: brighter stars are slightly larger
            size = 1 if base_alpha < 20 else (2 if rng.random() < 0.3 else 1)
            # Slight color tint for some stars
            if rng.random() < 0.15:
                # Warm-tinted star
                star_color = QColor(255, 220, 180, alpha)
            elif rng.random() < 0.15:
                # Cool-tinted star
                star_color = QColor(180, 200, 255, alpha)
            else:
                star_color = QColor(255, 255, 255, alpha)
            painter.setBrush(QBrush(star_color))
            painter.drawEllipse(sx, sy, size, size)

        # --- Subtle two-level grid overlay ---
        # Minor grid lines (very faint)
        minor_pen = QPen(QColor(255, 255, 255, 6), 0.5)
        painter.setPen(minor_pen)
        grid_minor = 40
        for x in range(0, w, grid_minor):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, grid_minor):
            painter.drawLine(0, y, w, y)

        # Major grid lines (slightly more visible, every 4th minor)
        major_pen = QPen(QColor(255, 255, 255, 12), 0.5)
        painter.setPen(major_pen)
        grid_major = grid_minor * 4
        for x in range(0, w, grid_major):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, grid_major):
            painter.drawLine(0, y, w, y)

    def _paint_edges(self, painter: QPainter):
        """Draw edges as quadratic Bézier curves with alpha gradients.

        Only draws edges in the visible set (viewport culling).
        """
        nodes = self.engine.nodes
        if not nodes:
            return

        hovered = self._hovered_node
        selected = self._selected_node

        # Determine which edges are highlighted
        highlight_set: set[int] = set()
        if hovered >= 0 or selected >= 0:
            active = hovered if hovered >= 0 else selected
            for ei in self._visible_edge_indices:
                edge = self.engine.edges[ei]
                if edge.source_idx == active or edge.target_idx == active:
                    highlight_set.add(ei)

        # Also ensure hovered edge is in the set even if outside culling
        if self._hovered_edge >= 0:
            highlight_set.add(self._hovered_edge)

        visible_edge_set = set(self._visible_edge_indices)
        # Always include highlighted edges
        draw_set = visible_edge_set | highlight_set

        for ei in draw_set:
            if ei >= len(self.engine.edges):
                continue
            edge = self.engine.edges[ei]
            if edge.source_idx >= len(nodes) or edge.target_idx >= len(nodes):
                continue

            ni = nodes[edge.source_idx]
            nj = nodes[edge.target_idx]

            # Skip edges involving hidden nodes
            if ni.hidden or nj.hidden:
                continue

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

            # Edge width: proportional to weight — thin for weak, thick for strong
            # weight^0.5 gives more visible contrast: 0.1→1.3px, 0.5→2.7px, 1.0→4.0px
            base_width = 0.8 + edge.weight ** 0.5 * 3.2
            if is_highlighted:
                base_width *= 1.5
            # Hovered edge gets extra emphasis
            if ei == self._hovered_edge:
                base_width *= 1.3

            # Color: source node category color (75%) blended toward target (25%)
            edge_color = Colors.lerp_color(nj.color, ni.color, 0.75)

            if is_dim:
                alpha = 15
            elif is_highlighted or ei == self._hovered_edge:
                alpha = int(80 + edge.weight * 140)
            else:
                alpha = int(25 + edge.weight * 60)

            # Draw with alpha gradient (stronger at endpoints, lighter at mid)
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

                pen_color = Colors.with_alpha(edge_color, max(5, seg_alpha))
                painter.setPen(QPen(pen_color, base_width * alpha_t,
                                    Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(prev_x, prev_y), QPointF(px, py))
                prev_x, prev_y = px, py

    def _paint_edge_particles(self, painter: QPainter):
        """Draw animated particles flowing along edges (source → target).

        Only draws particles for edges in the visible set (viewport culling).
        """
        nodes = self.engine.nodes
        if not nodes or not self._animating:
            return

        hovered = self._hovered_node
        selected = self._selected_node

        # Only show particles on highlighted edges (or all if none selected)
        has_selection = hovered >= 0 or selected >= 0
        active = hovered if hovered >= 0 else selected

        t = self._anim_time

        visible_set = set(self._visible_edge_indices)

        for ei in visible_set:
            edge = self.engine.edges[ei]
            if edge.source_idx >= len(nodes) or edge.target_idx >= len(nodes):
                continue

            # If a node is selected, only show particles on connected edges
            if has_selection:
                if edge.source_idx != active and edge.target_idx != active:
                    continue
                particle_count = 4
                particle_alpha = 160
            else:
                particle_count = 2
                particle_alpha = 70

            ni = nodes[edge.source_idx]
            nj = nodes[edge.target_idx]

            # Skip particles for hidden nodes
            if ni.hidden or nj.hidden:
                continue

            ax, ay = self._animated_pos(ni)
            bx, by = self._animated_pos(nj)

            # Control point (same as edge drawing)
            if self._show_bundling:
                cx = edge.ctrl_x
                cy = edge.ctrl_y
                t_off = math.sin(t * 0.5 + edge.weight * 10) * 2
                cx += t_off
                cy += t_off
            else:
                cx = (ax + bx) / 2
                cy = (ay + by) / 2

            # Edge color (same logic as _paint_edges: source category dominant)
            edge_color = Colors.lerp_color(nj.color, ni.color, 0.75)

            for p in range(particle_count):
                # Each particle has a unique phase offset so they're staggered
                phase = (p / particle_count)
                # Animate: particles flow from t=0 (source) to t=1 (target)
                progress = (t * 0.4 + phase + ei * 0.07) % 1.0

                # Quadratic Bézier position at this progress
                inv = 1.0 - progress
                px = inv * inv * ax + 2 * inv * progress * cx + progress * progress * bx
                py = inv * inv * ay + 2 * inv * progress * cy + progress * progress * by

                # Particle size: small dot, slightly larger near middle
                size_factor = 1.0 - abs(2.0 * progress - 1.0)  # peak at 0.5
                dot_r = 1.5 + size_factor * 1.5

                # Alpha: fade in at start, fade out at end
                fade = min(progress * 4.0, (1.0 - progress) * 4.0, 1.0)
                alpha = int(particle_alpha * fade)

                # Draw particle with a tiny glow
                glow_r = dot_r * 3.0
                glow = QRadialGradient(px, py, glow_r)
                glow.setColorAt(0.0, Colors.with_alpha(edge_color, alpha))
                glow.setColorAt(0.4, Colors.with_alpha(edge_color, alpha // 3))
                glow.setColorAt(1.0, Colors.with_alpha(edge_color, 0))

                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(QPointF(px, py), glow_r, glow_r)

                # Bright core dot
                painter.setBrush(QBrush(
                    Colors.with_alpha(QColor(255, 255, 255), alpha // 2)))
                painter.drawEllipse(QPointF(px, py), dot_r, dot_r)

    def _paint_hovered_edge_label(self, painter: QPainter):
        """Draw a label tooltip for the currently hovered edge only."""
        if self._hovered_edge < 0 or not self._show_edge_labels:
            return

        nodes = self.engine.nodes
        ei = self._hovered_edge
        if ei >= len(self.engine.edges):
            return

        edge = self.engine.edges[ei]
        if edge.source_idx >= len(nodes) or edge.target_idx >= len(nodes):
            return

        ni = nodes[edge.source_idx]
        nj = nodes[edge.target_idx]
        if ni.hidden or nj.hidden:
            return

        ax, ay = self._animated_pos(ni)
        bx, by = self._animated_pos(nj)

        # Control point
        if self._show_bundling:
            cx = edge.ctrl_x
            cy = edge.ctrl_y
            t_off = math.sin(self._anim_time * 0.5 + edge.weight * 10) * 2
            cx += t_off
            cy += t_off
        else:
            cx = (ax + bx) / 2
            cy = (ay + by) / 2

        # Label position: at t=0.5 on the Bézier (midpoint)
        mid_x = 0.25 * ax + 0.5 * cx + 0.25 * bx
        mid_y = 0.25 * ay + 0.5 * cy + 0.25 * by

        # Build label text
        label_parts = []
        if edge.relation_type:
            label_parts.append(edge.relation_type)
        label_parts.append(f"w: {edge.weight:.2f}")
        label_parts.append(f"s: {edge.score:.2f}")
        label_text = "  |  ".join(label_parts)

        # Measure text
        font_size = 10
        painter.setFont(QFont("sans-serif", font_size, QFont.Medium))
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(label_text)
        th = fm.height()

        # Background pill
        pad_x, pad_y = 8, 4
        pill_w = tw + pad_x * 2
        pill_h = th + pad_y * 2
        pill_x = mid_x - pill_w / 2
        pill_y = mid_y - pill_h - 6  # offset above the edge

        # Draw pill background with rounded rect
        edge_color = Colors.lerp_color(nj.color, ni.color, 0.75)
        bg_color = Colors.with_alpha(QColor(Colors.BG_RAISED), 220)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 5, 5)

        # Draw pill border using the edge's source-category color
        border_color = Colors.with_alpha(edge_color, 180)
        painter.setPen(QPen(border_color, 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 5, 5)

        # Draw colored accent dot before text
        dot_r = 3.0
        dot_x = pill_x + pad_x + dot_r
        dot_y = pill_y + pill_h / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(edge_color))
        painter.drawEllipse(QPointF(dot_x, dot_y), dot_r, dot_r)

        # Draw text
        text_color = QColor(Colors.TEXT)
        painter.setPen(QPen(text_color))
        text_x = pill_x + pad_x + dot_r * 2 + 4
        text_y = pill_y + pad_y + fm.ascent()
        painter.drawText(int(text_x), int(text_y), label_text)

    def _paint_nodes(self, painter: QPainter, w: int, h: int):
        """Draw nodes with concentric ring halos and glow.

        Only draws nodes in the visible set (viewport culling).
        """
        nodes = self.engine.nodes
        if not nodes:
            return

        hovered = self._hovered_node
        selected = self._selected_node
        has_search = len(self._search_matches) > 0 or self._search_text

        # Determine neighbor set for hover glow
        neighbor_set: set[int] = set()
        if hovered >= 0:
            for edge in self.engine.edges:
                if edge.source_idx == hovered:
                    neighbor_set.add(edge.target_idx)
                elif edge.target_idx == hovered:
                    neighbor_set.add(edge.source_idx)

        # Always ensure hovered/selected nodes are drawn
        always_draw = {hovered, selected} - {-1}
        visible_set = set(self._visible_node_indices) | always_draw

        for i in visible_set:
            if i < 0 or i >= len(nodes):
                continue
            node = nodes[i]
            # Skip hidden nodes entirely
            if node.hidden:
                continue

            ax, ay = self._animated_pos(node)

            is_hovered = i == hovered
            is_selected = i == selected
            is_neighbor = i in neighbor_set
            is_search_match = i in self._search_matches

            # Dim nodes that don't match the active search filter
            if has_search and not is_search_match:
                # Draw a dim ghost of the node
                r = node.radius
                dim_color = Colors.with_alpha(QColor(node.color), 25)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(dim_color))
                painter.drawEllipse(QPointF(ax, ay), r, r)
                # Skip label for dimmed nodes
                continue

            r = node.radius

            # --- Drop shadow (offset ellipse for depth) ---
            shadow_offset_x = r * 0.18
            shadow_offset_y = r * 0.25
            shadow_r = r * 1.35
            shadow_grad = QRadialGradient(
                ax + shadow_offset_x, ay + shadow_offset_y, shadow_r)
            shadow_alpha = 60 if (is_hovered or is_selected) else 35
            shadow_grad.setColorAt(0.0, QColor(0, 0, 0, shadow_alpha))
            shadow_grad.setColorAt(0.5, QColor(0, 0, 0, shadow_alpha // 3))
            shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(shadow_grad))
            painter.drawEllipse(
                QPointF(ax + shadow_offset_x, ay + shadow_offset_y),
                shadow_r, shadow_r)

            # --- Outer glow (QRadialGradient) ---
            glow_radius = r * (3.0 if is_hovered or is_selected else
                               (2.2 if is_neighbor else 1.8))
            glow = QRadialGradient(ax, ay, glow_radius)

            base_color = QColor(node.color)
            if is_hovered or is_selected:
                # Pulsating glow for selected/hovered nodes
                pulse = 0.5 + 0.5 * math.sin(
                    self._anim_time * 3.0 + node.phase * 0.5)
                glow_alpha_inner = int(80 + 40 * pulse)
                glow_alpha_mid = int(30 + 20 * pulse)
            elif is_neighbor:
                glow_alpha_inner = 60
                glow_alpha_mid = 20
            else:
                glow_alpha_inner = 35
                glow_alpha_mid = 10

            c_inner = Colors.with_alpha(base_color, glow_alpha_inner)
            c_mid = Colors.with_alpha(base_color, glow_alpha_mid)
            c_outer = Colors.with_alpha(base_color, 0)

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
                ring_alpha = int(40 / (ring + 0.5))
                if is_hovered or is_selected:
                    ring_alpha = int(ring_alpha * 2.0)
                elif is_neighbor:
                    ring_alpha = int(ring_alpha * 1.4)
                ring_color = Colors.with_alpha(QColor(node.color),
                                               min(ring_alpha, 200))
                painter.setPen(QPen(ring_color, 1.0))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(ax, ay), ring_r, ring_r)

            # --- Core node ---
            core_grad = QRadialGradient(ax - r * 0.2, ay - r * 0.2, r * 1.2)

            if is_hovered or is_selected:
                core_inner = Colors.with_alpha(
                    QColor(base_color).lighter(160), 240)
            elif is_neighbor:
                core_inner = Colors.with_alpha(
                    QColor(base_color).lighter(130), 200)
            else:
                core_inner = Colors.with_alpha(
                    QColor(base_color).lighter(115), 180)

            core_outer = Colors.with_alpha(
                QColor(base_color).darker(130), 120)

            core_grad.setColorAt(0.0, core_inner)
            core_grad.setColorAt(0.7, core_outer)
            core_grad.setColorAt(1.0, QColor(base_color).darker(200))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(core_grad))
            painter.drawEllipse(QPointF(ax, ay), r, r)

            # --- Border ---
            border_alpha = 200 if is_hovered or is_selected else 120
            border_color = Colors.with_alpha(
                QColor(base_color).lighter(
                    160 if is_hovered or is_selected else 130),
                border_alpha)
            border_w = 2.0 if is_selected else (1.5 if is_hovered else 1.0)
            painter.setPen(QPen(border_color, border_w))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(ax, ay), r, r)

            # --- Search match highlight ring ---
            if is_search_match and has_search:
                pulse = 0.5 + 0.5 * math.sin(self._anim_time * 4.0)
                ring_alpha = int(120 + 80 * pulse)
                highlight_color = Colors.with_alpha(QColor(Colors.ACCENT), ring_alpha)
                painter.setPen(QPen(highlight_color, 2.5))
                painter.setBrush(Qt.NoBrush)
                search_ring_r = r + 6
                painter.drawEllipse(QPointF(ax, ay), search_ring_r, search_ring_r)

            # --- Pin indicator ---
            if node.pinned:
                painter.setPen(Qt.NoPen)
                pin_color = Colors.with_alpha(QColor(Colors.ACCENT), 180)
                painter.setBrush(QBrush(pin_color))
                # Small diamond indicator at top of node
                pin_x = ax
                pin_y = ay - r - 5
                pin_s = 3.5
                pin_path = QPainterPath()
                pin_path.moveTo(pin_x, pin_y - pin_s)
                pin_path.lineTo(pin_x + pin_s, pin_y)
                pin_path.lineTo(pin_x, pin_y + pin_s)
                pin_path.lineTo(pin_x - pin_s, pin_y)
                pin_path.closeSubpath()
                painter.drawPath(pin_path)

            # --- Label with text shadow for readability ---
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

                bg = Colors.with_alpha(QColor(Colors.BG), 160)
                painter.fillRect(int(lx - 3), int(ly - th + 2),
                                 tw + 6, th + 2, bg)

                text_color = QColor(Colors.TEXT) if (
                    is_hovered or is_selected) else QColor(Colors.TEXT_DIM)
                # Text shadow (offset 1px, semi-transparent dark)
                shadow_color = Colors.with_alpha(QColor(0, 0, 0), 120)
                painter.setPen(QPen(shadow_color))
                painter.drawText(int(lx + 1), int(ly + 3), label)
                # Main text
                painter.setPen(QPen(text_color))
                painter.drawText(int(lx), int(ly + 2), label)

    def _paint_minimap(self, painter: QPainter, w: int, h: int):
        """Draw a polished minimap overview in the bottom-left corner."""
        nodes = self.engine.nodes
        if not nodes:
            return

        # Minimap dimensions and position
        mm_w, mm_h = 160, 110
        mm_margin = 10
        mm_x = mm_margin
        mm_y = h - mm_h - mm_margin

        # Find bounding box of all nodes
        xs = [n.x for n in nodes]
        ys = [n.y for n in nodes]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        graph_w = max(max_x - min_x, 1.0)
        graph_h = max(max_y - min_y, 1.0)

        # Add padding
        pad = 30
        min_x -= pad
        min_y -= pad
        graph_w += pad * 2
        graph_h += pad * 2

        # Scale to fit minimap with internal padding
        inner_pad = 8
        inner_w = mm_w - inner_pad * 2
        inner_h = mm_h - inner_pad * 2
        scale_x = inner_w / max(graph_w, 1.0)
        scale_y = inner_h / max(graph_h, 1.0)
        scale = min(scale_x, scale_y)

        # --- Background ---
        painter.setPen(Qt.NoPen)
        bg = Colors.with_alpha(QColor(Colors.BG), 200)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(mm_x, mm_y, mm_w, mm_h, 6, 6)

        # --- Border ---
        border_pen = QPen(QColor(Colors.BORDER), 1.0)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(mm_x, mm_y, mm_w, mm_h, 6, 6)

        # --- Accent top line ---
        painter.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        painter.drawLine(mm_x + 1, mm_y, mm_x + mm_w - 1, mm_y)

        # --- Label ---
        painter.setFont(QFont("monospace", 6))
        painter.setPen(QPen(QColor(Colors.TEXT_DIM)))
        painter.drawText(mm_x + 5, mm_y + 10, "OVERVIEW")

        # --- Draw edges on minimap ---
        for edge in self.engine.edges:
            if edge.source_idx >= len(nodes) or edge.target_idx >= len(nodes):
                continue
            ni = nodes[edge.source_idx]
            nj = nodes[edge.target_idx]
            if ni.hidden or nj.hidden:
                continue

            ex1 = mm_x + inner_pad + (ni.x - min_x) * scale
            ey1 = mm_y + inner_pad + (ni.y - min_y) * scale
            ex2 = mm_x + inner_pad + (nj.x - min_x) * scale
            ey2 = mm_y + inner_pad + (nj.y - min_y) * scale

            painter.setPen(QPen(QColor(255, 255, 255, 25), 0.5))
            painter.drawLine(QPointF(ex1, ey1), QPointF(ex2, ey2))

        # --- Draw nodes on minimap ---
        for i, node in enumerate(nodes):
            if node.hidden:
                continue
            nx = mm_x + inner_pad + (node.x - min_x) * scale
            ny = mm_y + inner_pad + (node.y - min_y) * scale

            dot_r = 1.5 if node.degree >= 3 else 1.0

            is_active = (i == self._hovered_node or
                         i == self._selected_node)
            if is_active:
                # Highlighted node on minimap
                painter.setPen(Qt.NoPen)
                glow = QRadialGradient(nx, ny, dot_r * 4)
                glow.setColorAt(0.0, Colors.with_alpha(QColor(node.color), 120))
                glow.setColorAt(1.0, Colors.with_alpha(QColor(node.color), 0))
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(QPointF(nx, ny), dot_r * 4, dot_r * 4)

                painter.setBrush(QBrush(QColor(node.color).lighter(150)))
                painter.drawEllipse(QPointF(nx, ny), dot_r * 1.5, dot_r * 1.5)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(
                    Colors.with_alpha(QColor(node.color), 140)))
                painter.drawEllipse(QPointF(nx, ny), dot_r, dot_r)

    def _paint_info(self, painter: QPainter, w: int, h: int):
        """Draw info overlay — bottom-right title block."""
        bw, bh = 180, 48
        x0, y0 = w - bw - 10, h - bh - 10

        painter.setPen(Qt.NoPen)
        bg = Colors.with_alpha(QColor(Colors.BG_RAISED), 180)
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

        # Handle panning (middle / right button drag)
        if self._panning:
            current_x = mx
            current_y = my
            old_pan_x = self._target_pan_x
            old_pan_y = self._target_pan_y
            self._target_pan_x = self._pan_start_offset_x + (current_x - self._pan_start_x)
            self._target_pan_y = self._pan_start_offset_y + (current_y - self._pan_start_y)
            # Track velocity for momentum
            self._vel_x = self._target_pan_x - old_pan_x
            self._vel_y = self._target_pan_y - old_pan_y
            self.update()
            return

        # Inverse-transform mouse coords to layout coordinates for hit testing
        w, h = self.width(), self.height()
        layout_mx = (mx - w / 2.0 - self._pan_x) / max(self._zoom, 0.01) + w / 2.0
        layout_my = (my - h / 2.0 - self._pan_y) / max(self._zoom, 0.01) + h / 2.0

        closest = -1
        min_d = float('inf')

        for i, node in enumerate(nodes):
            if node.hidden:
                continue
            ax, ay = self._animated_pos(node)
            dx = layout_mx - ax
            dy = layout_my - ay
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

        # Edge hover detection — only when no node is hovered
        if closest < 0:
            hovered_edge = self._find_edge_at(layout_mx, layout_my)
            if hovered_edge != self._hovered_edge:
                self._hovered_edge = hovered_edge
                if hovered_edge >= 0:
                    self.setCursor(Qt.CrossCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
                self.update()
        else:
            # Clear edge hover when a node is hovered
            if self._hovered_edge >= 0:
                self._hovered_edge = -1
                self.update()

    def mousePressEvent(self, event):
        # Middle or right button → start panning
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._panning = True
            self._momentum_active = False
            pos = event.position()
            self._pan_start_x = pos.x()
            self._pan_start_y = pos.y()
            self._pan_start_offset_x = self._target_pan_x
            self._pan_start_offset_y = self._target_pan_y
            self.setCursor(Qt.ClosedHandCursor)
            return

        if self._hovered_node >= 0:
            self._selected_node = self._hovered_node
            node = self.engine.nodes[self._selected_node]
            self.node_clicked.emit(node.id)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._panning = False
            self._momentum_active = True  # Enable momentum on release
            self.setCursor(Qt.ArrowCursor)

    def wheelEvent(self, event):
        """Smooth zoom toward mouse position via scroll wheel."""
        delta = event.angleDelta().y()
        factor = 1.12 if delta > 0 else 1.0 / 1.12
        new_target = max(0.15, min(8.0, self._target_zoom * factor))

        if new_target != self._target_zoom:
            pos = event.position()
            w, h = self.width(), self.height()
            mx, my = pos.x(), pos.y()

            # Mouse in layout coords before zoom change
            old_zoom = self._target_zoom
            layout_x = (mx - w / 2.0 - self._target_pan_x) / old_zoom + w / 2.0
            layout_y = (my - h / 2.0 - self._target_pan_y) / old_zoom + h / 2.0

            # After zoom change, adjust pan so same layout point stays under mouse
            self._target_pan_x = mx - w / 2.0 - (layout_x - w / 2.0) * new_target
            self._target_pan_y = my - h / 2.0 - (layout_y - h / 2.0) * new_target

            self._target_zoom = new_target

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

        # Edge hover labels toggle
        self.edge_labels_check = QCheckBox("Edge hover labels")
        self.edge_labels_check.setChecked(True)
        layout.addWidget(self.edge_labels_check)

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

        # Search / filter bar
        search_bar = QHBoxLayout()
        search_bar.setContentsMargins(12, 4, 12, 4)

        search_icon = QLabel("🔍")
        search_icon.setFixedWidth(20)
        search_bar.addWidget(search_icon)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "Search nodes by name, label, or category...")
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Colors.BG};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Colors.ACCENT};
            }}
        """)
        self._search_input.textChanged.connect(self._on_search_changed)
        search_bar.addWidget(self._search_input, stretch=1)

        self._search_count = QLabel("")
        self._search_count.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 10px;"
        )
        self._search_count.setFixedWidth(120)
        search_bar.addWidget(self._search_count)

        # Show All button (unhides hidden nodes)
        self._show_all_btn = QPushButton("Show All")
        self._show_all_btn.setFixedWidth(80)
        self._show_all_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.BG_RAISED};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {Colors.ACCENT};
                color: {Colors.BG};
            }}
        """)
        self._show_all_btn.clicked.connect(self._show_all_nodes)
        search_bar.addWidget(self._show_all_btn)

        search_w = QWidget()
        search_w.setLayout(search_bar)
        search_w.setStyleSheet(
            f"background-color: {Colors.BG_RAISED}; "
            f"border-bottom: 1px solid {Colors.BORDER};"
        )
        layout.addWidget(search_w)

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
        self.controls.edge_labels_check.toggled.connect(self.canvas.set_edge_labels)

        self.canvas.node_clicked.connect(self._on_node_clicked)
        self.canvas.node_hovered.connect(self._on_node_hovered)
        self.canvas.node_navigate.connect(self._on_node_navigate)
        self.canvas.node_inspect.connect(self._on_node_inspect)

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

    def _on_node_navigate(self, node_id: str):
        """Handle Navigate from context menu — emit status with details."""
        for node in self.canvas.engine.nodes:
            if node.id == node_id:
                # Build connections summary
                conn_ids = [c.get("id", "?") for c in node.connections[:5]]
                conn_str = ", ".join(conn_ids)
                if len(node.connections) > 5:
                    conn_str += f" (+{len(node.connections) - 5} more)"
                self.signals.status_message.emit(
                    f"Navigate → {node.label} | "
                    f"Degree: {node.degree} | "
                    f"Category: {node.category or 'unknown'} | "
                    f"Connected: {conn_str}"
                )
                break

    def _on_node_inspect(self, node_id: str):
        """Handle Inspect from context menu — show detailed node info."""
        for i, node in enumerate(self.canvas.engine.nodes):
            if node.id == node_id:
                lines = [
                    f"Node: {node.label}",
                    f"ID: {node.id}",
                    f"Category: {node.category or '—'}",
                    f"Degree: {node.degree}",
                    f"Position: ({node.x:.1f}, {node.y:.1f})",
                    f"Pinned: {node.pinned}",
                    f"Connections: {len(node.connections)}",
                ]
                # Show top connections with scores
                for ci, conn in enumerate(node.connections[:8]):
                    cid = conn.get("id", "?")
                    score = conn.get("score", 0)
                    lines.append(f"  → {cid} (score: {score:.2f})")
                if len(node.connections) > 8:
                    lines.append(
                        f"  ... and {len(node.connections) - 8} more")

                self.controls.info.setText("\n".join(lines))
                self.signals.status_message.emit(
                    f"Inspecting: {node.label}")
                break

    def _on_search_changed(self, text: str):
        """Handle search input text changes."""
        self.canvas.set_search_filter(text)
        n_matches = len(self.canvas._search_matches)
        n_total = len(self.canvas.engine.nodes)
        if text.strip():
            self._search_count.setText(
                f"{n_matches} / {n_total} nodes")
        else:
            self._search_count.setText("")

    def _show_all_nodes(self):
        """Unhide all hidden nodes."""
        for node in self.canvas.engine.nodes:
            node.hidden = False
        self.canvas.update()

    def get_params(self) -> list:
        return [
            {"name": "max_neighbors", "label": "Max Neighbors",
             "type": "spin", "min": 1, "max": 256, "default": 50},
            {"name": "traverse_depth", "label": "Traverse Depth",
             "type": "spin", "min": 1, "max": 20, "default": 3},
        ]
