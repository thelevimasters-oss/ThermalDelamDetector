"""Utility helpers for filesystem and metadata operations."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image

from .processing import SUPPORTED_EXTENSIONS


def discover_images(folder: Path) -> Iterable[Path]:
    """Yield supported images inside ``folder`` (non-recursive)."""

    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def ensure_output_folder(input_folder: Path, output_folder: Path | None = None) -> Path:
    """Return a usable output directory, creating it if needed."""

    if output_folder is None:
        output_folder = input_folder / "processed"
    output_folder.mkdir(parents=True, exist_ok=True)
    return output_folder


def save_with_metadata(image: Image.Image, destination: Path, exif_bytes: bytes | None) -> None:
    """Save ``image`` to ``destination`` while attempting to preserve EXIF data."""

    if exif_bytes:
        image.save(destination, exif=exif_bytes)
    else:
        image.save(destination)
