"""Simple thermal delamination detector.

This module provides a command-line interface for flagging temperature
measurements that deviate above a rolling baseline by a specified amount.
"""
from __future__ import annotations

import argparse
import csv
from collections import deque
from pathlib import Path
from statistics import mean
from typing import Deque, Iterable, List, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flag potential delamination hotspots in thermal data.")
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to the CSV file containing thermal measurements.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Temperature delta above the rolling baseline considered anomalous.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=10,
        help="Size of the rolling window used to compute the baseline.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for the output CSV. Defaults to '<input>_delam_candidates.csv'.",
    )
    return parser.parse_args()


def read_measurements(path: Path) -> List[Tuple[str, float]]:
    measurements: List[Tuple[str, float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "temperature" not in reader.fieldnames:
            raise ValueError("Input CSV must contain a 'temperature' column.")
        for row in reader:
            try:
                temp = float(row["temperature"])
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive programming
                raise ValueError(f"Invalid temperature value: {row['temperature']}") from exc
            # Use the first column as an identifier if available, else the row index.
            identifier = next((row[key] for key in reader.fieldnames if key != "temperature"), str(len(measurements)))
            measurements.append((identifier, temp))
    if not measurements:
        raise ValueError("No measurement rows found in the input CSV.")
    return measurements


def detect_delamination(
    measurements: Iterable[Tuple[str, float]],
    window: int,
    threshold: float,
) -> List[Tuple[str, float, float]]:
    if window <= 0:
        raise ValueError("Window size must be greater than zero.")
    if threshold <= 0:
        raise ValueError("Threshold must be greater than zero.")

    buffer: Deque[float] = deque(maxlen=window)
    results: List[Tuple[str, float, float]] = []
    for identifier, temperature in measurements:
        if len(buffer) == buffer.maxlen:
            baseline = mean(buffer)
            delta = temperature - baseline
            if delta >= threshold:
                results.append((identifier, temperature, delta))
        buffer.append(temperature)
    return results


def write_results(output_path: Path, results: Iterable[Tuple[str, float, float]]) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["identifier", "temperature", "delta"])
        writer.writerows(results)


def main() -> None:
    args = parse_args()
    measurements = read_measurements(args.input)
    detections = detect_delamination(measurements, args.window, args.threshold)

    if args.output is None:
        output_path = args.input.with_suffix("")
        output_path = output_path.parent / f"{output_path.name}_delam_candidates.csv"
    else:
        output_path = args.output

    if detections:
        write_results(output_path, detections)
        print(f"Flagged {len(detections)} readings. Results saved to {output_path}.")
    else:
        print("No readings exceeded the specified threshold.")


if __name__ == "__main__":
    main()
