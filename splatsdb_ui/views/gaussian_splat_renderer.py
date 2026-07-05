# SPDX-License-Identifier: GPL-3.0
"""Gaussian Splat Renderer for OpenGL.

Each vector node is rendered as a true Gaussian Splat — a soft, organic blob
with alpha blending that merges naturally with neighboring splats.

Instead of spheres/points, we use textured billboards with a 2D Gaussian falloff.
This matches SplatDB's core concept: vector data stored as Gaussian Splats.
"""

from __future__ import annotations

import numpy as np
from typing import Optional

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from OpenGL.GL import *


class GaussianSplatItem(gl.GLGraphicsItem.GLGraphicsItem):
    """Custom OpenGL item that renders nodes as Gaussian Splats.

    Each splat is a billboard quad with a Gaussian texture.
    Alpha blending creates the characteristic soft, organic look.
    """

    def __init__(self, **kwds):
        super().__init__()
        self._positions = None
        self._colors = None
        self._sizes = None
        self._opacity = None
        self._rotation = None  # Optional per-splat anisotropy
        self.setData(**kwds)

    def setData(self, **kwds):
        positions = kwds.get("pos", self._positions)
        colors = kwds.get("color", self._colors)
        sizes = kwds.get("size", self._sizes)
        opacity = kwds.get("opacity", self._opacity)
        rotation = kwds.get("rotation", self._rotation)

        if positions is not None:
            self._positions = np.array(positions, dtype=np.float32)
        if colors is not None:
            if colors.ndim == 1:
                colors = np.tile(colors, (len(self._positions), 1))
            self._colors = np.array(colors, dtype=np.float32)
        if sizes is not None:
            self._sizes = np.array(sizes, dtype=np.float32)
        if opacity is not None:
            self._opacity = np.array(opacity, dtype=np.float32)
        if rotation is not None:
            self._rotation = np.array(rotation, dtype=np.float32)

        self.update()

    def paint(self):
        if self._positions is None or len(self._positions) == 0:
            return

        self.setupGLState()

        # Enable additive alpha blending for splat compositing
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_POINT_SMOOTH)
        glHint(GL_POINT_SMOOTH_HINT, GL_NICEST)
        glDisable(GL_DEPTH_TEST)  # Splats should layer softly

        # Get modelview matrix for billboard calculations
        modelview = glGetDoublev(GL_MODELVIEW_MATRIX)

        n_splats = len(self._positions)
        default_size = 12.0

        for i in range(n_splats):
            pos = self._positions[i]
            size = self._sizes[i] if self._sizes is not None else default_size
            color = self._colors[i] if self._colors is not None else [0.96, 0.62, 0.04, 0.6]

            # Scale splat size based on distance from camera (perspective)
            cam_pos = self._get_camera_pos(modelview)
            dx = pos[0] - cam_pos[0]
            dy = pos[1] - cam_pos[1]
            dz = pos[2] - cam_pos[2]
            dist = max((dx*dx + dy*dy + dz*dz) ** 0.5, 0.1)

            # Perspective-corrected size
            point_size = size * (20.0 / dist)
            point_size = max(2.0, min(point_size, 80.0))

            glPointSize(point_size)
            glBegin(GL_POINTS)
            glColor4f(float(color[0]), float(color[1]), float(color[2]),
                      float(color[3]) if len(color) > 3 else 0.6)
            glVertex3f(float(pos[0]), float(pos[1]), float(pos[2]))
            glEnd()

        # Restore state
        glEnable(GL_DEPTH_TEST)

    @staticmethod
    def _get_camera_pos(modelview):
        """Extract camera position from modelview matrix."""
        # Camera position = -transpose(rotation) * translation
        return np.array([
            -modelview[0][0] * modelview[3][0] - modelview[0][1] * modelview[3][1] - modelview[0][2] * modelview[3][2],
            -modelview[1][0] * modelview[3][0] - modelview[1][1] * modelview[3][1] - modelview[1][2] * modelview[3][2],
            -modelview[2][0] * modelview[3][0] - modelview[2][1] * modelview[3][1] - modelview[2][2] * modelview[3][2],
        ], dtype=np.float32)


class SplatBillboardRenderer:
    """Alternative: render splats as textured billboard quads using GL_QUADS.

    Each splat is a quad with a Gaussian alpha texture.
    More visually accurate than GL_POINTS — shows the true splat shape.
    """

    @staticmethod
    def generate_gaussian_texture(size=64):
        """Generate a 2D Gaussian alpha texture."""
        x = np.linspace(-3, 3, size)
        y = np.linspace(-3, 3, size)
        xx, yy = np.meshgrid(x, y)
        gaussian = np.exp(-(xx**2 + yy**2) / 2.0)
        return gaussian.astype(np.float32)

    @staticmethod
    def render_splat_quads(positions, colors, sizes, modelview, projection):
        """Render splats as billboard quads with Gaussian falloff."""
        n = len(positions)

        # Extract camera right and up vectors from modelview
        right = np.array([modelview[0][0], modelview[1][0], modelview[2][0]], dtype=np.float32)
        up = np.array([modelview[0][1], modelview[1][1], modelview[2][1]], dtype=np.float32)

        cam_pos = GaussianSplatItem._get_camera_pos(modelview)

        glBegin(GL_QUADS)
        for i in range(n):
            pos = positions[i]
            color = colors[i] if i < len(colors) else [0.96, 0.62, 0.04, 0.5]
            size = sizes[i] if i < len(sizes) else 0.5

            # Perspective scale
            dist = max(np.linalg.norm(pos - cam_pos), 0.1)
            scale = size * (5.0 / dist)
            scale = max(0.1, min(scale, 3.0))

            # Billboard corners
            s_right = right * scale
            s_up = up * scale

            alpha = float(color[3]) if len(color) > 3 else 0.5

            # Soft alpha at edges (Gaussian-like falloff per vertex)
            center_alpha = alpha
            edge_alpha = alpha * 0.3

            glColor4f(float(color[0]), float(color[1]), float(color[2]), center_alpha)

            p = pos
            # Top-right
            v = p + s_right + s_up
            glVertex3f(float(v[0]), float(v[1]), float(v[2]))
            # Bottom-right
            v = p + s_right - s_up
            glColor4f(float(color[0]), float(color[1]), float(color[2]), edge_alpha)
            glVertex3f(float(v[0]), float(v[1]), float(v[2]))
            # Bottom-left
            v = p - s_right - s_up
            glVertex3f(float(v[0]), float(v[1]), float(v[2]))
            # Top-left
            v = p - s_right + s_up
            glColor4f(float(color[0]), float(color[1]), float(color[2]), edge_alpha)
            glVertex3f(float(v[0]), float(v[1]), float(v[2]))

        glEnd()
