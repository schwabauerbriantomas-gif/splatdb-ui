# SPDX-License-Identifier: GPL-3.0
"""Embedding worker — generates embeddings in a QThread."""

from PySide6.QtCore import QObject, Signal
import numpy as np


class EmbeddingWorker(QObject):
    """Generates embeddings using the active model in a background thread."""
    finished = Signal(object)  # np.ndarray
    progress = Signal(int)    # percentage
    error = Signal(str)

    def __init__(self, texts: list[str], engine=None, fallback_dim: int = 1024):
        super().__init__()
        self.texts = texts
        self.engine = engine
        self._fallback_dim = fallback_dim

    def run(self):
        try:
            if self.engine is None:
                # Fallback: return random vectors (dimension matches SplatDB v2.6 default)
                dim = self._fallback_dim
                result = np.random.randn(len(self.texts), dim).astype(np.float32)
                # Normalize
                norms = np.linalg.norm(result, axis=1, keepdims=True)
                result = result / np.maximum(norms, 1e-8)
                self.finished.emit(result)
                return

            total = len(self.texts)
            batch_size = 32
            all_embeddings = []

            for i in range(0, total, batch_size):
                batch = self.texts[i:i + batch_size]
                embeddings = self.engine.encode(batch)
                all_embeddings.append(embeddings)
                progress = min(100, int((i + len(batch)) / total * 100))
                self.progress.emit(progress)

            result = np.concatenate(all_embeddings, axis=0)
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))
