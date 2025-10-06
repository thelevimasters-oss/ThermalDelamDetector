"""Core thermal image processing utilities."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from PIL import Image


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".rjpg", ".tif", ".tiff"}


@dataclass(slots=True)
class ProcessingConfig:
    """Configuration parameters that control the thermal pipeline."""

    hotspot_percentile: float = 97.0
    min_cluster_size: int = 45
    opening_iterations: int = 1
    closing_iterations: int = 1
    kernel_size: int = 3

    def clamp(self) -> "ProcessingConfig":
        """Clamp values to practical ranges and return ``self`` for chaining."""

        self.hotspot_percentile = float(np.clip(self.hotspot_percentile, 50.0, 100.0))
        self.min_cluster_size = int(np.clip(self.min_cluster_size, 1, 10000))
        self.opening_iterations = int(np.clip(self.opening_iterations, 0, 5))
        self.closing_iterations = int(np.clip(self.closing_iterations, 0, 5))
        self.kernel_size = int(np.clip(self.kernel_size, 3, 9) // 2 * 2 + 1)
        return self


@dataclass(slots=True)
class ProcessingResult:
    """A processed thermal image."""

    source_path: Path
    overlay_image: Image.Image
    mask: np.ndarray
    temperature_map: np.ndarray
    exif_bytes: Optional[bytes]


class ImageProcessor:
    """Process thermal imagery using a deterministic pipeline."""

    def __init__(self, config: Optional[ProcessingConfig] = None) -> None:
        self.config = (config or ProcessingConfig()).clamp()
        self._palette = _build_palette()

    def update_config(self, **kwargs: float) -> None:
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self.config.clamp()

    # Public API ---------------------------------------------------------
    def process_image(self, image_path: Path) -> ProcessingResult:
        """Process a single image and return the overlay result."""

        if image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file extension: {image_path.suffix}")

        image = Image.open(image_path)
        exif_bytes = image.info.get("exif")

        temperature_map = _extract_temperature_map(image)
        normalized = _normalize_temperature(temperature_map)
        threshold = np.percentile(normalized, self.config.hotspot_percentile)
        hotspot_mask = normalized >= threshold

        if self.config.opening_iterations:
            hotspot_mask = _binary_opening(
                hotspot_mask,
                iterations=self.config.opening_iterations,
                kernel_size=self.config.kernel_size,
            )
        if self.config.closing_iterations:
            hotspot_mask = _binary_closing(
                hotspot_mask,
                iterations=self.config.closing_iterations,
                kernel_size=self.config.kernel_size,
            )

        hotspot_mask = _remove_small_objects(hotspot_mask, self.config.min_cluster_size)

        overlay = _create_overlay_image(normalized, hotspot_mask, self._palette)
        overlay_pil = Image.fromarray(overlay, mode="RGB")

        return ProcessingResult(
            source_path=image_path,
            overlay_image=overlay_pil,
            mask=hotspot_mask,
            temperature_map=normalized,
            exif_bytes=exif_bytes,
        )

    def process_folder(self, folder: Path) -> Iterable[ProcessingResult]:
        for image_path in sorted(folder.iterdir()):
            if image_path.is_file() and image_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                yield self.process_image(image_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_temperature_map(image: Image.Image) -> np.ndarray:
    """Extract a grayscale temperature surrogate from the incoming image."""

    if image.mode not in ("L", "I;16", "F"):
        grayscale = image.convert("L")
    else:
        grayscale = image
    data = np.asarray(grayscale, dtype=np.float32)

    if data.ndim != 2:
        raise ValueError("Expected a 2D grayscale temperature map")

    return data


def _normalize_temperature(data: np.ndarray) -> np.ndarray:
    minimum = float(np.nanmin(data))
    maximum = float(np.nanmax(data))
    if not np.isfinite(minimum) or not np.isfinite(maximum):
        raise ValueError("Temperature data contains no finite values")
    span = max(maximum - minimum, 1e-6)
    normalized = (data - minimum) / span
    return np.clip(normalized, 0.0, 1.0)


def _build_palette(steps: int = 256) -> np.ndarray:
    """Build a blue-to-red palette for visualization."""

    anchors = [
        (0.0, np.array([0, 0, 64], dtype=np.float32)),
        (0.25, np.array([0, 128, 255], dtype=np.float32)),
        (0.5, np.array([0, 255, 255], dtype=np.float32)),
        (0.75, np.array([255, 255, 0], dtype=np.float32)),
        (1.0, np.array([255, 0, 0], dtype=np.float32)),
    ]

    palette = np.zeros((steps, 3), dtype=np.uint8)
    for i in range(steps):
        t = i / (steps - 1)
        for (t0, c0), (t1, c1) in zip(anchors[:-1], anchors[1:]):
            if t0 <= t <= t1:
                local_t = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                color = c0 * (1 - local_t) + c1 * local_t
                palette[i] = color.round().astype(np.uint8)
                break
    return palette


def _create_overlay_image(normalized: np.ndarray, mask: np.ndarray, palette: np.ndarray) -> np.ndarray:
    grayscale = (normalized * 255).round().astype(np.uint8)
    colored = palette[grayscale]

    overlay = colored.copy()
    red = np.array([255, 0, 0], dtype=np.uint8)
    highlight = mask
    overlay[highlight] = (
        0.4 * overlay[highlight].astype(np.float32) + 0.6 * red
    ).round().astype(np.uint8)

    return overlay


def _binary_opening(mask: np.ndarray, iterations: int, kernel_size: int) -> np.ndarray:
    result = mask.copy()
    for _ in range(iterations):
        result = _binary_erode(result, kernel_size)
    for _ in range(iterations):
        result = _binary_dilate(result, kernel_size)
    return result


def _binary_closing(mask: np.ndarray, iterations: int, kernel_size: int) -> np.ndarray:
    result = mask.copy()
    for _ in range(iterations):
        result = _binary_dilate(result, kernel_size)
    for _ in range(iterations):
        result = _binary_erode(result, kernel_size)
    return result


def _binary_dilate(mask: np.ndarray, kernel_size: int) -> np.ndarray:
    kernel = np.ones((kernel_size, kernel_size), dtype=bool)
    pad = kernel_size // 2
    padded = np.pad(mask, pad, mode="constant", constant_values=False)
    result = np.zeros_like(mask, dtype=bool)
    for y in range(kernel_size):
        for x in range(kernel_size):
            if kernel[y, x]:
                result |= padded[y : y + mask.shape[0], x : x + mask.shape[1]]
    return result


def _binary_erode(mask: np.ndarray, kernel_size: int) -> np.ndarray:
    kernel = np.ones((kernel_size, kernel_size), dtype=bool)
    pad = kernel_size // 2
    # Use ``False`` for the padded border so erosion behaves like standard
    # morphological erosion where pixels outside the image are treated as
    # background. Using ``True`` incorrectly preserved edge pixels and meant
    # erosion/ opening operations were ineffective at the borders.
    padded = np.pad(mask, pad, mode="constant", constant_values=False)
    result = np.ones_like(mask, dtype=bool)
    for y in range(kernel_size):
        for x in range(kernel_size):
            if kernel[y, x]:
                result &= padded[y : y + mask.shape[0], x : x + mask.shape[1]]
    return result


def _remove_small_objects(mask: np.ndarray, min_size: int) -> np.ndarray:
    if min_size <= 1:
        return mask

    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    result = mask.copy()
    neighbors = [
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    ]

    for row in range(height):
        for col in range(width):
            if not mask[row, col] or visited[row, col]:
                continue

            stack = [(row, col)]
            component = []
            visited[row, col] = True

            while stack:
                r, c = stack.pop()
                component.append((r, c))
                for dr, dc in neighbors:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < height and 0 <= nc < width:
                        if mask[nr, nc] and not visited[nr, nc]:
                            visited[nr, nc] = True
                            stack.append((nr, nc))

            if len(component) < min_size:
                for r, c in component:
                    result[r, c] = False

    return result
