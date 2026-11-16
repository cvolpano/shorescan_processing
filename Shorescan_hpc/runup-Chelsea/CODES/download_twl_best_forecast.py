"""
download_twl_best_forecast.py

Author:  Chelsea A. Volpano (cvolpano@gmail.com)
Created: 2026-11-04
Model:   Claude Opus 5.5 (claude-opus-5-5), via Claude Code

Summary
-------
Downloads every USGS Total Water Level & Coastal Change (TWL&CC) Viewer forecast run
for one site over a date range, then builds ONE best-estimate time series: for each
valid time, it keeps the value from the run with the shortest lead time
(lead = valid time - run start time). A missing run is filled by the next-freshest
forecast, and the `lead_h` column shows where that happened.

Settings come from the pipeline's config.json (CONFIG_JSON): "twl_region", "site_id",
"twlDir" (cache folder), and "productsPath" (lat/lon, only if there is no site_id).

Outputs, all in the same JSON layout as utils_runup.fetch_water_level_data ({key: [values]}):
  - <twlDir>/<Region>_<site>_run<forecast_id>.json : one file per forecast run (cache; reruns
    read these instead of calling the API)
  - OUT_BEST_JSON: best-estimate series, one entry per valid time, with extra keys
    forecast_id, run_time, run_time_source, lead_h. Point config "twlBestJson" at it.
  - OUT_ALL_JSON:  every run stacked (for checking forecast skill vs. lead time)
  - CSV copies of both only if WRITE_CSV = True

Conventions and assumptions
---------------------------
  - Times: API `dateTime` strings without a time zone are treated as UTC (as in
    ImageHandler.compute_runup). All times written out are UTC.
  - Vertical datum: values are saved exactly as the API returns them (NAVD88, per
    user, 2026-11-04). No VDatum conversion is applied.
  - Run start time: taken from the run's own date/time fields when present,
    otherwise the earliest valid time in that run. `run_time_source` records which.
  - Negative lead times (hindcast hours before a run's start) are dropped unless
    INCLUDE_NEGATIVE_LEAD is True.
  - Coordinates: site search uses geographic lat/lon (WGS84, -180..180).

Reuses from utils_runup.py: make_request_with_retry (HTTP 429 handling), bounding_box.

Change log
----------
  - 2026-11-04: first version.
  - 2026-11-04: PRODUCTS_JSON option reads lat/lon from products.json (same site as compute_runup);
                longitude wrapped to -180..180.
  - 2026-11-04: reads twl_region, site_id, twlDir from config.json (CONFIG_JSON); all outputs and
                the per-run cache use the fetch_water_level_data JSON layout; CSV optional (WRITE_CSV).
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from geopy.distance import geodesic

import utils_runup

# ---------------------------------------------------------------- CONFIG
BASE_URL = "https://coastal.er.usgs.gov/hurricanes/research/twlviewer/api/"
CONFIG_JSON = "config.json"             # pipeline config; twl_region, site_id, twlDir read from it if present
REGION_CHOICE = 1                       # 1-based, same as config "twl_region" (overridden by CONFIG_JSON)
LAT, LON = None, None                   # site location (decimal degrees); used if SITE_ID is None
PRODUCTS_JSON = None                    # or path to products.json / site config JSON: lat/lon read from it if LAT/LON unset
SITE_ID = None                          # set to skip the nearest-site search (overridden by CONFIG_JSON)
SEARCH_DISTANCE_M = 500                 # bounding box half-width for the site search
MAX_SITE_DIST_KM = 20                   # same limit as fetch_water_level_data
START_DATE, END_DATE = "2025-03-20", "2025-03-31"   # inclusive, run dates (UTC)
CACHE_DIR = Path("data_twl")            # overridden by config "twlDir" (same folder as the daily files)
# 2026-11-04: outputs switched to JSON (user's format); CSV kept as an option via WRITE_CSV
# OUT_BEST_CSV = Path("DATA/DATA/twl_best_forecast.csv")
# OUT_ALL_CSV = Path("DATA/DATA/twl_all_runs.csv")
OUT_BEST_JSON = None                    # None -> <twlDir>/<Region>_<site>_best_<start>_<end>.json
OUT_ALL_JSON = None                     # None -> <twlDir>/<Region>_<site>_allruns_<start>_<end>.json
WRITE_CSV = False
INCLUDE_NEGATIVE_LEAD = False
# ------------------------------------------------------------------------

RUN_TIME_KEYS = ("forecastDateTime", "runDateTime", "issueDateTime", "dateTime",
                 "startDateTime", "startDate")  # tried in order if no date+time pair


def apply_config_json(path):
    """Fill REGION_CHOICE, SITE_ID, CACHE_DIR and PRODUCTS_JSON from the pipeline config.json."""
    global REGION_CHOICE, SITE_ID, CACHE_DIR, PRODUCTS_JSON
    if not path or not Path(path).is_file():
        print(f"CONFIG_JSON not found ({path}); using values in this script's CONFIG block.")
        return
    cfg = json.loads(Path(path).read_text())
    REGION_CHOICE = int(cfg.get("twl_region") or REGION_CHOICE)
    SITE_ID = cfg.get("site_id", SITE_ID)
    CACHE_DIR = Path(cfg.get("twlDir", CACHE_DIR))
    if PRODUCTS_JSON is None and cfg.get("productsPath"):
        PRODUCTS_JSON = path  # latlon_from_json follows productsPath
    print(f"From {path}: twl_region={REGION_CHOICE}, site_id={SITE_ID}, twlDir={CACHE_DIR}")


def to_dict_of_lists(records):
    """API list of dicts -> {key: [values]} with numbers as float, exactly like fetch_water_level_data."""
    out = {key: [] for key in records[0]}
    for entry in records:
        for key, value in entry.items():
            try:
                out[key].append(float(value))
            except (TypeError, ValueError):
                out[key].append(value)
    return out


def write_dict_of_lists(df, path):
    """DataFrame -> {column: [values]} JSON; times as 'YYYY-MM-DD HH:MM:SS' UTC strings, NaN -> null."""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.tz_convert("UTC").dt.strftime("%Y-%m-%d %H:%M:%S")
    out = out.astype(object).where(out.notna(), None)
    Path(path).write_text(json.dumps({c: out[c].tolist() for c in out.columns}, indent=4))


def get_region(region_choice):
    """Return (region_id, region_name) for a 1-based region index."""
    regions = utils_runup.make_request_with_retry(f"{BASE_URL}regions")
    region = regions[region_choice - 1]
    return region["id"], region["fullName"]


def list_runs(region_id, day):
    """All forecast runs issued on `day` (no time filter, so every cycle is returned)."""
    return utils_runup.make_request_with_retry(
        f"{BASE_URL}regions/{region_id}/forecasts", params={"date": str(day)}) or []


def run_start_time(run):
    """Run start time from the run's metadata, or (NaT, None) if it has none."""
    if "date" in run and "time" in run:
        return pd.to_datetime(f"{run['date']} {run['time']}", utc=True), "metadata date+time"
    for key in RUN_TIME_KEYS:
        if run.get(key):
            return pd.to_datetime(run[key], utc=True), f"metadata {key}"
    return pd.NaT, None


