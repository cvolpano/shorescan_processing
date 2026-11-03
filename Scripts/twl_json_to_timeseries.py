"""
twl_json_to_timeseries.py

Author:  Chelsea A. Volpano (cvolpano@gmail.com)
Created: 2026-11-02
Model:   Generated with Claude Opus 5.5 (Anthropic), claude.ai

Summary
-------
Converts forecast JSON downloads from the USGS/NOAA Total Water Level and
Coastal Change (TWL&CC) Forecast Viewer into two CSV time series. Several
forecasts can be issued per day; each file is one forecast issue:

1. <prefix>_all_forecasts_long.csv
   Every hourly value from every forecast file, with the forecast issue
   time and lead time (hours) attached. Use for forecast-skill work.
2. <prefix>_best_estimate.csv
   One row per hour: the value from the shortest-lead forecast available.
   Hours that no forecast covers are kept as NaN rows with gap=True.

Vertical datum: values are kept as delivered, in metres relative to NAVD88
    (Birchler et al., 2024, https://doi.org/10.1016/j.coastaleng.2024.104590).
    NO additional datum conversion is applied.
Time: the JSON 'dateTime' field is GMT/UTC; it is converted to
    America/New_York (EST/EDT, daylight saving handled). Both UTC and local
    columns are written with explicit offsets, e.g. 2024-12-13 19:00:00-05:00.

Usage
-----
Command line:
    python twl_json_to_timeseries.py --input-dir ../DATA/data_wl
Notebook:
    from twl_json_to_timeseries import process_folder
    long_df, best_df = process_folder("../DATA/data_wl")

Change log
----------
2026-11-02  Initial version.
2026-11-02  README now explains rolling vs best-estimate series, caveats,
            and a table of best-estimate hours by lead day.
2026-11-02  Supports several issues per day: issue time read from
            _YYYY-MM-DDTHHMM file names (old daily files = 00:00 UTC);
            checks each forecast starts at its issue time; finer lead bins.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

LOCAL_TZ = "America/New_York"
FILL_VALUES = [-999.0, -9999.0, -99999.0]  # common fill values -> NaN
# Filenames: "Boston,_MA_1548_2024-12-14T0600.json" (issue time, UTC) from
# twl_download.py, or the older daily "Boston,_MA_1548_2024-12-14.json",
# which is the 00:00 UTC issue.
FILE_RE = re.compile(r"^(?P<prefix>.+)_(?P<date>\d{4}-\d{2}-\d{2})"
                     r"(?:T(?P<hhmm>\d{4}))?\.json$")
# TWL = tide + surge + R2; tideWindSetup already includes wave setup, so
# twl = tideWindSetup - setup + runup. Each term is rounded to 0.01 m.
CLOSURE_TOL_M = 0.021


def read_forecast(path: Path) -> pd.DataFrame | None:
    """Read one forecast JSON into a DataFrame (one row per hour).

    Returns None (with a warning) for unreadable or malformed files so a
    single bad download does not stop the whole run.
    """
    match = FILE_RE.match(path.name)
    if match is None:
        print(f"WARNING: skipping {path.name} (name has no _YYYY-MM-DD date)")
        return None
    try:
        with path.open() as f:
            df = pd.DataFrame(json.load(f))  # dict-of-lists or list-of-dicts
    except (json.JSONDecodeError, ValueError, OSError) as err:
        print(f"WARNING: skipping {path.name}: {err}")
        return None
    if df.empty or "dateTime" not in df.columns:
        print(f"WARNING: skipping {path.name} (empty or no 'dateTime')")
        return None

    # Issue time from the file name; old daily files are the 00:00 issue.
    hhmm = match["hhmm"] or "0000"
    df["issue_time_utc"] = pd.Timestamp(
        f"{match['date']} {hhmm[:2]}:{hhmm[2:]}", tz="UTC")
    return df


def build_long_table(files: list[Path]) -> pd.DataFrame:
    """Stack all forecasts into one long table with lead times."""
    # Read every file, then concatenate ONCE (cheap); concatenating inside
    # the loop would copy the growing table each time (slow, memory-heavy).
    frames = [df for p in files if (df := read_forecast(p)) is not None]
    if not frames:
        raise FileNotFoundError("No readable forecast JSON files found.")
    long = pd.concat(frames, ignore_index=True)

    # Naive 'dateTime' strings are GMT -> parse as timezone-aware UTC.
    long["valid_time_utc"] = pd.to_datetime(long.pop("dateTime"), utc=True)

    # Replace fill values with NaN in every numeric column at once.
    num_cols = long.select_dtypes("number").columns
    long[num_cols] = long[num_cols].replace(FILL_VALUES, np.nan)

    lead = (long["valid_time_utc"] - long["issue_time_utc"]) / pd.Timedelta("1h")
    long["lead_hours"] = lead.round().astype("int64")

    # Check that each forecast starts at its issue time. A non-zero first
    # step means the issue time in the file name is not the forecast start.
    first = long.groupby("issue_time_utc")["lead_hours"].min()
    off = first[first != 0]
    if len(off):
        print(f"NOTE: {len(off)} of {len(first)} forecasts do not start at "
              f"their issue time (first-step offsets, h: "
              f"{sorted(off.unique().tolist())})")

    # Drop steps before the issue time (date/filename mismatch) and any
    # repeated hours within one forecast.
    n_neg = int((long["lead_hours"] < 0).sum())
    if n_neg:
        print(f"WARNING: dropping {n_neg} rows with negative lead time")
    long = long[long["lead_hours"] >= 0]
    long = long.drop_duplicates(["issue_time_utc", "valid_time_utc"])

    long["valid_time_local"] = long["valid_time_utc"].dt.tz_convert(LOCAL_TZ)
    long["issue_time_local"] = long["issue_time_utc"].dt.tz_convert(LOCAL_TZ)

    front = ["valid_time_local", "valid_time_utc", "issue_time_local",
             "issue_time_utc", "lead_hours"]
    long = long[front + [c for c in long.columns if c not in front]]
    # Sorting by lead within each hour lets build_best_estimate pick the
    # shortest lead with a single drop_duplicates call.
    return long.sort_values(["valid_time_utc", "lead_hours"],
                            ignore_index=True)


def build_best_estimate(long: pd.DataFrame,
                        max_lead_hours: int | None = None) -> pd.DataFrame:
    """Keep the shortest-lead value for each hour on a gap-free hourly grid.

    max_lead_hours: optional cap; hours only covered by longer leads become
    NaN gaps (e.g. 23 to use only day-1 forecasts).
    """
    src = long if max_lead_hours is None else long[
        long["lead_hours"] <= max_lead_hours]
    best = src.drop_duplicates("valid_time_utc", keep="first")  # long is sorted

    # Reindex onto a continuous hourly UTC grid so missing hours appear as
    # NaN rows instead of silently vanishing.
    grid = pd.date_range(long["valid_time_utc"].min(),
                         long["valid_time_utc"].max(), freq="h", tz="UTC",
                         name="valid_time_utc")
    best = best.set_index("valid_time_utc").reindex(grid).reset_index()
    best["valid_time_local"] = best["valid_time_utc"].dt.tz_convert(LOCAL_TZ)
    best["lead_hours"] = best["lead_hours"].astype("Int64")  # NaN-safe int
    best["gap"] = best["lead_hours"].isna()

    front = ["valid_time_local", "valid_time_utc", "lead_hours", "gap"]
    return best[front + [c for c in best.columns if c not in front]]


def check_twl_closure(df: pd.DataFrame) -> None:
    """Report whether twl == tideWindSetup - setup + runup (rounding tol.)."""
    needed = {"twl", "tideWindSetup", "setup", "runup"}
    if not needed.issubset(df.columns):
        return
    resid = df["twl"] - (df["tideWindSetup"] - df["setup"] + df["runup"])
    bad = int((resid.abs() > CLOSURE_TOL_M).sum())
    print(f"TWL closure check: {bad} of {resid.notna().sum()} rows exceed "
          f"{CLOSURE_TOL_M} m (max |resid| = {resid.abs().max():.3f} m)")


README_TEMPLATE = """\
TWL&CC FORECAST TIME SERIES (USGS/NOAA Total Water Level Viewer)
=================================================================
Created {created} by twl_json_to_timeseries.py from {n_files} forecast files.
Period (local): {start} to {end}

