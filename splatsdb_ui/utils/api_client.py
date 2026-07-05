# SPDX-License-Identifier: GPL-3.0
"""HTTP API client for SplatDB backend.

Mirrors the Rust API exactly:
  GET  /health           → HealthResponse
  POST /status           → StatusResponse
  POST /store            → StoreResponse
  POST /search           → SearchResponse

Plus optimization stats:
  GET  /optimization     → OptimizationMetrics + GpuConfig + CacheStats
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import httpx


@dataclass
class HealthResponse:
    status: str = ""
    version: str = ""


@dataclass
class StatusResponse:
    """Full backend status — mirrors Rust StatusResponse."""
    n_active: int = 0
    max_splats: int = 0
    dimension: int = 0
    has_hnsw: bool = False
    has_lsh: bool = False
    has_quantization: bool = False
    has_semantic_memory: bool = False


@dataclass
class StoreRequest:
    text: str
    category: Optional[str] = None
    id: Optional[str] = None
    embedding: Optional[list[float]] = None


@dataclass
class StoreResponse:
    id: str = ""
    status: str = ""


@dataclass
class SearchResult:
    """A single search result."""
    index: int = 0
    score: float = 0.0
    metadata: Optional[str] = None
    text: str = ""


@dataclass
class SearchResponse:
    results: list[SearchResult] = field(default_factory=list)


@dataclass
class OptimizationMetrics:
    total_queries: int = 0
    total_adds: int = 0
    gpu_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass
class GpuConfig:
    device_name: str = ""
    vram_mb: int = 0
    optimal_batch_size: int = 0
    compute_units: int = 0


@dataclass
class CacheStats:
    enabled: bool = False
    hits: int = 0
    misses: int = 0
    size: int = 0


class SplatDBClient:
    """HTTP client for SplatDB Axum backend.

    Endpoint mapping (Rust api_server.rs):
        GET  /health          → HealthResponse
        POST /status          → StatusResponse
        POST /store           → StoreResponse   (body: StoreRequest)
        POST /search          → SearchResponse  (body: SearchRequest)
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8199", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    def close(self):
        if self._client and not self._client.is_closed:
            self._client.close()

    # ── Health ─────────────────────────────────────────────────────

    def health(self) -> HealthResponse:
        r = self.client.get("/health")
        r.raise_for_status()
        d = r.json()
        return HealthResponse(status=d.get("status", ""), version=d.get("version", ""))

    def is_connected(self) -> bool:
        try:
            self.health()
            return True
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    # ── Status ─────────────────────────────────────────────────────

    def status(self) -> StatusResponse:
        r = self.client.post("/status")
        r.raise_for_status()
        d = r.json()
        return StatusResponse(
            n_active=d.get("n_active", 0),
            max_splats=d.get("max_splats", 0),
            dimension=d.get("dimension", 0),
            has_hnsw=d.get("has_hnsw", False),
            has_lsh=d.get("has_lsh", False),
            has_quantization=d.get("has_quantization", False),
            has_semantic_memory=d.get("has_semantic_memory", False),
        )

    # ── Store ──────────────────────────────────────────────────────

    def store(
        self,
        text: str,
        category: Optional[str] = None,
        doc_id: Optional[str] = None,
        embedding: Optional[list[float]] = None,
    ) -> StoreResponse:
        payload = {"text": text}
        if category:
            payload["category"] = category
        if doc_id:
            payload["id"] = doc_id
        if embedding:
            payload["embedding"] = embedding

        r = self.client.post("/store", json=payload)
        r.raise_for_status()
        d = r.json()
        return StoreResponse(id=d.get("id", ""), status=d.get("status", ""))

    def store_batch(self, documents: list[StoreRequest]) -> list[StoreResponse]:
        return [self.store(
            text=d.text,
            category=d.category,
            doc_id=d.id,
            embedding=d.embedding,
        ) for d in documents]

    # ── Search ─────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 10,
        embedding: Optional[list[float]] = None,
    ) -> SearchResponse:
        payload = {"query": query, "top_k": top_k}
        if embedding:
            payload["embedding"] = embedding

        r = self.client.post("/search", json=payload)
        r.raise_for_status()
        d = r.json()
        results = []
        for item in d.get("results", []):
            results.append(SearchResult(
                index=item.get("index", 0),
                score=item.get("score", 0.0),
                metadata=item.get("metadata"),
            ))
        return SearchResponse(results=results)

    # ── Optimization stats ─────────────────────────────────────────
    # NOTE: These endpoints (/optimization, /prefetch, /cache/clear)
    # do NOT exist in the current SplatDB api_server.rs (v2.6.0).
    # The structs exist in optimized_api.rs but are not wired to HTTP
    # routes. These methods return empty/false until the backend adds
    # them. Tracked for future implementation.

    def optimization_stats(self) -> dict:
        """Get optimization metrics (cache, GPU, query stats).

        Not yet implemented in SplatDB HTTP API (v2.6.0).
        Returns empty dict when unavailable.
        """
        try:
            r = self.client.get("/optimization")
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.HTTPError):
            return {}

    def prefetch_suggestions(self, n: int = 10) -> list[str]:
        """Get prefetch suggestions.

        Not yet implemented in SplatDB HTTP API (v2.6.0).
        Returns empty list when unavailable.
        """
        try:
            r = self.client.get(f"/prefetch?n={n}")
            r.raise_for_status()
            return r.json().get("suggestions", [])
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.HTTPError):
            return []

    def clear_cache(self) -> bool:
        """Clear query cache.

        Not yet implemented in SplatDB HTTP API (v2.6.0).
        Returns False when unavailable.
        """
        try:
            r = self.client.post("/cache/clear")
            r.raise_for_status()
            return True
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.HTTPError):
            return False
