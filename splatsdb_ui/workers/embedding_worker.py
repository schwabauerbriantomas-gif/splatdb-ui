# SPDX-License-Identifier: GPL-3.0
"""Embedding worker — generates embeddings in a QThread."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, QThread
import numpy as np


class EmbeddingWorker(QObject):
    """Generates embeddings using the active model in a background thread."""

    finished = Signal(object)   # np.ndarray
    progress = Signal(int)      # percentage 0–100
    error = Signal(str)         # user-friendly error message

    def __init__(self, texts: list[str], engine=None, *, thread: QThread | None = None):
        super().__init__()
        self.texts = texts
        self.engine = engine
        self._thread = thread  # for isInterruptionRequested()

    def run(self):
        """Generate embeddings. Emits progress, then finished or error."""
        try:
            self.progress.emit(0)

            if not self.texts:
                self.error.emit("No texts provided for embedding.")
                self.finished.emit(np.array([]))
                return

            if self._is_cancelled():
                self.finished.emit(np.array([]))
                return

            if self.engine is None:
                # Fallback: return random vectors
                self.progress.emit(10)
                dim = 384
                total = len(self.texts)
                result = np.random.randn(total, dim).astype(np.float32)
                # Normalize
                norms = np.linalg.norm(result, axis=1, keepdims=True)
                result = result / np.maximum(norms, 1e-8)
                self.progress.emit(100)
                self.finished.emit(result)
                return

            total = len(self.texts)
            batch_size = 32
            all_embeddings = []

            for i in range(0, total, batch_size):
                if self._is_cancelled():
                    self.finished.emit(np.array([]))
                    return

                batch = self.texts[i:i + batch_size]

                try:
                    embeddings = self.engine.encode(batch)
                except MemoryError:
                    self.error.emit(
                        "Out of memory while generating embeddings.\n"
                        "Try processing fewer texts at once or reduce batch size."
                    )
                    self.finished.emit(np.array([]))
                    return
                except RuntimeError as exc:
                    err = str(exc).lower()
                    if "cuda" in err or "gpu" in err:
                        self.error.emit(
                            f"GPU error during embedding: {exc}\n"
                            "Try switching to CPU mode in engine settings."
                        )
                    else:
                        self.error.emit(f"Embedding generation failed: {exc}")
                    self.finished.emit(np.array([]))
                    return

                all_embeddings.append(embeddings)
                pct = min(100, int((i + len(batch)) / total * 100))
                self.progress.emit(pct)

            result = np.concatenate(all_embeddings, axis=0)
            self.progress.emit(100)
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(f"Embedding worker failed: {e}")
            self.finished.emit(np.array([]))

    def _is_cancelled(self) -> bool:
        """Check whether the hosting QThread has been requested to stop."""
        if self._thread is not None:
            return self._thread.isInterruptionRequested()
        return False
