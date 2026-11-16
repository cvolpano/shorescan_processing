"""
Convert ShoreScan transect YAML files to CSV.

Author:  Chelsea A. Volpano (cvolpano@gmail.com)
Revised: 2026-11-14 with Claude Opus 5.5 (claude-opus-5-5)

SUMMARY
-------
Reads one transect YAML or a folder of them and writes CSVs, one column
per key (e.g. U, V pixel coordinates), one row per point. Handles two
layouts:
  flat   : U: 360, 359, ...  /  V: 390, 390, ...   -> <stem>.csv
  nested : transect_0: {Easting: ..., Northing: ...} -> <stem>_transect_0.csv
IO/EO calibration YAMLs (*_IO.yaml, *_EO.yaml) in the same folder are
skipped.

USAGE
-----
python process_transect_yaml.py <file_or_folder> [output_directory]

REVISION SUMMARY
----------------
2026-11-14  Folder input; skip IO/EO files; support flat U/V layout
            (previously wrote nothing for it); output_directory now used;
            removed duplicate 'transect' in nested output names.
"""

import csv
import sys
from itertools import zip_longest
from pathlib import Path

import yaml

CALIB_SUFFIXES = ("_IO", "_EO")


def flatten_dict(d, parent_key="", sep="."):
    """Recursively flatten nested dicts to dot-notated keys."""
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def to_list(value):
    """Turn a comma-separated string, list, or scalar into a list of str."""
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value]
    return [str(value).strip()]


def group_transects(data, stem):
    """
    Return {output_name: {column: [values]}}.

    Nested keys ('transect_0.Easting') are grouped by their first part;
    top-level keys ('U', 'V') form a single transect named after the file.
    """
    groups = {}
    for key, value in flatten_dict(data).items():
        if "." in key:
            tid, metric = key.split(".", 1)
            name = f"{stem}_{tid}"
        else:
            name, metric = stem, key
        groups.setdefault(name, {})[metric] = to_list(value)
    return groups


def write_csv(path, columns):
    """Write {column: [values]} to CSV; shorter columns padded with ''."""
    fieldnames = sorted(columns)
    # zip_longest pairs up the i-th value of every column in one pass,
    # filling gaps with '' when column lengths differ.
    rows = zip_longest(*(columns[c] for c in fieldnames), fillvalue="")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)
        n = 0
        for row in rows:
            writer.writerow(row)
            n += 1
    lengths = {len(columns[c]) for c in fieldnames}
    if len(lengths) > 1:
        print(f"  ⚠️ unequal column lengths in {path.name}: "
              f"{ {c: len(columns[c]) for c in fieldnames} }")
    return n


def process_transect_yaml(yaml_file, output_dir="."):
    """Convert one transect YAML to CSV(s). Returns number of CSVs written."""
    yaml_file = Path(yaml_file)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    try:
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"❌ YAML parsing error in {yaml_file.name}: {e}")
        return 0

    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        print(f"❌ {yaml_file.name}: root must be a mapping; skipped.")
        return 0

    written = 0
    for name, columns in group_transects(data, yaml_file.stem).items():
        csv_path = out_path / f"{name}.csv"
        n = write_csv(csv_path, columns)
        print(f"📁 {csv_path} ({n} rows)")
        written += 1
    return written


def resolve_yaml_inputs(input_path):
    """Return transect YAMLs from a file or folder, excluding IO/EO files."""
    path = Path(input_path)
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"Path does not exist: {path}")
    files = sorted(p for p in path.glob("*.y*ml")
                   if not p.stem.upper().endswith(CALIB_SUFFIXES))
    if not files:
        raise FileNotFoundError(f"No transect .yaml/.yml files in {path}")
    return files


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_transect_yaml.py "
              "<file_or_folder> [output_directory]")
        sys.exit(1)

    output_directory = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path(".")
    files = resolve_yaml_inputs(sys.argv[1])
    total = sum(process_transect_yaml(f, output_directory) for f in files)
    print(f"\n✅ Wrote {total} CSV(s) from {len(files)} YAML file(s) "
          f"to '{output_directory.resolve()}'.")