def find_site(region_id, forecast_id, lat, lon):
    """Nearest site to (lat, lon) within MAX_SITE_DIST_KM, as in fetch_water_level_data."""
    bbox = utils_runup.bounding_box(lat, lon, SEARCH_DISTANCE_M)
    params = {"siteLatitude": [f"gte_{bbox['min_lat']}", f"lte_{bbox['max_lat']}"],
              "siteLongitude": [f"gte_{bbox['min_lon']}", f"lte_{bbox['max_lon']}"]}
    sites = utils_runup.make_request_with_retry(
        f"{BASE_URL}regions/{region_id}/forecasts/{forecast_id}/sites?pageSize=100", params=params)
    if not sites:
        return None
    dist = [geodesic((lat, lon), (s["siteLatitude"], s["siteLongitude"])).kilometers for s in sites]
    i = int(np.argmin(dist))
    return sites[i]["id"] if dist[i] < MAX_SITE_DIST_KM else None


def fetch_run(region_id, region_name, run):
    """Water levels for one run as a DataFrame; cached as raw JSON in CACHE_DIR."""
    fid = run["id"]
    tag = SITE_ID if SITE_ID is not None else f"{LAT:.5f}_{LON:.5f}"
    # 2026-11-04: cache now in the {key: [values]} layout of fetch_water_level_data (was {"run", "site_id", "waterLevels"})
    cache = CACHE_DIR / f"{region_name.replace(' ', '_')}_{tag}_run{fid}.json"
    if cache.exists():
        water_level = json.loads(cache.read_text())
        site_id = SITE_ID if SITE_ID is not None else tag
    else:
        site_id = SITE_ID if SITE_ID is not None else find_site(region_id, fid, LAT, LON)
        if site_id is None:
            print(f"  run {fid}: no site within {MAX_SITE_DIST_KM} km, skipped")
            return None
        levels = utils_runup.make_request_with_retry(
            f"{BASE_URL}regions/{region_id}/forecasts/{fid}/sites/{site_id}/waterLevels")
        if not levels:
            return None
        water_level = to_dict_of_lists(levels)
        cache.write_text(json.dumps(water_level, indent=4))
    if not water_level or not water_level.get("dateTime"):
        return None

    df = pd.DataFrame(water_level)  # dict of equal-length lists -> one column per key
    df["valid_time"] = pd.to_datetime(df.pop("dateTime"), utc=True)
    run_time, source = run_start_time(run)
    if pd.isna(run_time):
        run_time, source = df["valid_time"].min(), "earliest valid time"
    df["forecast_id"], df["site_id"] = fid, site_id
    df["run_time"], df["run_time_source"] = run_time, source
    return df