FILES
-----
{stem}_all_forecasts_long.csv   every hour of every forecast ("rolling")
{stem}_best_estimate.csv        one value per hour ("best estimate")

UNITS, DATUM AND TIME
---------------------
twl, twl05, twl95, tideWindSetup  m, NAVD88 (as delivered; no conversion)
setup, runup*, swash, incSwash,
  infragSwash                     m (heights above the mean water level)
hs                                significant wave height, m
pp                                peak wave period, s
valid_time_utc                    time the value applies to, UTC
valid_time_local                  same time in {tz}, with UTC offset
issue_time_*                      forecast issue time, from the file name
                                  (_YYYY-MM-DDTHHMM, UTC; files with no
                                  THHMM are the 00:00 UTC issue)
lead_hours                        valid time minus issue time, hours
Source: Birchler et al. (2024), https://doi.org/10.1016/j.coastaleng.2024.104590

HOW THE FORECASTS OVERLAP
-------------------------
Each file is one forecast issue. The TWL&CC forecast is re-issued when NWS
offices update their wave forecasts, typically 2-4 times per day (e.g.
00:00, 06:00, 12:00 UTC on 2024-12-14), and more often during storms
(Stockdon et al., 2023, https://doi.org/10.1038/s43247-023-00817-2).
Each issue gives hourly values for 6 days (lead 0 to 144 h), so the issues
overlap heavily: any given hour is predicted by many forecasts, each made a
different amount of time ahead. With 6-hourly issues:

  valid time ->   00-05Z  06-11Z  12-17Z  18-23Z  next day ...
  issued 00Z     [0-5h]  [6-11]  [12-17] [18-23] [24-47]  ...
  issued 06Z             [0-5h]  [6-11]  [12-17] [18-41]  ...
  issued 12Z                     [0-5h]  [6-11]  [12-35]  ...
                    ^       ^       ^       ^
                 best estimate takes the shortest-lead value available in
                 each column; if no 18Z issue exists, 18-23Z comes from the
                 12Z issue at lead 6-11 h

Forecasts generally lose skill as lead time grows, because the wave and
surge inputs become less certain the further ahead they look. A value
predicted 6 h ahead is usually more reliable than one predicted 5 days
ahead.

1) ROLLING FORECASTS: *_all_forecasts_long.csv
   Keeps every value from every forecast, one row per (issue time, valid
   time) pair. Nothing is discarded.
   Use it to:
   - measure forecast skill as a function of lead time against observations
     (e.g. a tide gauge or pressure sensor);
   - see how the prediction for one storm changed from issue to issue;
   - reconstruct the full 6-day forecast from any one issue:
       df[df.issue_time_utc == "2024-12-14 06:00:00+00:00"]
   - pull a fixed-lead series, e.g. only 24-47 h-ahead values:
       df[df.lead_hours.between(24, 47)]

