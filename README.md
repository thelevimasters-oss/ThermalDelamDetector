# Thermal Delamination Detector

This repository contains a lightweight Python script for flagging potential delamination in thermal imagery. The tool ingests a comma-separated values (CSV) file of temperature readings and applies simple heuristics to help identify suspicious regions for further inspection.

## Project structure

```
.
├── README.md                # Project documentation
└── thermal_delam_detector.py # Core detection script
```

## Prerequisites

* Python 3.9 or later
* Optional: a virtual environment tool such as `venv` or `conda`

## Getting started

1. **Clone the repository**
   ```bash
   git clone https://github.com/<your-user>/ThermalDelamDetector.git
   cd ThermalDelamDetector
   ```
2. **(Optional) Create and activate a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```
3. **Install dependencies**
   The script uses only the Python standard library, so no additional packages are required.

## Usage

Supply the path to your thermal dataset when invoking the script:

```bash
python thermal_delam_detector.py --input data/thermal_readings.csv --threshold 5.0
```

### Arguments

* `--input`: Path to a CSV file containing at least two columns: `x`/`y` coordinates (or timestamps) and a `temperature` value.
* `--threshold`: Temperature delta (in °C) above the rolling baseline that should be flagged as a potential delamination hotspot. Defaults to `3.0`.
* `--window`: Size of the rolling window (number of samples) used to compute the baseline. Defaults to `10`.

### Output

The script prints a summary of flagged rows to the console and writes them to `delam_candidates.csv` in the same directory as the input file.

## Example

```bash
python thermal_delam_detector.py --input example-data/sample_panel.csv --threshold 4.5 --window 8
```

This command loads `example-data/sample_panel.csv`, flags readings that exceed the rolling baseline by at least 4.5 °C within an 8-sample window, and stores the results alongside your dataset.

## Contributing

Contributions are welcome! Please fork the repository and open a pull request with your improvements or ideas.

## License

This project is released under the MIT License. See `LICENSE` (to be added) for details.
