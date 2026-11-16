"""
run_runup.py
------------
Author : Chelsea A. Volpano (cvolpano@gmail.com)
Date   : 2026-11-11
Model  : Generated with Claude Opus 5.5 (claude-opus-5-5)

Summary
    Headless (no-notebook) version of the CoastCam runup cell, for HPC batch
    jobs. Loads config.json, builds an ImageDatastore, drops non-transect
    image products, extracts runup with the SegFormer model, rectifies onto
    the DEM, and writes NetCDF output.

Usage
    python -u run_runup.py                       # defaults: ./config.json, ./CODES
    python -u run_runup.py --config my.json --codes-dir /path/to/CODES
    python -u run_runup.py --no-save             # quick test, no NetCDF written

Changelog
    2026-11-11  Converted from CoastCam_processing.ipynb cell.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

# Compute nodes have no display. Set a non-GUI backend before anything
# (e.g., ImageHandler) imports pyplot, or plotting calls can crash the job.
import matplotlib
matplotlib.use("Agg")

# Config keys that hold file paths (taken from the notebook comments).
PATH_KEYS = ("imageDir", "demPath", "segformerCodeDir", "segformerModel")


def parse_args():
    """Read command-line options so paths aren't hard-coded."""
    p = argparse.ArgumentParser(description="Extract runup from CoastCam timestacks.")
    p.add_argument("--config", default="config.json", help="Path to config.json")
    p.add_argument("--codes-dir", default="CODES", help="Path to the CODES folder")
    p.add_argument("--no-save", action="store_true", help="Skip writing NetCDF (test runs)")
    return p.parse_args()


def check_config_paths(config):
    """Fail early if config paths are Windows-style or missing on this machine."""
    problems = []
    for key in PATH_KEYS:
        val = config.get(key)
        if val is None:
            continue  # key not used in this config
        if ":\\" in str(val) or ":/" in str(val)[:3]:
            problems.append(f"{key} looks like a Windows path: {val}")
        elif not Path(val).exists():
            problems.append(f"{key} does not exist: {val}")
    if problems:
        raise FileNotFoundError("Fix config.json before running:\n  " + "\n  ".join(problems))


def main():
    args = parse_args()
    t0 = time.time()

    # Resolve paths relative to THIS file, not the shell's working directory.
    # In Jupyter the working dir is the notebook folder; in a batch job it may
    # not be, so 'CODES' and 'config.json' would silently point elsewhere.
    base = Path(__file__).resolve().parent
    codes_dir = (base / args.codes_dir).resolve()
    config_path = (base / args.config).resolve()
    os.chdir(base)  # match notebook behaviour for any relative paths inside CODES

    if str(codes_dir) not in sys.path:
        sys.path.append(str(codes_dir))
    from ImageHandler import ImageDatastore  # import after sys.path is set

    with open(config_path, "r") as f:
        config = json.load(f)
    check_config_paths(config)
    print(f"Config: {config_path}\nCODES : {codes_dir}", flush=True)

    # # Split .tiff files from i2RGUS into individual transects
    # # (kept commented out, as in the notebook)
    # if config.get('split_tiff', False) is True:
    #     import utils_runup
    #     utils_runup.split_tiff(config)

    # Set up datastore for all files in imageDir
    datastore = ImageDatastore(configPath=config)

    # Remove image products -> keep transects
    datastore.remove_images_by_type(["snap", "timex", "var", "bright", "dark"])
    datastore.image_stats()

    # Runup from SegFormer, rectified onto DEM, saved to NetCDF
    datastore.get_runup_from_timestacks(segformer_flag=True, save_flag=not args.no_save)

    print(f"Done in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