2) BEST ESTIMATE: *_best_estimate.csv
   For each hour, keeps only the value from the most recent forecast,
   i.e. the shortest lead time available. This gives one continuous series
   that is the best prediction available for each hour, given the files
   downloaded. With every issue downloaded, that is usually lead 0-11 h.
   - If an issue is missing, its hours are filled from an earlier
     forecast at a longer lead; lead_hours shows when this happened.
   - If no forecast covers an hour, the row is kept with NaN values and
     gap=True, so the time axis stays regular.
   Use it for:
   - a continuous record to compare with observations or to plot;
   - counting hours above a threshold (e.g. dune toe or crest elevation);
   - input to other analyses that need one value per hour.

CAVEATS
-------
- The best estimate is stitched together from separate forecasts. Small
  jumps can appear where it switches from one forecast issue to the next
  (e.g. at 00, 06, 12 UTC). These are forecast-to-forecast differences,
  not physical events.
- It is still a forecast, not an observation or a hindcast.
- The last ~6 days of the best estimate come only from the final forecast,
  so their lead times run up to 144 h. Check lead_hours, or rebuild with
  max_lead_hours (e.g. 11 or 23) to keep short-lead values only.
- lead_hours is measured from the issue time the API reports. Issue times
  are assumed to be UTC, like the dateTime values; the script prints a NOTE
  if any forecast does not start at its issue time.
