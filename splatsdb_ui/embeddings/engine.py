# SPDX-License-Identifier: GPL-3.0
"""Multi-model embedding engine.

Supports:
  - llama-embed-nemotron-8b (local CUDA/CPU via PyTorch)
  - sentence-transformers (any HF model)
  - ONNX Runtime (fast CPU inference)
  - Remote API (vLLM, HuggingFace TEI)

Users can switch models at runtime via the UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import numpy as np


@dataclass
class ModelInfo:
    """Metadata for an embedding model."""
    name: str
    display_name: str
    dimension: int
    provider: str          # nemotron | sentence | onnx | remote
    path: Optional[str]    # local model path
    device: str = "auto"   # auto | cuda | cpu
    loaded: bool = False
    size_gb: float = 0.0


class EmbeddingProvider(ABC):
    """Base class for embedding providers."""

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts → (N, D) float32 array."""
        ...

    @abstractmethod
    def encode_one(self, text: str) -> np.ndarray:
        """Encode a single text → (D,) float32 array."""
        ...

    @abstractmethod
    def dim(self) -> int:
        """Return the embedding dimension."""
        ...

    @abstractmethod
    def model_name(self) -> str:
        """Return the model name."""
        ...

    @abstractmethod
    def unload(self):
        """Release model resources."""
        ...


class NemotronProvider(EmbeddingProvider):
    """llama-embed-nemotron-8b — NVIDIA's 8B embedding model.

    Loads from a local path (e.g. ~/models/llama-embed-nemotron-8b).
    Uses PyTorch + Transformers. Supports CUDA and CPU.
    """

    def __init__(self, model_path: str, device: str = "auto"):
        self._model_path = model_path
        self._device = self._resolve_device(device)
        self._model = None
        self._tokenizer = None
        self._dim = 4096  # nemotron-8b output dimension

    def _resolve_device(self, device: str) -> str:
        if device == "auto":
            try:
                import torch
                return "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return device

    def load(self):
        """Load model and tokenizer."""
        from transformers import AutoModel, AutoTokenizer
        import torch

        self._tokenizer = AutoTokenizer.from_pretrained(self._model_path)
        self._model = AutoModel.from_pretrained(self._model_path).to(self._device)
        self._model.eval()

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    def encode(self, texts: list[str]) -> np.ndarray:
        import torch

        if self._model is None:
            self.load()

        encoded = self._tokenizer(
            texts, padding=True, truncation=True, max_length=512, return_tensors="pt"
        )
        encoded = {k: v.to(self._device) for k, v in encoded.items()}

        with torch.no_grad():
            outputs = self._model(**encoded)
            # Use CLS token or mean pooling
            embeddings = outputs.last_hidden_state[:, 0, :]

        # Normalize
        norms = embeddings.norm(dim=1, keepdim=True)
        embeddings = embeddings / norms.clamp(min=1e-8)

        return embeddings.cpu().numpy().astype(np.float32)

    def dim(self) -> int:
        return self._dim

    def model_name(self) -> str:
        return "llama-embed-nemotron-8b"

    def unload(self):
        import gc
        self._model = None
        self._tokenizer = None
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


class SentenceProvider(EmbeddingProvider):
    """sentence-transformers provider — loads any HF model."""

    def __init__(self, model_name: str, device: str = "auto"):
        self._model_name = model_name
        self._device = self._resolve_device(device)
        self._model = None
        self._dim = 0

    def _resolve_device(self, device: str) -> str:
        if device == "auto":
            try:
                import torch
                return "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return device

    def load(self):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self._model_name, device=self._device)
        self._dim = self._model.get_sentence_embedding_dimension()

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            self.load()
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return np.array(embeddings, dtype=np.float32)

    def dim(self) -> int:
        if self._dim == 0:
            self.load()
        return self._dim

    def model_name(self) -> str:
        return self._model_name

    def unload(self):
        self._model = None
        import gc
        gc.collect()


class ONNXProvider(EmbeddingProvider):
    """ONNX Runtime provider — fast CPU inference for quantized models."""

    def __init__(self, model_path: str):
        self._model_path = model_path
        self._session = None
        self._dim = 0

    def load(self):
        import onnxruntime as ort
        self._session = ort.InferenceSession(self._model_path)
        # Get output dimension from model
        output_info = self._session.get_outputs()[0]
        self._dim = output_info.shape[-1] if isinstance(output_info.shape[-1], int) else 384

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._session is None:
            self.load()
        # Tokenize externally (simple whitespace for now, use tokenizer in production)
        # This is a placeholder — real impl would use the model's tokenizer
        raise NotImplementedError("ONNX provider requires tokenizer integration")

    def dim(self) -> int:
        return self._dim

    def model_name(self) -> str:
        return f"onnx:{Path(self._model_path).stem}"

    def unload(self):
        self._session = None