def best_estimate(all_runs):
    """For each valid time keep the row with the smallest lead time (ties -> newest run)."""
    df = all_runs.assign(lead_h=(all_runs["valid_time"] - all_runs["run_time"]).dt.total_seconds() / 3600)
    if not INCLUDE_NEGATIVE_LEAD:
        df = df[df["lead_h"] >= 0]
    # one sort + drop_duplicates instead of a loop over valid times
    df = df.sort_values(["valid_time", "lead_h", "run_time"], ascending=[True, True, False])
    return df.drop_duplicates("valid_time", keep="first").reset_index(drop=True), df


def latlon_from_json(path):
    """lat/lon from products.json (as in compute_runup), or from a config JSON that has 'productsPath'."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and "productsPath" in data:      # site config file -> follow to products.json
        prod = Path(data["productsPath"])
        data = json.loads((prod if prod.suffix == ".json" else prod / "products.json").read_text())
    grid = data if isinstance(data, dict) else data[0]
    return float(grid["lat"]), float(grid["lon"])


def main():
    global LAT, LON
    apply_config_json(CONFIG_JSON)
    if SITE_ID is None and (LAT is None or LON is None):
        if PRODUCTS_JSON is None:
            raise ValueError("Set SITE_ID, LAT and LON, or PRODUCTS_JSON in CONFIG.")
        LAT, LON = latlon_from_json(PRODUCTS_JSON)
        print(f"Site location from {PRODUCTS_JSON}: lat {LAT:.5f}, lon {LON:.5f}")
    if SITE_ID is None:
        LON = ((LON + 180) % 360) - 180  # wrap 0..360 longitudes to -180..180
        if not (-90 <= LAT <= 90):
            raise ValueError(f"Latitude {LAT} out of range; check the order of lat/lon.")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    region_id, region_name = get_region(REGION_CHOICE)

    frames, no_runs = [], []
    for day in pd.date_range(START_DATE, END_DATE, freq="D").date:
        runs = list_runs(region_id, day)
        if not runs:
            no_runs.append(day)
            continue
        print(f"{day}: {len(runs)} run(s)")
        frames += [f for f in (fetch_run(region_id, region_name, r) for r in runs) if f is not None]
    if not frames:
        raise RuntimeError(f"No forecast data for {START_DATE} to {END_DATE}.")

    best, all_runs = best_estimate(pd.concat(frames, ignore_index=True))
    # 2026-11-04: JSON output in the fetch_water_level_data layout; CSV only if WRITE_CSV
    # OUT_BEST_CSV.parent.mkdir(parents=True, exist_ok=True)
    # best.to_csv(OUT_BEST_CSV, index=False)
    # all_runs.to_csv(OUT_ALL_CSV, index=False)
    stem = f"{region_name.replace(' ', '_')}_{SITE_ID if SITE_ID is not None else f'{LAT:.5f}_{LON:.5f}'}"
    out_best = Path(OUT_BEST_JSON or CACHE_DIR / f"{stem}_best_{START_DATE}_{END_DATE}.json")
    out_all = Path(OUT_ALL_JSON or CACHE_DIR / f"{stem}_allruns_{START_DATE}_{END_DATE}.json")
    out_best.parent.mkdir(parents=True, exist_ok=True)
    # 'dateTime' key restored so the file reads exactly like the daily files
    write_dict_of_lists(best.rename(columns={"valid_time": "dateTime"}), out_best)
    write_dict_of_lists(all_runs.rename(columns={"valid_time": "dateTime"}), out_all)
    if WRITE_CSV:
        best.to_csv(out_best.with_suffix(".csv"), index=False)
        all_runs.to_csv(out_all.with_suffix(".csv"), index=False)

    # --- short report: run timing, lead times, gaps
    print(f"\nDays with no runs: {no_runs or 'none'}")
    print("Run start time source:", best["run_time_source"].value_counts().to_dict())
    print(f"Runs per day (median): {all_runs.groupby(all_runs['run_time'].dt.date)['forecast_id'].nunique().median():.0f}")
    print("Lead time in best series (h):", best["lead_h"].describe()[["min", "50%", "max"]].round(1).to_dict())
    step = best["valid_time"].diff().median()
    gaps = best.loc[best["valid_time"].diff() > 1.5 * step, "valid_time"]
    print(f"Time step {step}; gaps: {len(gaps)}" + (f" (first at {gaps.iloc[0]})" if len(gaps) else ""))
    print(f"Saved {len(best)} rows to {out_best} and {len(all_runs)} rows to {out_all}")
    print(f'Add to config.json: "twlBestJson": "{out_best}"')


if __name__ == "__main__":
    main()
