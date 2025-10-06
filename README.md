# Thermal Delamination Detector

A Python-based desktop application for civil engineers to review thermal RJPG imagery and highlight potential bridge deck delaminations without relying on AI models. The repository ships as a plain Python script so you can launch the tool directly from source or integrate the processing pipeline into your own automation.

## Features

- Drag-and-drop (when supported) or manual folder selection for RJPG batches.
- Adjustable percentile thresholding and morphology parameters with live previews.
- Deterministic thermal processing pipeline that normalizes, thresholds, denoises, and highlights hotspots in red.
- Batch export that preserves EXIF metadata for downstream orthomosaic and GIS workflows.

## Requirements

- Python 3.10 or newer.
- Python packages: [`pillow`](https://pypi.org/project/Pillow/) and [`numpy`](https://pypi.org/project/numpy/).
- Optional: [`tkinterdnd2`](https://pypi.org/project/tkinterdnd2/) to enable drag-and-drop on Windows/Linux.

You can install the dependencies into a virtual environment with:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install pillow numpy tkinterdnd2
```

The `tkinterdnd2` package is optional; omit it if you do not need drag-and-drop support.

## Running the Python script

From the project root run either of the following entry points to launch the Tkinter GUI:

```bash
python main.py
# or
python -m thermal_delam_detector.app
```

Both commands call the same `launch()` function that builds the GUI and starts the mainloop. The `main.py` entry point will
automatically install required Python dependencies (``Pillow`` and ``numpy``) and will attempt to install the optional
``tkinterdnd2`` package for drag-and-drop support, making it a one-stop launch script. When the window opens:

1. Drop a folder of RJPG/JPEG/TIFF thermal images onto the window or choose it via the **Browse** button.
2. Adjust the percentile, minimum hotspot size, and morphology sliders until the preview looks right.
3. Click **Process images** to export annotated overlays to the selected output folder (defaults to `<input>/processed`).

### Running without a display

If you are on a headless environment where Tk cannot initialise (for example a remote server without an X/Wayland session),
the `main.py` entry point also exposes a batch-processing mode. Provide an input directory containing supported images and the
tool will save processed overlays to `<input>/processed` (or a custom output directory via `--output`):

```bash
python main.py --input /path/to/images --output /path/to/output
```

Additional optional flags mirror the GUI controls:

- `--hotspot-percentile` – adjust the percentile threshold (default `97`).
- `--min-cluster-size` – minimum hotspot size in pixels (default `45`).
- `--opening-iterations` / `--closing-iterations` – morphological cleanup iterations (default `1`).
- `--kernel-size` – kernel size for the morphology operations (default `3`).

When no display is detected and `--input` is omitted the script will exit with a helpful message instead of throwing a Tk
initialisation error. Pass `--force-gui` to override the display check when you know a display server is available.

## Automating the processing pipeline

The core logic for detecting delaminations lives in `thermal_delam_detector/processing.py`. If you prefer to script processing without the GUI, you can import the `ImageProcessor` class and call `process_folder()` from your own Python code:

```python
from pathlib import Path
from thermal_delam_detector.processing import ImageProcessor

processor = ImageProcessor()
results = processor.process_folder(Path("/path/to/images"), Path("/path/to/output"))
```

Each `ProcessingResult` includes the rendered overlay and metadata about hotspots, enabling further customization.

## Notes

- The application works entirely offline using rule-based processing.
- Output overlays keep original GPS/EXIF metadata when present, making them suitable for photogrammetry and GIS ingestion.
- Optional drag-and-drop is enabled automatically when the `tkinterdnd2` package is available.
