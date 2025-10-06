# Thermal Delamination Detector

A desktop application for civil engineers to review thermal RJPG imagery and highlight potential bridge deck delaminations without relying on AI models.

## Features

- Drag-and-drop (when supported) or manual folder selection for RJPG batches.
- Adjustable percentile thresholding and morphology parameters with live previews.
- Deterministic thermal processing pipeline that normalizes, thresholds, denoises, and highlights hotspots in red.
- Batch export that preserves EXIF metadata for downstream orthomosaic and GIS workflows.

## Getting started

1. Ensure Python 3.10+ is installed along with the `pillow` and `numpy` packages.
2. From the project root run:

   ```bash
   python main.py
   ```

3. Drop a folder of RJPG/JPEG/TIFF thermal images onto the window or choose it via the "Browse" button.
4. Adjust the percentile, minimum hotspot size, and morphology sliders until the preview looks right.
5. Click **Process images** to export annotated overlays to the selected output folder (defaults to `<input>/processed`).

## Notes

- The application works entirely offline using rule-based processing.
- Output overlays keep original GPS/EXIF metadata when present, making them suitable for photogrammetry and GIS ingestion.
- Optional drag-and-drop is enabled automatically when the `tkinterdnd2` package is available.