- Jumps in pp (and so in setup/runup) inside one forecast are usually the
  spectral peak switching between swell and wind sea, not bad data.
  Runup scales with sqrt(Hs * L0), where L0 depends on Tp
  (Stockdon et al., 2006, https://doi.org/10.1016/j.coastaleng.2005.12.005).
- Reading the CSVs with pandas: the text "None" in predictedImpact is read
  as missing by default; use keep_default_na=False, na_values=[""] to keep it.

THIS RUN: BEST-ESTIMATE HOURS BY LEAD TIME
------------------------------------------
{lead_table}
Gap hours (no forecast available): {n_gap}
"""


def write_readme(path: Path, n_files: int, best: pd.DataFrame) -> None:
    """Write a metadata sidecar: units, datum, time, and how to use each CSV."""
    # Count best-estimate hours per lead bin in one vectorized pd.cut call:
    # 6-h bins within day 1, then whole days (the final 144 h step is in
    # the last bin).
    edges = [0, 6, 12, 18, 24, 48, 72, 96, 120, 145]
    labels = ["0-5 h", "6-11 h", "12-17 h", "18-23 h", "24-47 h (day 2)",
              "48-71 h (day 3)", "72-95 h (day 4)", "96-119 h (day 5)",
              "120-144 h (day 6)"]
    counts = pd.cut(best["lead_hours"].dropna().astype(int), edges,
                    right=False, labels=labels).value_counts(sort=False)
    lead_table = "\n".join(f"  lead {lab:<18}: {n:>6} hours"
                           for lab, n in counts.items() if n)

    path.write_text(README_TEMPLATE.format(
        created=pd.Timestamp.now(tz=LOCAL_TZ).strftime("%Y-%m-%d"),
        n_files=n_files,
        start=best["valid_time_local"].iloc[0],
        end=best["valid_time_local"].iloc[-1],
        stem=path.name.removesuffix("_README.txt"),
        tz=LOCAL_TZ,
        lead_table=lead_table,
        n_gap=int(best["gap"].sum())))


def process_folder(input_dir: str | Path, output_dir: str | Path | None = None,
                   max_lead_hours: int | None = None
                   ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build and save the long and best-estimate CSVs for one site folder."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir) if output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in input_dir.glob("*.json") if FILE_RE.match(p.name))
    prefixes = {FILE_RE.match(p.name)["prefix"] for p in files}
    if len(prefixes) > 1:
        raise ValueError(f"Several sites in one folder: {sorted(prefixes)}")

    long = build_long_table(files)
    best = build_best_estimate(long, max_lead_hours)
    check_twl_closure(long)

    start = best["valid_time_local"].iloc[0].strftime("%Y%m%d")
    end = best["valid_time_local"].iloc[-1].strftime("%Y%m%d")
    stem = f"{prefixes.pop()}_{start}-{end}"
    long.to_csv(output_dir / f"{stem}_all_forecasts_long.csv", index=False)
    best.to_csv(output_dir / f"{stem}_best_estimate.csv", index=False)
    write_readme(output_dir / f"{stem}_README.txt", len(files), best)

    print(f"Read {len(files)} files -> {len(long)} forecast rows, "
          f"{len(best)} hourly rows ({int(best['gap'].sum())} gap hours)")
    print(f"Saved to {output_dir.resolve()} as {stem}_*.csv")
    return long, best


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--input-dir", required=True,
                        help="folder with one site's TWL JSON files")
    parser.add_argument("--output-dir", default=None,
                        help="where to write CSVs (default: input dir)")
    parser.add_argument("--max-lead-hours", type=int, default=None,
                        help="optional cap on lead time for best estimate")
    args = parser.parse_args()
    process_folder(args.input_dir, args.output_dir, args.max_lead_hours)
