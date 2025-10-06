"""Application entry point for launching the GUI with automatic dependency setup."""
from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Mapping, Sequence


_REQUIRED_DEPENDENCIES: Mapping[str, str] = {
    "PIL": "Pillow",
    "numpy": "numpy",
}

_OPTIONAL_DEPENDENCIES: Mapping[str, str] = {
    "tkinterdnd2": "tkinterdnd2",
}


def _site_packages_directory() -> Path | None:
    """Return the directory where ``pip`` will install pure Python packages."""

    try:
        purelib = sysconfig.get_path("purelib")
    except (KeyError, OSError):  # pragma: no cover - extremely rare
        return None

    if not purelib:
        return None

    return Path(purelib)


def _is_writable(path: Path | None) -> bool:
    """Return ``True`` if ``path`` or one of its parents is writable."""

    if path is None:
        return False

    current = path
    while True:
        if current.exists():
            return os.access(current, os.W_OK)
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _installation_requires_admin() -> bool:
    """Determine whether installing packages likely requires admin rights."""

    return not _is_writable(_site_packages_directory())


def _confirm_admin_install(package_name: str, *, required: bool) -> bool:
    """Ask the user whether to continue when admin rights are needed."""

    message = (
        f"Installing required dependency '{package_name}' requires administrative "
        "privileges. Please re-run this program as an administrator or install the "
        "package manually."
    )

    if not sys.stdin.isatty():
        if required:
            raise SystemExit(message)
        print(message, file=sys.stderr)
        return False

    prompt = (
        f"Installing '{package_name}' may require administrative privileges.\n"
        "Do you want to continue? [y/N]: "
    )
    response = input(prompt).strip().lower()
    if response in {"y", "yes"}:
        return True

    if required:
        raise SystemExit(message)

    print(
        f"Skipping optional dependency '{package_name}' at user request.",
        file=sys.stderr,
    )
    return False


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

        if _installation_requires_admin() and not _confirm_admin_install(
            package_name, required=required
        ):
            return

        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.stdout:
            print(result.stdout, file=sys.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")

        if result.returncode != 0:
            error_message = (
                f"Failed to install {'required' if required else 'optional'} dependency "
                f"'{package_name}'."
            )
            lowered = (result.stderr or "").lower()
            if "permission" in lowered or "access is denied" in lowered:
                error_message += (
                    " Installation appears to require administrative privileges. "
                    "Please re-run this program with elevated permissions or "
                    "install the dependency manually."
                )

            if required:
                raise SystemExit(error_message)

            print(f"Warning: {error_message}", file=sys.stderr)
            return

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


def _display_status() -> tuple[bool, str | None]:
    """Return display availability together with an optional failure reason."""

    try:
        import tkinter as tk
    except ModuleNotFoundError:
        return False, (
            "Python was built without the Tkinter module. Install Python with the "
            "optional Tcl/Tk components (the \"Tcl/tk and IDLE\" feature in the official "
            "installer) or use a distribution that bundles Tk."
        )
    except ImportError as exc:
        return False, (
            "Tkinter could not be imported. The underlying error was: "
            f"{exc}. Reinstall or repair Python so that the Tcl/Tk libraries are available."
        )

    if sys.platform.startswith("win"):
        # When Tkinter imports successfully on Windows we normally assume a display
        # is available. However, some minimal Python builds ship the ``tkinter``
        # package without the native Tcl/Tk DLLs. Importing succeeds but creating a
        # root window raises ``TclError`` immediately. Probing for a root window lets
        # us surface that specific failure mode with a clearer message.
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            return False, (
                "Tk reported an initialisation error: "
                f"{exc}. This usually means Tcl/Tk was not installed. "
                "Re-run the official Python installer and ensure the "
                '"tcl/tk and IDLE" feature is selected.'
            )
        else:
            root.withdraw()
            root.destroy()
            return True, None

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        return False, (
            "Tk could not connect to a display server. Ensure an X11/Wayland "
            "session is running and that the DISPLAY environment variable is "
            f"set correctly. Underlying error: {exc}"
        )
    else:
        root.withdraw()
        root.destroy()
        return True, None


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

    display_available, display_error = _display_status()
    if not args.force_gui and not display_available:
        message = [
            "The graphical interface could not be started because Tk was unable to initialise.",
        ]
        if display_error:
            message.append(display_error)
        message.append(
            "If you are running the tool on a headless machine, launch the batch processor "
            "instead with 'python main.py --input <folder-with-images>' (optionally add "
            "'--output' to choose the destination)."
        )
        raise SystemExit("\n".join(message))

    from thermal_delam_detector.app import launch

    launch(force_gui=args.force_gui)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