class RemoteProvider(EmbeddingProvider):
    """Remote embedding API — vLLM, HuggingFace TEI, or custom."""

    def __init__(self, url: str, model_name: str = "remote", dim: int = 384):
        self._url = url.rstrip("/")
        self._model_name = model_name
        self._dim = dim

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    def encode(self, texts: list[str]) -> np.ndarray:
        import httpx
        r = httpx.post(
            f"{self._url}/embed",
            json={"texts": texts},
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        return np.array(data["embeddings"], dtype=np.float32)

    def dim(self) -> int:
        return self._dim

    def model_name(self) -> str:
        return self._model_name

    def unload(self):
        pass  # No local resources


class EmbeddingEngine:
    """Central embedding engine — manages multiple models, switches at runtime.

    Usage:
        engine = EmbeddingEngine()
        engine.register_model(ModelInfo(
            name="nemotron-8b",
            display_name="LLaMA-Embed Nemotron 8B",
            dimension=4096,
            provider="nemotron",
            path="llama-embed-nemotron-8b",
            size_gb=16.0,
        ))
        engine.set_active("nemotron-8b")
        vectors = engine.encode(["Hello world", "Vector search"])
    """

    def __init__(self, models_dir: str = ""):
        self._models_dir = Path(models_dir) if models_dir else Path.home() / "models"
        self._registry: dict[str, ModelInfo] = {}
        self._providers: dict[str, EmbeddingProvider] = {}
        self._active: Optional[str] = None

    def register_model(self, info: ModelInfo):
        """Register a model in the engine."""
        self._registry[info.name] = info

    def unregister_model(self, name: str):
        """Remove a model. Unloads if active."""
        if name == self._active:
            self.unload_active()
        self._registry.pop(name, None)
        self._providers.pop(name, None)

    def available_models(self) -> list[ModelInfo]:
        """List all registered models."""
        return list(self._registry.values())

    def set_active(self, name: str, device: str = "auto"):
        """Switch the active model. Unloads previous if different."""
        if name not in self._registry:
            raise ValueError(f"Model '{name}' not registered")

        if self._active and self._active != name:
            self.unload_active()

        info = self._registry[name]
        provider = self._create_provider(info, device)
        self._providers[name] = provider
        self._active = name
        info.loaded = True
        info.device = device

    def _create_provider(self, info: ModelInfo, device: str) -> EmbeddingProvider:
        """Instantiate the correct provider for a model."""
        if info.provider == "nemotron":
            return NemotronProvider(info.path, device=device)
        elif info.provider == "sentence":
            return SentenceProvider(info.path or info.name, device=device)
        elif info.provider == "onnx":
            return ONNXProvider(info.path)
        elif info.provider == "remote":
            return RemoteProvider(info.path or "", model_name=info.name, dim=info.dimension)
        else:
            raise ValueError(f"Unknown provider: {info.provider}")

    def unload_active(self):
        """Unload the current active model."""
        if self._active and self._active in self._providers:
            self._providers[self._active].unload()
            self._registry[self._active].loaded = False
            self._active = None

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts using the active model."""
        if not self._active:
            raise RuntimeError("No active model set")
        provider = self._providers.get(self._active)
        if not provider:
            raise RuntimeError(f"Provider not loaded for '{self._active}'")
        return provider.encode(texts)

    def encode_one(self, text: str) -> np.ndarray:
        """Encode a single text."""
        return self.encode([text])[0]

    @property
    def active_model(self) -> Optional[str]:
        return self._active

    @property
    def active_dimension(self) -> int:
        if self._active and self._active in self._providers:
            return self._providers[self._active].dim()
        info = self._registry.get(self._active) if self._active else None
        return info.dimension if info else 0

    def auto_discover(self) -> list[ModelInfo]:
        """Scan models_dir for known model formats and register them."""
        discovered = []
        if not self._models_dir.exists():
            return discovered

        for path in sorted(self._models_dir.iterdir()):
            if not path.is_dir():
                continue
            # Check for HF model markers
            config_file = path / "config.json"
            if config_file.exists():
                name = path.name
                if name not in self._registry:
                    # Try to determine model type
                    info = ModelInfo(
                        name=name,
                        display_name=name.replace("-", " ").replace("_", " ").title(),
                        dimension=self._guess_dimension(path),
                        provider="nemotron" if "nemotron" in name.lower() else "sentence",
                        path=str(path),
                        size_gb=self._guess_size(path),
                    )
                    self.register_model(info)
                    discovered.append(info)

        return discovered

    def _guess_dimension(self, path: Path) -> int:
        """Guess dimension from config.json."""
        try:
            import json
            with open(path / "config.json") as f:
                cfg = json.load(f)
            return cfg.get("hidden_size", 384)
        except Exception:
            return 384

    def _guess_size(self, path: Path) -> float:
        """Guess model size in GB."""
        total = 0
        for f in path.rglob("*.safetensors"):
            total += f.stat().st_size
        for f in path.rglob("*.bin"):
            total += f.stat().st_size
        return total / 1e9
