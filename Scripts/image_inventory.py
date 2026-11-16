"""
image_inventory.py
==================
Author : Chelsea A. Volpano (cvolpano@gmail.com)
Created: 2026-11-13
Model  : Claude Opus 5.5 (claude-opus-5-5)

Summary
-------
Recursively inventories CoastCam image files named like

    1727780400.Tue.Oct.01_11_00_00.GMT.2024.CACO03.c1.ras.tiff
    <epoch UTC>.<dow>.<Mon>.<DD>_<HH>_<MM>_<SS>.GMT.<YYYY>.<calib>.<cam>.ras.tiff

Change log
----------
2026-11-13  Created.
2026-11-13  Default extension .ras -> .ras.tiff (regex accepts .ras,
            .ras.tif, .ras.tiff). Use --ext to search a different ending.

and produces, per camera (c1, c2, ...):
  * an availability plot: present (coloured by calibration ID, e.g. CACO03 /
    CACO04) vs. missing, on a regular expected time grid;
  * a daily percent-complete panel;
  * CSVs of the file inventory and of every gap (start, end, # missing).

Times are taken from the leading Unix epoch (seconds, UTC) and cross-checked
against the human-readable GMT stamp. All times stay in UTC; no CRS/time-zone
conversion is performed.

Usage
-----
    python image_inventory.py /path/to/images
    python image_inventory.py /path/to/images --interval 30min --out avail.png
"""

import argparse
import os
import re
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

# One regex with named groups; pandas .str.extract applies it to every name
# at once (vectorized) instead of looping over files with re.match.
FNAME_RE = re.compile(
    r"^(?P<epoch>\d{9,11})\."           # Unix epoch seconds (UTC)
    r"[A-Za-z]{3}\."                     # day of week (ignored)
    r"(?P<mon>[A-Za-z]{3})\.(?P<day>\d{2})_"
    r"(?P<hms>\d{2}_\d{2}_\d{2})\.GMT\."
    r"(?P<year>\d{4})\."
    r"(?P<calib>[^.]+)\."               # calibration ID, e.g. CACO03
    r"(?P<cam>c\d+)\."                  # camera, e.g. c1
    # r"ras$",  # 2026-11-13: files are actually *.ras.tiff; see next line
    r"ras(?:\.tiff?)?$",                # .ras, .ras.tif or .ras.tiff
    flags=re.IGNORECASE,
)

MISSING_COLOR = "#f2b8b5"
CALIB_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b"]


