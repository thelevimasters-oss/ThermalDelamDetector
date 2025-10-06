"""Application entry point for launching the GUI with automatic dependency setup."""
from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence


_REQUIRED_DEPENDENCIES: Mapping[str, str] = {
    "PIL": "Pillow",
    "numpy": "numpy",
}

_OPTIONAL_DEPENDENCIES: Mapping[str, str] = {
    "tkinterdnd2": "tkinterdnd2",
}


def _ensure_module(module_name: str, package_name: str, *, required: bool) -> None:
    """Ensure ``module_name`` can be imported, installing ``package_name`` if needed."""

    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError:
        message = (
            f"Installing required dependency: {package_name}"
            if required
            else f"Installing optional dependency: {package_name}"
        )
        print(message, file=sys.stderr)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        except subprocess.CalledProcessError as exc:
            if required:
                raise SystemExit(
                    f"Failed to install required dependency '{package_name}'."
                ) from exc
            print(
                f"Warning: optional dependency '{package_name}' could not be installed.",
                file=sys.stderr,
            )
        else:
            importlib.invalidate_caches()
            importlib.import_module(module_name)


def ensure_dependencies() -> None:
    """Install missing dependencies so the application is ready to launch."""

    for module_name, package_name in _REQUIRED_DEPENDENCIES.items():
        _ensure_module(module_name, package_name, required=True)

    for module_name, package_name in _OPTIONAL_DEPENDENCIES.items():
        _ensure_module(module_name, package_name, required=False)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Thermal Delamination Detector GUI and command-line entry point.",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        help="Folder containing RJPG/JPEG/TIFF images to process in headless mode.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Destination folder for processed overlays (defaults to '<input>/processed').",
    )
    parser.add_argument(
        "--hotspot-percentile",
        type=float,
        help="Percentile used to detect hotspots (default 97).",
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        help="Minimum hotspot size in pixels (default 45).",
    )
    parser.add_argument(
        "--opening-iterations",
        type=int,
        help="Number of morphological opening iterations (default 1).",
    )
    parser.add_argument(
        "--closing-iterations",
        type=int,
        help="Number of morphological closing iterations (default 1).",
    )
    parser.add_argument(
        "--kernel-size",
        type=int,
        help="Kernel size for morphological operations (odd integer, default 3).",
    )
    parser.add_argument(
        "--force-gui",
        action="store_true",
        help="Attempt to launch the GUI even if no display is detected.",
    )
    return parser.parse_args(argv)


def _display_available() -> bool:
    if sys.platform.startswith("win"):
        return True
    if sys.platform == "darwin":
        return bool(os.environ.get("DISPLAY"))
    return bool(
        os.environ.get("DISPLAY")
        or os.environ.get("WAYLAND_DISPLAY")
        or os.environ.get("MIR_SOCKET")
    )


def _run_cli(args: argparse.Namespace) -> None:
    from thermal_delam_detector.io_utils import (
        discover_images,
        ensure_output_folder,
        save_with_metadata,
    )
    from thermal_delam_detector.processing import ImageProcessor

    if args.input is None:
        raise SystemExit("Input folder must be provided when running headlessly.")

    input_folder = args.input.expanduser().resolve()
    if not input_folder.exists() or not input_folder.is_dir():
        raise SystemExit(f"Input folder does not exist or is not a directory: {input_folder}")

    output_folder = ensure_output_folder(
        input_folder,
        args.output.expanduser().resolve() if args.output else None,
    )

    processor = ImageProcessor()
    config_updates = {}
    if args.hotspot_percentile is not None:
        config_updates["hotspot_percentile"] = args.hotspot_percentile
    if args.min_cluster_size is not None:
        config_updates["min_cluster_size"] = args.min_cluster_size
    if args.opening_iterations is not None:
        config_updates["opening_iterations"] = args.opening_iterations
    if args.closing_iterations is not None:
        config_updates["closing_iterations"] = args.closing_iterations
    if args.kernel_size is not None:
        config_updates["kernel_size"] = args.kernel_size
    if config_updates:
        processor.update_config(**config_updates)

    images = list(discover_images(input_folder))
    if not images:
        raise SystemExit(
            f"No supported images were found in: {input_folder}. Supported extensions: .rjpg, .jpg, .jpeg, .tif, .tiff"
        )

    processed = 0
    for image_path in images:
        result = processor.process_image(image_path)
        destination = output_folder / f"{image_path.stem}_processed.jpg"
        save_with_metadata(result.overlay_image, destination, result.exif_bytes)
        processed += 1
        print(f"Processed {image_path.name} -> {destination}")

    print(
        f"Finished processing {processed} image(s). Annotated overlays saved to: {output_folder}"
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    ensure_dependencies()

    if args.input is not None:
        _run_cli(args)
        return

    if not args.force_gui and not _display_available():
        raise SystemExit(
            "No display detected. Provide --input to process images in headless mode "
            "or re-run with --force-gui after configuring a display server."
        )

    from thermal_delam_detector.app import launch

    launch()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
