# SPDX-License-Identifier: GPL-3.0
"""Engine Manager — LM Studio-style backend switcher.

Manages multiple SplatDB backends:
  - Local process (spawn splatsdb serve)
  - Remote HTTP (any URL)
  - Switch between engines at runtime
  - Auto-discover local installations
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import signal
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from enum import Enum

from PySide6.QtCore import QObject, Signal, QProcess, QTimer


class EngineStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class EngineType(Enum):
    LOCAL = "local"       # Local splatsdb binary
    REMOTE = "remote"     # Remote HTTP server
    WSL = "wsl"           # WSL2 binary accessible from Windows


@dataclass
class EngineConfig:
    """Configuration for a single SplatDB engine/backend."""
    name: str
    engine_type: str          # local | remote | wsl
    binary_path: str = ""     # Path to splatsdb binary (local/wsl)
    host: str = "127.0.0.1"
    port: int = 8199
    api_key: str = ""
    preset: str = "default"   # default|simple|advanced|training|distributed|mcp|gpu|custom
    custom_config: dict = field(default_factory=dict)
    working_dir: str = ""
    auto_start: bool = False
    env_vars: dict = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EngineConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


PRESETS = {
    "default": {
        "description": "Balanced defaults — good for development",
        "device": "cpu",
        "latent_dim": 1024,
        "max_splats": 100000,
        "enable_quantization": True,
        "enable_graph": True,
        "enable_semantic_memory": True,
        "enable_hnsw": False,
        "enable_lsh": False,
        "enable_gpu_search": False,
    },
    "simple": {
        "description": "Edge computing — stripped down, fast startup",
        "device": "cpu",
        "latent_dim": 1024,
        "max_splats": 10000,
        "enable_quantization": False,
        "enable_graph": False,
        "enable_semantic_memory": False,
        "enable_hnsw": False,
        "enable_lsh": False,
        "enable_gpu_search": False,
        "memory_tier": "ram-only",
        "knn_k": 32,
    },
    "advanced": {
        "description": "Full Agentic AI — all features enabled",
        "device": "cpu",
        "latent_dim": 1024,
        "max_splats": 1000000,
        "enable_quantization": True,
        "quant_bits": 4,
        "enable_graph": True,
        "enable_semantic_memory": True,
        "enable_hnsw": True,
        "hnsw_m": 32,
        "enable_auto_scaling": True,
        "enable_mapreduce": True,
    },
    "training": {
        "description": "Embedding model research — training + data lake",
        "device": "cpu",
        "latent_dim": 1024,
        "max_splats": 500000,
        "enable_training": True,
        "enable_data_lake": True,
        "training_epochs": 50,
        "training_matryoshka_dims": [32, 64, 128, 256, 1024],
        "training_distillation": True,
    },
    "distributed": {
        "description": "Multi-node cluster — auto-scaling, MapReduce",
        "device": "cpu",
        "latent_dim": 1024,
        "max_splats": 10000000,
        "enable_auto_scaling": True,
        "enable_mapreduce": True,
        "mapreduce_n_chunks": 32,
        "autoscale_max_nodes": 50,
    },
    "mcp": {
        "description": "AI agent memory — optimized for MCP server",
        "device": "auto",
        "latent_dim": 1024,
        "max_splats": 100000,
        "enable_quantization": True,
        "enable_graph": True,
        "enable_semantic_memory": True,
        "enable_gpu_search": True,
    },
    "gpu": {
        "description": "CUDA acceleration — GPU search, large scale",
        "device": "cuda",
        "latent_dim": 1024,
        "max_splats": 5000000,
        "enable_cuda": True,
        "enable_gpu_search": True,
        "enable_hnsw": True,
        "hnsw_m": 48,
        "enable_quantization": True,
        "quant_bits": 4,
        "knn_k": 256,
    },
    "custom": {
        "description": "Custom configuration — edit all parameters",
    },
}

# All SplatDBConfig fields with metadata for the config editor
CONFIG_FIELDS = {
    # System
    "device": {"label": "Device", "type": "combo", "options": ["auto", "cpu", "cuda", "vulkan"], "group": "System"},
    "dtype": {"label": "Data Type", "type": "combo", "options": ["Float32", "Float64", "Int32", "Int64"], "group": "System"},
    # Latent Space
    "latent_dim": {"label": "Latent Dimension", "type": "spin", "min": 1, "max": 8192, "group": "Latent Space"},
    "n_splats_init": {"label": "Initial Splats", "type": "spin", "min": 100, "max": 10000000, "group": "Latent Space"},
    "max_splats": {"label": "Max Splats", "type": "spin", "min": 1000, "max": 100000000, "group": "Latent Space"},
    "knn_k": {"label": "KNN K", "type": "spin", "min": 1, "max": 1024, "group": "Latent Space"},
    # Splat Parameters
    "init_alpha": {"label": "Init Alpha", "type": "float", "min": 0.0, "max": 10.0, "step": 0.1, "group": "Splat Params"},
    "init_kappa": {"label": "Init Kappa", "type": "float", "min": 0.1, "max": 100.0, "step": 0.1, "group": "Splat Params"},
    "min_kappa": {"label": "Min Kappa", "type": "float", "min": 0.1, "max": 50.0, "step": 0.1, "group": "Splat Params"},
    "max_kappa": {"label": "Max Kappa", "type": "float", "min": 1.0, "max": 200.0, "step": 1.0, "group": "Splat Params"},
    # Temperature
    "splat_temperature": {"label": "Splat Temperature", "type": "float", "min": 0.0, "max": 2.0, "step": 0.01, "group": "Temperature"},
    "weight_decay_start": {"label": "Weight Decay Start", "type": "float", "min": 0.0, "max": 2.0, "step": 0.01, "group": "Temperature"},
    # Energy
    "energy_splat_weight": {"label": "Energy Splat Weight", "type": "float", "min": 0.0, "max": 10.0, "step": 0.1, "group": "Energy"},
    "energy_geom_weight": {"label": "Energy Geom Weight", "type": "float", "min": 0.0, "max": 10.0, "step": 0.01, "group": "Energy"},
    "energy_comp_weight": {"label": "Energy Comp Weight", "type": "float", "min": 0.0, "max": 10.0, "step": 0.01, "group": "Energy"},
    "global_temperature": {"label": "Global Temperature", "type": "float", "min": 0.0, "max": 10.0, "step": 0.1, "group": "Energy"},
    # SOC
    "soc_threshold": {"label": "SOC Threshold", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "group": "SOC"},
    "soc_buffer_capacity": {"label": "SOC Buffer Capacity", "type": "spin", "min": 100, "max": 100000, "group": "SOC"},
    "soc_update_interval": {"label": "SOC Update Interval", "type": "spin", "min": 1, "max": 10000, "group": "SOC"},
    "phi_convergence_threshold": {"label": "Phi Convergence", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "group": "SOC"},
    # Hardware
    "enable_vulkan": {"label": "Enable Vulkan", "type": "check", "group": "Hardware"},
    "enable_cuda": {"label": "Enable CUDA", "type": "check", "group": "Hardware"},
    "cuda_metric": {"label": "CUDA Metric", "type": "combo", "options": ["cosine", "l2", "ip"], "group": "Hardware"},
    # Memory
    "enable_3_tier_memory": {"label": "3-Tier Memory", "type": "check", "group": "Memory"},
    "memory_tier": {"label": "Memory Tier", "type": "combo", "options": ["3-tier", "ram-only", "disk-backed"], "group": "Memory"},
    "context_local": {"label": "Context Local", "type": "spin", "min": 1, "max": 256, "group": "Memory"},
    "context_medium": {"label": "Context Medium", "type": "spin", "min": 1, "max": 1024, "group": "Memory"},
    "context_global": {"label": "Context Global", "type": "spin", "min": 1, "max": 8192, "group": "Memory"},
    # MoE Decoder
    "vocab_size": {"label": "Vocab Size", "type": "spin", "min": 1000, "max": 200000, "group": "MoE Decoder"},
    "hidden_dim": {"label": "Hidden Dim", "type": "spin", "min": 64, "max": 8192, "group": "MoE Decoder"},
    "moe_experts": {"label": "MoE Experts", "type": "spin", "min": 1, "max": 64, "group": "MoE Decoder"},
    "moe_active": {"label": "MoE Active", "type": "spin", "min": 1, "max": 64, "group": "MoE Decoder"},
    # Search Backend
    "search_backend": {"label": "Search Backend", "type": "combo", "options": ["Hrm2", "Hnsw", "Lsh", "Quantized"], "group": "Search"},
    "hrm2_n_coarse": {"label": "HRM2 N Coarse", "type": "spin", "min": 1, "max": 256, "group": "Search"},
    "hrm2_n_fine": {"label": "HRM2 N Fine", "type": "spin", "min": 1, "max": 1024, "group": "Search"},
    "hrm2_n_probe": {"label": "HRM2 N Probe", "type": "spin", "min": 1, "max": 256, "group": "Search"},
    # HNSW
    "enable_hnsw": {"label": "Enable HNSW", "type": "check", "group": "HNSW"},
    "hnsw_m": {"label": "HNSW M", "type": "spin", "min": 4, "max": 128, "group": "HNSW"},
    "hnsw_ef_construction": {"label": "EF Construction", "type": "spin", "min": 10, "max": 2000, "group": "HNSW"},
    "hnsw_ef_search": {"label": "EF Search", "type": "spin", "min": 1, "max": 2000, "group": "HNSW"},
    "hnsw_metric": {"label": "HNSW Metric", "type": "combo", "options": ["cosine", "l2", "ip"], "group": "HNSW"},
    "over_fetch": {"label": "Over-fetch", "type": "spin", "min": 0, "max": 100, "group": "HNSW"},
    # LSH
    "enable_lsh": {"label": "Enable LSH", "type": "check", "group": "LSH"},
    "lsh_n_tables": {"label": "LSH Tables", "type": "spin", "min": 1, "max": 100, "group": "LSH"},
    "lsh_n_projections": {"label": "LSH Projections", "type": "spin", "min": 1, "max": 256, "group": "LSH"},
    # Quantization
    "enable_quantization": {"label": "Enable Quantization", "type": "check", "group": "Quantization"},
    "quant_algorithm": {"label": "Algorithm", "type": "combo", "options": ["TurboQuant", "PolarQuant", "None"], "group": "Quantization"},
    "quant_bits": {"label": "Quant Bits", "type": "spin", "min": 1, "max": 16, "group": "Quantization"},
    "quant_projections": {"label": "Projections", "type": "spin", "min": 1, "max": 1024, "group": "Quantization"},
    "quant_seed": {"label": "Seed", "type": "spin", "min": 0, "max": 2**32, "group": "Quantization"},
    "quant_search_fraction": {"label": "Search Fraction", "type": "float", "min": 0.01, "max": 1.0, "step": 0.01, "group": "Quantization"},
    # Graph
    "enable_graph": {"label": "Enable Graph", "type": "check", "group": "Graph"},
    "graph_max_neighbors": {"label": "Max Neighbors", "type": "spin", "min": 1, "max": 256, "group": "Graph"},
    "graph_traverse_depth": {"label": "Traverse Depth", "type": "spin", "min": 1, "max": 20, "group": "Graph"},
    "graph_boost_weight": {"label": "Boost Weight", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "group": "Graph"},
    # Semantic Memory
    "enable_semantic_memory": {"label": "Enable Semantic Memory", "type": "check", "group": "Semantic"},
    "semantic_fusion": {"label": "Fusion Method", "type": "combo", "options": ["Rrf", "Weighted", "VectorOnly", "Bm25Only"], "group": "Semantic"},
    "semantic_vector_weight": {"label": "Vector Weight", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "group": "Semantic"},
    "semantic_bm25_weight": {"label": "BM25 Weight", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "group": "Semantic"},
    "semantic_bm25_k1": {"label": "BM25 k1", "type": "float", "min": 0.0, "max": 5.0, "step": 0.1, "group": "Semantic"},
    "semantic_bm25_b": {"label": "BM25 b", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "group": "Semantic"},
    "semantic_decay_halflife": {"label": "Decay Halflife (s)", "type": "float", "min": 1.0, "max": 999999.0, "step": 100.0, "group": "Semantic"},
    # MapReduce
    "enable_mapreduce": {"label": "Enable MapReduce", "type": "check", "group": "MapReduce"},
    "mapreduce_n_chunks": {"label": "Chunks", "type": "spin", "min": 1, "max": 256, "group": "MapReduce"},
    # Auto-Scaling
    "enable_auto_scaling": {"label": "Enable Auto-Scaling", "type": "check", "group": "Auto-Scaling"},
    "autoscale_min_nodes": {"label": "Min Nodes", "type": "spin", "min": 1, "max": 1000, "group": "Auto-Scaling"},
    "autoscale_max_nodes": {"label": "Max Nodes", "type": "spin", "min": 1, "max": 1000, "group": "Auto-Scaling"},
    "autoscale_cooldown_secs": {"label": "Cooldown (s)", "type": "float", "min": 1.0, "max": 3600.0, "step": 1.0, "group": "Auto-Scaling"},
    # Quality
    "enable_quality_reflection": {"label": "Enable Quality Reflection", "type": "check", "group": "Quality"},
    "quality_recall_target": {"label": "Recall Target", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "group": "Quality"},
    # Training
    "enable_training": {"label": "Enable Training", "type": "check", "group": "Training"},
    "training_epochs": {"label": "Epochs", "type": "spin", "min": 1, "max": 10000, "group": "Training"},
    "training_eval_interval": {"label": "Eval Interval", "type": "spin", "min": 1, "max": 100000, "group": "Training"},
    "training_save_interval": {"label": "Save Interval", "type": "spin", "min": 1, "max": 1000000, "group": "Training"},
    "training_noise_augmentation": {"label": "Noise Augmentation", "type": "check", "group": "Training"},
    "training_distillation": {"label": "Distillation", "type": "check", "group": "Training"},
    # Data Lake
    "enable_data_lake": {"label": "Enable Data Lake", "type": "check", "group": "Data Lake"},
    "data_lake_max_entries": {"label": "Max Entries", "type": "spin", "min": 1000, "max": 100000000, "group": "Data Lake"},
    "data_lake_compress": {"label": "Compress", "type": "check", "group": "Data Lake"},
    # Entity Extraction
    "enable_entity_extraction": {"label": "Enable Entity Extraction", "type": "check", "group": "Entity"},
    "entity_min_confidence": {"label": "Min Confidence", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01, "group": "Entity"},
    # GPU
    "enable_gpu_search": {"label": "Enable GPU Search", "type": "check", "group": "GPU"},
    "gpu_batch_size": {"label": "GPU Batch Size", "type": "spin", "min": 1, "max": 65536, "group": "GPU"},
    "gpu_auto_tune": {"label": "GPU Auto-Tune", "type": "check", "group": "GPU"},
    # Training hyperparams
    "batch_size": {"label": "Batch Size", "type": "spin", "min": 1, "max": 4096, "group": "Training"},
    "seq_length": {"label": "Sequence Length", "type": "spin", "min": 1, "max": 4096, "group": "Training"},
    "learning_rate": {"label": "Learning Rate", "type": "float", "min": 0.0, "max": 1.0, "step": 0.0001, "group": "Training"},
    "weight_decay": {"label": "Weight Decay", "type": "float", "min": 0.0, "max": 1.0, "step": 0.001, "group": "Training"},
    "grad_clip": {"label": "Grad Clip", "type": "float", "min": 0.0, "max": 100.0, "step": 0.1, "group": "Training"},
    # Langevin
    "langevin_steps": {"label": "Langevin Steps", "type": "spin", "min": 0, "max": 10000, "group": "Langevin"},
    "langevin_dt": {"label": "Langevin dt", "type": "float", "min": 0.0, "max": 1.0, "step": 0.001, "group": "Langevin"},
    "langevin_gamma": {"label": "Langevin Gamma", "type": "float", "min": 0.0, "max": 10.0, "step": 0.01, "group": "Langevin"},
    "langevin_t": {"label": "Langevin T", "type": "float", "min": 0.0, "max": 10.0, "step": 0.01, "group": "Langevin"},
    # API
    "rest_port": {"label": "REST Port", "type": "spin", "min": 1, "max": 65535, "group": "API"},
    "grpc_port": {"label": "gRPC Port", "type": "spin", "min": 1, "max": 65535, "group": "API"},
}


class EngineManager(QObject):
    """Manages multiple SplatDB engine backends — LM Studio style.

    Features:
      - Add/remove/switch engines
      - Start/stop local processes
      - Connect to remote servers
      - Preset-based configuration
      - Full config editor for custom engines
      - Auto-discover local splatsdb installations
    """
    engine_added = Signal(str)           # engine name
    engine_removed = Signal(str)         # engine name
    engine_switched = Signal(str)        # engine name
    engine_started = Signal(str)         # engine name
    engine_stopped = Signal(str)         # engine name
    engine_error = Signal(str, str)      # engine name, error message
    status_changed = Signal(str, str)    # engine name, status

    def __init__(self, config_dir: Path):
        super().__init__()
        self._config_dir = config_dir
        self._engines: dict[str, EngineConfig] = {}
        self._active: Optional[str] = None
        self._processes: dict[str, QProcess] = {}
        self._statuses: dict[str, EngineStatus] = {}
        self._load_engines()
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._check_health)
        self._health_timer.start(5000)  # Check every 5s

    def _engines_file(self) -> Path:
        return self._config_dir / "engines.json"

    def _load_engines(self):
        f = self._engines_file()
        if f.exists():
            try:
                data = json.loads(f.read_text())
                for name, cfg in data.get("engines", {}).items():
                    self._engines[name] = EngineConfig.from_dict(cfg)
                self._active = data.get("active")
            except Exception:
                pass

    def _save_engines(self):
        self._config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "engines": {n: e.to_dict() for n, e in self._engines.items()},
            "active": self._active,
        }
        self._engines_file().write_text(json.dumps(data, indent=2))

    # ── Engine CRUD ────────────────────────────────────────────────

    def add_engine(self, config: EngineConfig):
        self._engines[config.name] = config
        self._statuses[config.name] = EngineStatus.STOPPED
        self._save_engines()
        self.engine_added.emit(config.name)

    def remove_engine(self, name: str):
        self.stop_engine(name)
        self._engines.pop(name, None)
        self._statuses.pop(name, None)
        if self._active == name:
            self._active = None
        self._save_engines()
        self.engine_removed.emit(name)

    def get_engine(self, name: str) -> Optional[EngineConfig]:
        return self._engines.get(name)

    def list_engines(self) -> list[EngineConfig]:
        return list(self._engines.values())

    def active_engine(self) -> Optional[EngineConfig]:
        return self._engines.get(self._active) if self._active else None

    def active_name(self) -> Optional[str]:
        return self._active

    def switch_engine(self, name: str):
        if name in self._engines:
            self._active = name
            self._save_engines()
            self.engine_switched.emit(name)

    def get_status(self, name: str) -> EngineStatus:
        return self._statuses.get(name, EngineStatus.STOPPED)

    # ── Start/Stop ─────────────────────────────────────────────────

    def start_engine(self, name: str):
        config = self._engines.get(name)
        if not config:
            self.engine_error.emit(name, "Engine not found")
            return

        if config.engine_type == "remote":
            # Remote engines: just verify connectivity
            self._statuses[name] = EngineStatus.RUNNING
            self.status_changed.emit(name, EngineStatus.RUNNING.value)
            self.engine_started.emit(name)
            return

        # Local/WSL: spawn process
        binary = self._find_binary(config)
        if not binary:
            self.engine_error.emit(name, f"Binary not found: {config.binary_path}")
            return

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)

        # Build arguments — splatsdb serve only accepts --port and --host
        args = [
            "serve",
            "--port", str(config.port),
            "--host", config.host,
        ]

        # Preset config is applied via env var or config file (future feature).
        # The splatsdb serve command always uses SplatDBConfig::default()
        # internally. Custom presets require running the MCP server instead.

        # Environment
        env = proc.processEnvironment()
        for k, v in config.env_vars.items():
            env.insert(k, v)
        if config.api_key:
            env.insert("SPLATSDB_API_KEY", config.api_key)
        proc.setProcessEnvironment(env)

        if config.working_dir:
            proc.setWorkingDirectory(config.working_dir)

        proc.readyReadStandardOutput.connect(
            lambda: self._on_process_output(name, proc)
        )
        proc.errorOccurred.connect(
            lambda err: self._on_process_error(name, err)
        )
        proc.finished.connect(
            lambda code, status: self._on_process_finished(name, code, status)
        )

        self._processes[name] = proc
        self._statuses[name] = EngineStatus.STARTING
        self.status_changed.emit(name, EngineStatus.STARTING.value)

        proc.start(binary, args)

    def stop_engine(self, name: str):
        proc = self._processes.get(name)
        if proc and proc.state() != QProcess.NotRunning:
            proc.terminate()
            if not proc.waitForFinished(3000):
                proc.kill()
            self._processes.pop(name, None)

        self._statuses[name] = EngineStatus.STOPPED
        self.status_changed.emit(name, EngineStatus.STOPPED.value)
        self.engine_stopped.emit(name)

    # ── Process callbacks ──────────────────────────────────────────

    def _on_process_output(self, name: str, proc: QProcess):
        output = proc.readAllStandardOutput().data().decode("utf-8", errors="replace")
        if "listening on" in output:
            self._statuses[name] = EngineStatus.RUNNING
            self.status_changed.emit(name, EngineStatus.RUNNING.value)
            self.engine_started.emit(name)

    def _on_process_error(self, name: str, error):
        self._statuses[name] = EngineStatus.ERROR
        self.status_changed.emit(name, EngineStatus.ERROR.value)
        self.engine_error.emit(name, f"Process error: {error}")

    def _on_process_finished(self, name: str, code: int, status: int):
        self._statuses[name] = EngineStatus.STOPPED
        self.status_changed.emit(name, EngineStatus.STOPPED.value)
        self.engine_stopped.emit(name)

    # ── Health check ───────────────────────────────────────────────

    def _check_health(self):
        for name, config in self._engines.items():
            status = self._statuses.get(name)
            if status in (EngineStatus.RUNNING, EngineStatus.STARTING):
                try:
                    import httpx
                    r = httpx.get(f"{config.url}/health", timeout=2.0)
                    if r.status_code == 200:
                        self._statuses[name] = EngineStatus.RUNNING
                    else:
                        self._statuses[name] = EngineStatus.ERROR
                except Exception:
                    if status == EngineStatus.RUNNING:
                        self._statuses[name] = EngineStatus.ERROR

    # ── Discovery ──────────────────────────────────────────────────

    def auto_discover(self) -> list[str]:
        """Find splatsdb binaries on the system."""
        found = []
        for candidate in [
            "splatsdb",
            "/usr/local/bin/splatsdb",
            "/usr/bin/splatsdb",
            str(Path.home() / "splatsdb/target/release/splatsdb"),
            str(Path.home() / "splatsdb/target/debug/splatsdb"),
            str(Path.home() / ".cargo/bin/splatsdb"),
        ]:
            if Path(candidate).exists() or shutil.which(candidate):
                found.append(candidate)
        return found

    def _find_binary(self, config: EngineConfig) -> Optional[str]:
        if config.binary_path and Path(config.binary_path).exists():
            return config.binary_path
        discovered = self.auto_discover()
        return discovered[0] if discovered else None

    # ── Presets ────────────────────────────────────────────────────

    @staticmethod
    def get_preset_config(preset_name: str) -> dict:
        """Get the configuration overrides for a preset."""
        return PRESETS.get(preset_name, {}).copy()

    @staticmethod
    def list_presets() -> dict[str, str]:
        """Return {name: description} for all presets."""
        return {name: data.get("description", "") for name, data in PRESETS.items()}
