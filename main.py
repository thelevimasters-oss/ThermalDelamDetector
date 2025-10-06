"""Application entry point for launching the GUI."""
from __future__ import annotations

from thermal_delam_detector.app import launch


def main() -> None:
    launch()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
