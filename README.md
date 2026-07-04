# SplatsDB UI

Professional desktop interface for [SplatsDB](https://github.com/schwabauerbriantomas-gif/m2m-vector-search) — Gaussian Splat vector search engine.

Built with PySide6 (Qt 6), dark theme, mixin architecture.

## Features

- **Multi-model embeddings**: Switch between models at runtime (bge-m3 1024D, llama-embed-nemotron-8b, all-MiniLM-L6-v2, BGE, GTE, custom ONNX)
- **OCR integration**: Extract text from images/PDFs → embed → search (Tesseract, PaddleOCR)
- **Vector search**: Semantic search with real-time results, distance visualization
- **Knowledge graph**: Visual graph traversal, entity management, relation mapping
- **Spatial memory**: Wing/Room/Hall navigation with filter panels
- **Cluster dashboard**: Node status, routing, shard management
- **Benchmarks**: GPU/CPU benchmarking with charts
- **Job queue**: Background operations with progress tracking
- **3D Explorer**: Interactive splat visualization with node inspector and file preview

## Quick Start

```bash
pip install splatsdb-ui

# With all extras (OCR + embeddings):
pip install "splatsdb-ui[all]"

# Launch:
splatsdb-ui
```

### Requirements

- SplatsDB backend running (`splatsdb serve` on port 8199, or MCP mode)
- Python 3.10+
- For CUDA embeddings: NVIDIA GPU + CUDA toolkit

## SplatsDB Backend Compatibility

This UI targets **SplatDB v2.6.0** (`m2m-vector-search`).

| Feature | UI | SplatDB v2.6.0 |
|---------|-----|-----------------|
| Latent dimension | 1024 (all presets) | 1024 (bge-m3 default) |
| HTTP endpoints | `/health`, `/status`, `/store`, `/search` | Same |
| Embedding model | bge-m3 (1024D, multilingual) | Same |

**Note:** The optimization/prefetch/cache endpoints (`/optimization`, `/prefetch`, `/cache/clear`)
are defined in the client but not yet implemented in the SplatDB HTTP server. The methods
return empty results gracefully.

## Architecture

```
splatsdb_ui/
├── main.py              # Entry point
├── app.py               # MainWindow (mixin composition)
├── engine_manager.py    # LM Studio-style backend switcher + presets
├── mixins/              # MainWindow behavior modules
│   ├── file_mixin.py        # File open, drag-drop
│   ├── search_mixin.py      # Search bar, results, shortcuts
│   ├── view_mixin.py        # View switching, panels
│   ├── edit_mixin.py        # Clipboard, selection
│   ├── settings_mixin.py    # Preferences, config persistence
│   ├── job_mixin.py         # Job queue, progress
│   └── audio_mixin.py       # UI sounds
├── views/               # Main content views
│   ├── welcome_view.py      # Welcome screen
│   ├── search_view.py       # Semantic search
│   ├── collections_view.py  # Collection browser
│   ├── graph_view.py        # Knowledge graph
│   ├── spatial_view.py      # Spatial memory navigator
│   ├── cluster_view.py      # Cluster dashboard
│   ├── benchmark_view.py    # Benchmark runner
│   ├── splat3d_view.py      # 3D splat explorer
│   ├── gaussian_splat_renderer.py  # 3D rendering engine
│   ├── ebm_view.py          # Energy-based model view
│   └── ocr_view.py          # OCR text extraction
├── widgets/             # Reusable UI components
│   ├── engine_switcher.py   # Backend selector (LM Studio style)
│   ├── config_editor.py     # Full config parameter editor
│   ├── result_card.py       # Search result card
│   ├── status_bar.py        # GPU/VRAM/metrics bar
│   ├── io_tray.py           # Input/output thumbnail tray
│   ├── param_panel.py       # Parameter sidebar
│   ├── job_queue.py         # Background job progress
│   ├── search_bar.py        # Global search input
│   ├── node_inspector.py    # Node detail inspector
│   └── file_preview.py      # File preview panel
├── workers/             # QThread workers
│   ├── embedding_worker.py  # Embedding generation
│   ├── search_worker.py     # Search queries
│   └── ocr_worker.py        # OCR text extraction
├── embeddings/          # Embedding engine
│   ├── engine.py            # Multi-model embedding engine
│   ├── registry.py          # Model registry + discovery
│   └── providers/           # Model providers
├── utils/               # Utilities
│   ├── api_client.py        # SplatsDB HTTP API client
│   ├── state.py             # Application state
│   ├── signals.py           # Global signal bus
│   ├── icons.py             # SVG icon system
│   └── theme.py             # Dark theme QSS
└── resources/
    └── icons/               # SVG icons
```

## Configuration

Config file: `~/.splatsdb-ui/config.yaml`

```yaml
backend:
  url: "http://127.0.0.1:8199"
  api_key: ""           # Optional Bearer token

embedding:
  default_model: "bge-m3"   # Matches SplatDB v2.6.0 default
  models_dir: "/mnt/d/models"
  device: "cuda"            # cuda | cpu | auto

ocr:
  engine: "auto"            # auto | tesseract | paddleocr
  language: "spa+eng"

ui:
  theme: "dark"
  sounds: true
  font_size: 13
```

## Presets

The engine manager supports these presets (all use `latent_dim: 1024` to match bge-m3):

| Preset | Use Case | Max Splats |
|--------|----------|------------|
| `default` | Balanced development | 100K |
| `simple` | Edge / minimal | 10K |
| `advanced` | Full features + HNSW | 1M |
| `training` | Embedding research | 500K |
| `distributed` | Multi-node cluster | 10M |
| `mcp` | AI agent memory | 100K |
| `gpu` | CUDA acceleration | 5M |
| `custom` | User-defined | — |

**Note:** The `splatsdb serve` command uses `SplatsDBConfig::default()` internally.
Presets are metadata for the UI config editor; they do not pass `--preset` to the CLI
(that flag does not exist). For preset-specific behavior, use the MCP server instead.

## License

GPL-3.0
