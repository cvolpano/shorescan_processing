"""
missing_filenames.py
====================
Author : Chelsea A. Volpano (cvolpano@gmail.com)
Created: 2026-11-14
Model  : Claude Opus 5.5 (claude-opus-5-5)

Summary
-------
Lists the expected filename of every missing CoastCam image, e.g.

    1727780400.Tue.Oct.01_11_00_00.GMT.2024.CACO03.c1.ras.tiff

Uses image_inventory.py (must be in the same folder or on PYTHONPATH) to
scan the archive and build the regular expected-time grid; every empty slot
on that grid gets a reconstructed name.

Calibration ID for a missing slot is copied from the most recent present
image of the same camera (or the next one, for gaps at the very start).
When the images on either side of a gap use different calibrations, the
slot is flagged `calib_uncertain=True` so you can check it by hand.

Before writing anything, the name builder is run on the images that DO
exist and compared with their real filenames; any mismatch is reported,
so you know the reconstructed names follow the real convention.

Outputs (UTC throughout, no time-zone conversion):
  <out>.csv  cam, time_utc, epoch, calib, calib_uncertain, expected_fname
  <out>.txt  expected filenames only, one per line

Usage
-----
    python missing_filenames.py /path/to/images
    python missing_filenames.py /path/to/images --interval 30min --out missing

Change log
----------
2026-11-14  Created.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from image_inventory import build_inventory, infer_interval, presence_grids

# Fixed English names: strftime's %a/%b follow the computer's locale, which
# would silently produce e.g. "Mar." for Tuesday on a Spanish-locale system.
DOW = np.array(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
MON = np.array(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])


def to_epoch(t):
    """Whole Unix seconds for a tz-aware UTC DatetimeIndex.

    Subtracting 1970-01-01 and dividing by 1 s works whatever internal unit
    pandas stores (ns in pandas 1.x, often s/us in 2.x); `.asi8 // 1e9`
    silently assumes nanoseconds.
    """
    return ((t - pd.Timestamp(0, tz="UTC")) // pd.Timedelta("1s")).to_numpy()


def make_fnames(times, calib, cam, suffix=".ras.tiff"):
    """Build CoastCam filenames for arrays of UTC times (vectorized).

    times : tz-aware UTC DatetimeIndex
    calib : array-like of calibration IDs, same length (or a single string)
    cam   : array-like of camera IDs, same length (or a single string)
    """
    t = pd.DatetimeIndex(times)
    epoch = to_epoch(t).astype(str)
    stamp = (DOW[t.dayofweek] + "." + MON[t.month - 1] + "."
             + t.strftime("%d_%H_%M_%S") + ".GMT." + t.strftime("%Y"))
    calib = np.broadcast_to(np.asarray(calib, dtype=str), epoch.shape)
    cam = np.broadcast_to(np.asarray(cam, dtype=str), epoch.shape)
    # Element-wise string join on numpy arrays, no Python loop.
    out = np.char.add(epoch, ".")
    for part in (stamp, ".", calib, ".", cam, suffix):
        out = np.char.add(out, part)
    return out


def check_round_trip(inv, suffix):
    """Rebuild names of existing files; return the rows that don't match."""
    rebuilt = make_fnames(inv["time"], inv["calib"].to_numpy(),
                          inv["cam"].to_numpy(), suffix)
    bad = inv.loc[rebuilt != inv["fname"].to_numpy(), ["fname"]].copy()
    bad["rebuilt"] = rebuilt[rebuilt != inv["fname"].to_numpy()]
    return bad


def missing_table(grids, calibs, suffix):
    """One row per missing slot with its expected filename."""
    names = np.array(calibs)
    rows = []
    for cam, labels in sorted(grids.items()):
        lab = labels.replace(0, np.nan)          # NaN = missing slot
        prev, nxt = lab.ffill(), lab.bfill()     # neighbours either side
        miss = lab.isna()
        if not miss.any():
            continue
        code = prev[miss].fillna(nxt[miss])      # start-of-record gaps
        uncertain = (prev[miss].notna() & nxt[miss].notna()
                     & (prev[miss] != nxt[miss]))
        calib = names[code.astype(int).to_numpy() - 1]
        t = labels.index[miss.to_numpy()]
        rows.append(pd.DataFrame({
            "cam": cam,
            "time_utc": t,
            "epoch": to_epoch(t),
            "calib": calib,
            "calib_uncertain": uncertain.to_numpy(),
            "expected_fname": make_fnames(t, calib, cam, suffix),
        }))
    if not rows:
        return pd.DataFrame(columns=["cam", "time_utc", "epoch", "calib",
                                     "calib_uncertain", "expected_fname"])
    return pd.concat(rows, ignore_index=True)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("root", type=Path, help="top folder to search recursively")
    p.add_argument("--interval", default=None,
                   help="expected spacing, e.g. 30min, 1h (default: infer)")
    p.add_argument("--ext", default=".ras.tiff",
                   help="file ending to search for and to write in names")
    p.add_argument("--out", default="missing_images",
                   help="output stem; writes <out>.csv and <out>.txt")
    a = p.parse_args()

    print(f"Scanning {a.root} ...")
    inv = build_inventory(a.root, a.ext)
    interval = (pd.Timedelta(a.interval) if a.interval
                else infer_interval(inv["time"]))
    print(f"  {len(inv)} images; interval {interval}"
          f"{'' if a.interval else ' (inferred)'}")

    bad = check_round_trip(inv, a.ext)
    if bad.empty:
        print("  name check: all existing filenames reproduced exactly")
    else:
        print(f"  [warn] {len(bad)} existing names not reproduced, e.g.\n"
              f"    real:    {bad['fname'].iloc[0]}\n"
              f"    rebuilt: {bad['rebuilt'].iloc[0]}")

    grids, calibs = presence_grids(inv, interval)
    miss = missing_table(grids, calibs, a.ext)
    for cam, n in miss.groupby("cam").size().items():
        print(f"  {cam}: {n} missing")
    if miss["calib_uncertain"].any():
        print(f"  [note] {int(miss['calib_uncertain'].sum())} missing slots "
              "fall in a gap where the calibration changes; check "
              "`calib_uncertain` in the CSV")

    miss.to_csv(f"{a.out}.csv", index=False)
    Path(f"{a.out}.txt").write_text("\n".join(miss["expected_fname"]) + "\n")
    print(f"  saved {a.out}.csv and {a.out}.txt ({len(miss)} names)")


if __name__ == "__main__":
    main()
