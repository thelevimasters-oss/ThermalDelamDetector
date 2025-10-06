"""Application entry point for launching the GUI with automatic dependency setup."""
from __future__ import annotations

import importlib
import subprocess
import sys
from typing import Mapping


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


def main() -> None:
    ensure_dependencies()
    from thermal_delam_detector.app import launch

    launch()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
