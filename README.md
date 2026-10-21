# Video Library

AI-powered local video library manager with face recognition and auto-categorization.

## Features

- **Video Scanning** - Recursively scan directories, extract metadata (duration, resolution, codec)
- **Frame Extraction** - Scene detection (PySceneDetect) + interval-based keyframe sampling
- **AI Analysis**
  - Face detection & clustering (InsightFace ArcFace, 512-dim embedding)
  - Content tagging (OpenCLIP ViT-B/32 zero-shot classification)
  - Optional: Ollama vision model for enhanced labeling
- **Face Management** - Auto-match known characters, custom naming, merge duplicates
- **One-Click Classification** - Auto-create folders by tags, organize videos via hardlink/copy/move
- **Dual Themes** - Catppuccin Mocha (dark) + Latte (light), auto-follow system preference
- **GUI** - PyQt6 thumbnail grid + detail panel + tagging dialogs

## Installation

### Prerequisites

- Python 3.10+
- pip

### Setup

```bash
git clone https://github.com/StopCodeToTrain/video-library.git
cd video-library
pip install -r requirements.txt
```

First launch will auto-initialize the SQLite database and `thumbnails/` directory.

## Usage

### GUI

```bash
python main.py
# or
python gui.py
```

### CLI

```bash
# Scan video directory
python main.py --scan /path/to/videos

# Scan and analyze
python main.py --scan /path/to/videos --analyze
```

### Workflow

1. **Scan** - Add video directories via `File > Scan Directory`
2. **Analyze** - Select videos, click "Analyze Selected" to extract frames, detect faces, generate tags
3. **Name Characters** - `Tools > Character Manager` to name detected faces
4. **Classify** - `Tools > One-Click Classify` to auto-organize videos into tag folders

## Project Structure

```
video_library/
├── main.py                  # Entry point (GUI + CLI)
├── gui.py                   # PyQt6 GUI (main window, dialogs, workers)
├── config.py                # JSON settings persistence + tag presets
├── pipeline.py              # Analysis orchestration pipeline
├── theme.py                 # Catppuccin light/dark QSS themes
├── requirements.txt
├── analysis/
│   ├── face_detector.py     # InsightFace face detection + embedding
│   ├── face_cluster.py      # DBSCAN clustering → character identities
│   ├── face_matcher.py      # Auto-match faces to named characters
│   ├── content_tagger.py    # OpenCLIP zero-shot image classification
│   └── llm_client.py        # Optional Ollama vision model client
├── video_io/
│   ├── scanner.py           # Recursive directory scanning + metadata
│   ├── frame_extractor.py   # Scene detection + keyframe sampling
│   ├── thumbnail.py         # Video thumbnail extraction
│   └── classifier.py        # Tag-based auto-classification
├── storage/
│   ├── database.py          # SQLite CRUD (7 tables)
│   └── models.py            # Dataclass definitions
└── utils/
    └── thumbnail_cache.py   # Thumbnail cache cleanup
```

## Dependencies

| Package | Purpose |
|---------|---------|
| PyQt6 | GUI framework |
| opencv-python-headless | Video I/O + image processing |
| scenedetect | Scene boundary detection |
| insightface | Face detection + ArcFace embedding |
| onnxruntime | ONNX model inference runtime |
| open-clip-torch | CLIP-based image classification |
| torch + torchvision | Deep learning backend |
| transformers | HuggingFace model hub |
| Pillow | Image processing |
| numpy | Numerical computation |

## License

[MIT License](LICENSE) — Copyright (c) 2026 StopCodeToTrain and contributors.
