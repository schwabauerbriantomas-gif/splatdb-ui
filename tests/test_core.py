#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0
"""Basic import and unit tests for splatsdb-ui."""

def test_imports():
    """Verify all modules import correctly."""
    from splatsdb_ui import __version__, __app_name__
    assert __version__ == "0.2.0"
    assert __app_name__ == "SplatDB"

    # Utils
    from splatsdb_ui.utils.signals import SignalBus
    from splatsdb_ui.utils.state import AppState
    from splatsdb_ui.utils.theme import DARK_QSS
    from splatsdb_ui.utils.api_client import (
        SplatDBClient, SearchResult, SearchResponse, StoreRequest,
        StoreResponse, StatusResponse, HealthResponse,
        OptimizationMetrics, GpuConfig, CacheStats,
    )

    # Engine management
    from splatsdb_ui.engine_manager import (
        EngineManager, EngineConfig, EngineStatus, EngineType,
        PRESETS, CONFIG_FIELDS,
    )
    assert len(PRESETS) == 8  # default, simple, advanced, training, distributed, mcp, gpu, custom
    assert len(CONFIG_FIELDS) >= 60  # All SplatDB config fields

    # Embeddings
    from splatsdb_ui.embeddings.engine import (
        EmbeddingEngine, ModelInfo, NemotronProvider,
        SentenceProvider, ONNXProvider, RemoteProvider,
    )
    from splatsdb_ui.embeddings.registry import KNOWN_MODELS, create_engine
    assert "llama-embed-nemotron-8b" in KNOWN_MODELS
    assert KNOWN_MODELS["llama-embed-nemotron-8b"].dimension == 4096
    # bge-m3 must be registered — matches SplatDB v2.6.0 default (1024d)
    assert "bge-m3" in KNOWN_MODELS
    assert KNOWN_MODELS["bge-m3"].dimension == 1024

    print("✅ All imports OK")


def test_engine_manager():
    """Test engine manager CRUD and presets."""
    import tempfile
    from pathlib import Path
    from splatsdb_ui.engine_manager import EngineManager, EngineConfig, PRESETS

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = EngineManager(Path(tmpdir))

        # Add engines
        local_cfg = EngineConfig(
            name="Local CPU",
            engine_type="local",
            binary_path="/usr/local/bin/splatsdb",
            port=8199,
            preset="default",
        )
        remote_cfg = EngineConfig(
            name="Remote Server",
            engine_type="remote",
            host="192.168.1.100",
            port=8080,
            preset="advanced",
            api_key="test-key",
        )
        manager.add_engine(local_cfg)
        manager.add_engine(remote_cfg)

        assert len(manager.list_engines()) == 2
        assert manager.get_engine("Local CPU") is not None
        assert manager.get_engine("Remote Server").url == "http://192.168.1.100:8080"

        # Switch
        manager.switch_engine("Remote Server")
        assert manager.active_name() == "Remote Server"

        # Remove
        manager.remove_engine("Local CPU")
        assert len(manager.list_engines()) == 1
        assert manager.active_name() == "Remote Server"

        # Presets
        assert len(PRESETS) == 8
        assert "description" in PRESETS["default"]
        assert PRESETS["gpu"]["device"] == "cuda"
        assert PRESETS["simple"]["max_splats"] == 10000

        # Persistence
        manager2 = EngineManager(Path(tmpdir))
        assert len(manager2.list_engines()) == 1

    print("✅ Engine manager OK")


def test_config_fields():
    """Verify all config fields map correctly."""
    from splatsdb_ui.engine_manager import CONFIG_FIELDS

    # Required groups
    groups = set(meta["group"] for meta in CONFIG_FIELDS.values())
    expected_groups = {
        "System", "Latent Space", "Splat Params", "Temperature", "Energy",
        "SOC", "Hardware", "Memory", "MoE Decoder", "Search", "HNSW", "LSH",
        "Quantization", "Graph", "Semantic", "MapReduce", "Auto-Scaling",
        "Quality", "Training", "Data Lake", "Entity", "GPU", "Langevin", "API",
    }
    for g in expected_groups:
        assert g in groups, f"Missing config group: {g}"

    # Key fields exist
    assert "device" in CONFIG_FIELDS
    assert "latent_dim" in CONFIG_FIELDS
    assert "max_splats" in CONFIG_FIELDS
    assert "enable_quantization" in CONFIG_FIELDS
    assert "enable_graph" in CONFIG_FIELDS
    assert "enable_semantic_memory" in CONFIG_FIELDS
    assert "hnsw_m" in CONFIG_FIELDS
    assert "quant_bits" in CONFIG_FIELDS
    assert "semantic_fusion" in CONFIG_FIELDS
    assert "search_backend" in CONFIG_FIELDS
    assert "enable_training" in CONFIG_FIELDS
    assert "enable_data_lake" in CONFIG_FIELDS
    assert "enable_gpu_search" in CONFIG_FIELDS

    print("✅ Config fields OK")


def test_presets_dimension():
    """Verify all presets use 1024d to match SplatDB v2.6.0 (bge-m3)."""
    from splatsdb_ui.engine_manager import PRESETS

    for name, preset in PRESETS.items():
        if name == "custom":
            continue
        assert preset["latent_dim"] == 1024, (
            f"Preset '{name}' has latent_dim={preset['latent_dim']}, expected 1024"
        )

    print("✅ All presets dimension OK")


def test_api_client():
    """Test API client data classes."""
    from splatsdb_ui.utils.api_client import (
        SearchResult, StatusResponse, StoreRequest, StoreResponse,
        HealthResponse, SearchResponse,
    )

    # Status response matches Rust struct (v2.6.0: latent_dim default is 1024)
    s = StatusResponse(n_active=1000, dimension=1024, has_hnsw=True, has_quantization=True)
    assert s.has_hnsw
    assert s.dimension == 1024

    # Search result
    r = SearchResult(index=0, score=0.95, metadata="test")
    assert r.score == 0.95

    # Store request
    sr = StoreRequest(text="hello", category="greeting")
    assert sr.text == "hello"

    # Search response
    resp = SearchResponse(results=[r])
    assert len(resp.results) == 1

    print("✅ API client OK")


def test_embedding_engine():
    """Test embedding engine model management."""
    from splatsdb_ui.embeddings.engine import EmbeddingEngine, ModelInfo

    engine = EmbeddingEngine(models_dir="/tmp/test_models")

    info = ModelInfo(
        name="test-model",
        display_name="Test Model",
        dimension=384,
        provider="sentence",
        path="all-MiniLM-L6-v2",
    )
    engine.register_model(info)
    assert len(engine.available_models()) == 1
    assert engine.active_model is None

    engine.unregister_model("test-model")
    assert len(engine.available_models()) == 0

    print("✅ Embedding engine OK")


if __name__ == "__main__":
    test_imports()
    test_engine_manager()
    test_config_fields()
    test_presets_dimension()
    test_api_client()
    test_embedding_engine()
    print("\n🟢 All tests passed!")
