<div align="center">

# SplatsDB UI

**Professional desktop interface for [SplatsDB](https://github.com/schwabauerbriantomas-gif/m2m-vector-search) — Gaussian Splat vector search engine**

[![CI](https://github.com/schwabauerbriantomas-gif/splatsdb-ui/actions/workflows/ci.yml/badge.svg)](https://github.com/schwabauerbriantomas-gif/splatsdb-ui/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PySide6](https://img.shields.io/badge/PySide6-6.6+-green.svg)](https://doc.qt.io/qtforpython-6/)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![SplatDB v2.6.0](https://img.shields.io/badge/SplatDB-v2.6.0-orange.svg)](https://github.com/schwabauerbriantomas-gif/m2m-vector-search)

</div>

## Overview

SplatsDB UI is a professional desktop application for managing and visualizing vector search operations using the SplatsDB Gaussian Splat engine. Built with PySide6 (Qt 6) and a dark, Linear-inspired theme.

## Features

- **Multi-model embeddings** — Runtime switching between bge-m3 (1024D default), LLaMA-Embed Nemotron 8B, MiniLM, BGE, GTE, and custom ONNX models
- **Semantic search** — Real-time vector search with result cards, distance visualization, and batch operations
- **Knowledge graph** — Interactive force-directed graph traversal with entity management and relation mapping
- **Spatial memory** — Wing/Room/Hall navigation with Voronoi partitioning and MST backbone visualization
- **3D Gaussian splat explorer** — Interactive 3D rendering with node inspector and file preview
- **EBM energy landscape** — Energy-based model visualization with avalanche dynamics
- **Cluster dashboard** — Node status, routing tables, and shard management
- **OCR pipeline** — Extract text from images/PDFs using Tesseract or PaddleOCR, embed, and store
- **Benchmarks** — GPU/CPU benchmarking with comparison tables (search, HNSW, ingestion)
- **Engine switcher** — LM Studio-style backend selector with preset configs and auto-discovery

## Quick Start

```bash
# Install
pip install splatsdb-ui

# With all extras (OCR + embeddings)
pip install "splatsdb-ui[all]"

# Launch
splatsdb-ui
```

### Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| SplatsDB backend | v2.6.0 (`splatsdb serve` on port 8199) |
| PySide6 | 6.6+ |
| NVIDIA GPU | Optional, for CUDA embeddings |

## SplatsDB Backend Compatibility

This UI targets **SplatDB v2.6.0** with bge-m3 embeddings (1024 dimensions).

| Feature | UI | SplatDB v2.6.0 |
|---------|-----|-----------------|
| Latent dimension | 1024 (all presets) | 1024 (bge-m3 default) |
| HTTP API | `/health`, `/status`, `/store`, `/search` | Same |
| Embedding model | bge-m3 (1024D, multilingual) | Same |
| MCP server | Future | 17 tools via `splatsdb mcp` |

## Architecture

```
splatsdb_ui/
├── main.py                  # Entry point
├── app.py                   # MainWindow (mixin composition)
├── engine_manager.py        # LM Studio-style backend switcher + presets
├── mixins/                  # MainWindow behavior modules
│   ├── search_mixin.py          # Search bar → QThread → backend → results
│   ├── file_mixin.py            # File open, drag-drop
│   ├── settings_mixin.py        # Config persistence
│   ├── audio_mixin.py           # UI sound feedback
│   ├── view_mixin.py            # View switching
│   └── edit_mixin.py            # Clipboard, selection
├── views/                   # Main content views
│   ├── search_view.py           # Semantic search with result cards
│   ├── graph_view.py            # Force-directed knowledge graph
│   ├── spatial_view.py          # Voronoi/Delaunay spatial memory
│   ├── splat3d_view.py          # 3D Gaussian splat explorer
│   ├── ebm_view.py              # Energy-based model landscape
│   ├── cluster_view.py          # Cluster dashboard
│   ├── ocr_view.py              # OCR text extraction pipeline
│   ├── benchmark_view.py        # Benchmark runner
│   └── collections_view.py      # Collection browser
├── widgets/                 # Reusable UI components
│   ├── engine_switcher.py       # Backend selector (play/stop)
│   ├── config_editor.py         # Full SplatsDB config (60+ params)
│   ├── param_panel.py           # Dynamic parameter sidebar
│   ├── node_inspector.py        # Node detail + connections table
│   ├── file_preview.py          # PDF/image preview
│   ├── result_card.py           # Search result card
│   ├── job_queue.py             # Background job progress
│   └── io_tray.py               # Input/output thumbnail tray
├── workers/                 # QThread background workers
│   ├── search_worker.py         # HTTP search queries
│   ├── embedding_worker.py      # Multi-model embeddings
│   └── ocr_worker.py            # OCR text extraction (Tesseract/PaddleOCR)
├── embeddings/              # Embedding engine
│   ├── engine.py                # Multi-model provider system
│   ├── registry.py              # Model registry (bge-m3, Nemotron, MiniLM)
│   └── providers/               # Provider implementations
├── dialogs/                 # Modal dialogs
│   └── about_dialog.py          # About dialog with project info
└── utils/                   # Utilities
    ├── api_client.py            # SplatsDB HTTP API client
    ├── state.py                 # Application state containers
    ├── signals.py               # Global signal bus
    ├── icons.py                 # SVG icon system
    └── theme.py                 # Dark theme (JetBrains/Linear inspired)
```

## Configuration

Config file: `~/.splatsdb-ui/config.json`

```json
{
  "backend": {
    "url": "http://127.0.0.1:8199",
    "api_key": ""
  },
  "embedding": {
    "active_model": "bge-m3",
    "device": "cuda"
  },
  "ocr": {
    "engine": "auto",
    "language": "spa+eng"
  },
  "ui": {
    "theme": "dark",
    "sounds_enabled": true,
    "font_size": 13
  }
}
```

## Presets

All presets use `latent_dim: 1024` to match bge-m3 / SplatDB v2.6.0.

| Preset | Use Case | Max Splats | Device |
|--------|----------|------------|--------|
| `default` | Balanced development | 100K | CPU |
| `simple` | Edge / minimal | 10K | CPU |
| `advanced` | Full features + HNSW | 1M | CPU |
| `training` | Embedding research | 500K | CPU |
| `distributed` | Multi-node cluster | 10M | CPU |
| `mcp` | AI agent memory | 100K | Auto |
| `gpu` | CUDA acceleration | 5M | CUDA |
| `custom` | User-defined | — | — |

## License

GPL-3.0