# def scan_files(root, ext=".ras"):  # 2026-11-13: default now .ras.tiff
def scan_files(root, ext=".ras.tiff"):
    """Yield (name, path) of every file under `root` ending in `ext`.

    os.scandir returns the file type with the directory listing, so it is
    much faster than os.walk/Path.rglob on large or network-mounted trees.
    An explicit stack avoids Python's recursion limit on deep trees.
    """
    ext = ext.lower()
    stack = [str(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.name.lower().endswith(ext):
                        yield entry.name, entry.path
        except (PermissionError, FileNotFoundError) as err:
            print(f"  [skip] {current}: {err}")


# def build_inventory(root, ext=".ras"):  # 2026-11-13: default .ras.tiff
def build_inventory(root, ext=".ras.tiff"):
    """Return a DataFrame (time, cam, calib, fname, path), one row per image."""
    records = list(scan_files(root, ext))
    if not records:
        raise FileNotFoundError(f"No '*{ext}' files found under {root}")
    names, paths = zip(*records)

    df = pd.Series(names).str.extract(FNAME_RE)
    df["fname"], df["path"] = names, paths

    bad = df["epoch"].isna()
    if bad.any():
        print(f"  [warn] {bad.sum()} files skipped (name does not match "
              f"pattern), e.g. {df.loc[bad, 'fname'].iloc[0]}")
    df = df.loc[~bad].copy()

    # Epoch -> tz-aware UTC timestamps.
    df["time"] = pd.to_datetime(df["epoch"].astype("int64"), unit="s",
                                utc=True)

    # Cross-check against the readable GMT stamp; flags renamed/corrupt files.
    stamp = (df["year"] + "-" + df["mon"] + "-" + df["day"] + " "
             + df["hms"].str.replace("_", ":"))
    t_stamp = pd.to_datetime(stamp, format="%Y-%b-%d %H:%M:%S", utc=True,
                             errors="coerce")
    mismatch = (t_stamp - df["time"]).abs() > pd.Timedelta("1s")
    if mismatch.any():
        print(f"  [warn] {mismatch.sum()} files: epoch != GMT stamp, e.g. "
              f"{df.loc[mismatch, 'fname'].iloc[0]} (epoch time used)")

    df["calib"] = df["calib"].str.upper()
    df["cam"] = df["cam"].str.lower()

    # The same image may sit in two folders (e.g. copies); keep one.
    df = df.sort_values(["cam", "time", "calib"])
    dup = df.duplicated(["cam", "time"])
    if dup.any():
        print(f"  [info] {dup.sum()} duplicate (cam, time) entries dropped")
    cols = ["time", "cam", "calib", "fname", "path"]
    return df.loc[~dup, cols].reset_index(drop=True)


def infer_interval(times):
    """Most common spacing between consecutive images (robust to gaps)."""
    d = times.sort_values().diff().dropna().dt.round("1s")
    d = d[d > pd.Timedelta(0)]
    if d.empty:
        raise ValueError("Need >= 2 distinct times to infer an interval; "
                         "pass --interval explicitly.")
    return d.mode().iloc[0]


def presence_grids(inv, interval):
    """Map each camera onto one shared regular grid.

    Returns {cam: Series(index=grid, values=label)}; label 0 = missing,
    k >= 1 = present with calibration k. Times are rounded to the grid so a
    few seconds of clock jitter still counts as present.
    """
    calibs = sorted(inv["calib"].unique())
    code = {c: i + 1 for i, c in enumerate(calibs)}
    t = inv["time"].dt.round(interval)
    grid = pd.date_range(t.min(), t.max(), freq=interval)

    grids = {}
    for cam, idx in inv.groupby("cam").groups.items():
        s = pd.Series(inv.loc[idx, "calib"].map(code).to_numpy(),
                      index=t.loc[idx])
        s = s[~s.index.duplicated()]
        grids[cam] = s.reindex(grid, fill_value=0).astype("int16")
    return grids, calibs


def run_lengths(labels):
    """Run-length encode a label Series -> DataFrame(start, n, label).

    np.diff finds every index where the label changes, so contiguous blocks
    are found without a Python loop over (possibly) 100k+ time steps.
    """
    v = labels.to_numpy()
    starts = np.r_[0, np.flatnonzero(np.diff(v)) + 1]
    n = np.diff(np.r_[starts, v.size])
    return pd.DataFrame({"start": labels.index[starts], "n": n,
                         "label": v[starts]})


def gap_table(grids, interval):
    """Every run of missing images: cam, start, end, n_missing."""
    rows = []
    for cam, labels in grids.items():
        r = run_lengths(labels)
        r = r[r["label"] == 0]
        rows.append(pd.DataFrame({
            "cam": cam,
            "start": r["start"],
            "end": r["start"] + (r["n"] - 1) * interval,
            "n_missing": r["n"],
            "duration": r["n"] * interval,
        }))
    return pd.concat(rows, ignore_index=True).sort_values(["cam", "start"])


def plot_availability(grids, calibs, interval, out=None, title=None):
    """Two-panel figure: availability bars and daily % complete."""
    cams = sorted(grids)
    fig, (ax0, ax1) = plt.subplots(
        2, 1, sharex=True, figsize=(12, 1.0 * len(cams) + 3.5),
        gridspec_kw={"height_ratios": [len(cams), 2]})
    width = interval / pd.Timedelta("1D")      # matplotlib x-units are days
    colors = {0: MISSING_COLOR}
    colors.update({i + 1: CALIB_COLORS[i % len(CALIB_COLORS)]
                   for i in range(len(calibs))})

    for row, cam in enumerate(cams):
        r = run_lengths(grids[cam])
        x0 = mdates.date2num(r["start"].dt.tz_localize(None))
        # One broken_barh call per label (few) instead of one bar per image.
        for lab, sub in r.groupby("label"):
            spans = list(zip(x0[sub.index], sub["n"] * width))
            ax0.broken_barh(spans, (row - 0.4, 0.8),
                            facecolors=colors[lab], edgecolor="none")

        daily = (grids[cam] > 0).resample("D").mean() * 100
        ax1.step(daily.index.tz_localize(None), daily.to_numpy(),
                 where="post", label=cam, lw=1.2)

    ax0.set_yticks(range(len(cams)), cams)
    ax0.set_ylim(-0.6, len(cams) - 0.4)
    ax0.invert_yaxis()
    handles = [Patch(color=colors[i + 1], label=c)
               for i, c in enumerate(calibs)]
    handles.append(Patch(color=MISSING_COLOR, label="missing"))
    ax0.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1),
               frameon=False)
    step = pd.tseries.frequencies.to_offset(interval).freqstr
    ax0.set_title(title or f"Image availability (expected every {step})")

    ax1.set_ylim(0, 105)
    ax1.set_ylabel("% present (daily)")
    ax1.set_xlabel("Time (UTC)")
    ax1.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False)
    ax1.grid(alpha=0.3)
    locator = mdates.AutoDateLocator()
    ax1.xaxis.set_major_locator(locator)
    ax1.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=200, bbox_inches="tight")
        print(f"  saved figure -> {out}")
    return fig


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("root", type=Path, help="top folder to search recursively")
    p.add_argument("--interval", default=None,
                   help="expected spacing, e.g. 30min, 1h (default: infer)")
    # p.add_argument("--ext", default=".ras", help="file extension (.ras)")
    # 2026-11-13: images are saved as <name>.ras.tiff
    p.add_argument("--ext", default=".ras.tiff",
                   help="file ending to search for (default .ras.tiff)")
    p.add_argument("--out", default="image_availability.png")
    p.add_argument("--show", action="store_true", help="open plot window")
    a = p.parse_args()

    print(f"Scanning {a.root} ...")
    inv = build_inventory(a.root, a.ext)
    interval = (pd.Timedelta(a.interval) if a.interval
                else infer_interval(inv["time"]))
    print(f"  {len(inv)} images, {inv['time'].min()} to {inv['time'].max()}")
    print(f"  expected interval: {interval}"
          f"{'' if a.interval else ' (inferred)'}")

    grids, calibs = presence_grids(inv, interval)
    for cam, g in sorted(grids.items()):
        n_ok = int((g > 0).sum())
        print(f"  {cam}: {n_ok}/{g.size} present ({100 * n_ok / g.size:.1f}%)")

    stem = Path(a.out).with_suffix("")
    inv.to_csv(f"{stem}_inventory.csv", index=False)
    gap_table(grids, interval).to_csv(f"{stem}_gaps.csv", index=False)
    print(f"  saved {stem}_inventory.csv and {stem}_gaps.csv")

    plot_availability(grids, calibs, interval, out=a.out)
    if a.show:
        plt.show()


if __name__ == "__main__":
    main()