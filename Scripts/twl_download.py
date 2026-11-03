"""
twl_download.py

Author:  Chelsea A. Volpano (cvolpano@gmail.com)
Created: 2026-11-02
Model:   Generated with Claude Opus 5.5 (Anthropic), claude.ai

Summary
-------
Downloads EVERY forecast issued for a USGS/NOAA TWL&CC site over a date
range, not just the first one of each day. The API lists several forecasts
per date (e.g. issued 00:00, 06:00 and 12:00 UTC on 2024-12-14), so
fetching all of them shortens the lead times in the best-estimate series.

For each date:
  1. GET regions/{region}/forecasts?date=YYYY-MM-DD  -> all issues that day
  2. For each issue not already on disk:
     GET .../forecasts/{forecast_id}/sites/{site_id}/waterLevels
  3. Save as <Region>_<site>_<YYYY-MM-DD>T<HHMM>.json (issue time, UTC), in
     the same dict-of-lists layout utils_runup.py used.
Files from the old daily download (<Region>_<site>_<YYYY-MM-DD>.json) are
the 00:00 issue; they are recognised and not downloaded again.

A catalog of every forecast seen (id, issue time, status) is written to
<Region>_<site>_forecast_catalog.csv.

Adapted from fetch_water_level_data() in utils_runup.py (A. shorescan code).
API: https://coastal.er.usgs.gov/hurricanes/research/twlviewer/ (see "API
Documentation"). Forecast issue times are assumed to be UTC, matching the
UTC 'dateTime' values in the files.

Change log
----------
2026-11-02  Initial version.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://coastal.er.usgs.gov/hurricanes/research/twlviewer/api/"


def _get_json(session: requests.Session, url: str, params=None,
              max_tries: int = 5):
    """GET a URL and return its JSON, waiting and retrying on HTTP 429."""
    for _ in range(max_tries):
        r = session.get(url, params=params, timeout=60)
        if r.status_code == 429:  # rate limited: wait as the server asks
            wait = float(r.headers.get("X-Retry-After", 2) or 2)
            print(f"Rate limit hit; waiting {wait:.1f} s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Still rate limited after {max_tries} tries: {url}")


def _to_dict_of_lists(records: list[dict]) -> dict[str, list]:
    """Convert API rows to {column: [values]}, numbers as floats.

    Same layout and number handling as utils_runup.py, so old and new
    files are read identically by twl_json_to_timeseries.py.
    """
    out = {key: [] for key in records[0]}
    for row in records:
        for key, value in row.items():
            try:
                out[key].append(float(value))
            except (TypeError, ValueError):
                out[key].append(value)
    return out


def download_forecasts(start_date: str, end_date: str, region_choice: int,
                       site_id: int, save_folder: str | Path,
                       pause_s: float = 1.0) -> pd.DataFrame:
    """Download every forecast issued between two dates for one site.

    region_choice: 1-based position in the API region list (1 = Boston, MA).
    Returns the forecast catalog as a DataFrame (also saved as CSV).
    """
    save_folder = Path(save_folder)
    save_folder.mkdir(parents=True, exist_ok=True)

    # One Session reuses the same connection for every request, which is
    # faster than opening a new one each time with requests.get().
    with requests.Session() as session:
        region = _get_json(session, BASE_URL + "regions")[region_choice - 1]
        prefix = f"{region['fullName'].replace(' ', '_')}_{site_id}"
        print(f"Region: {region['fullName']} (id {region['id']}), "
              f"site {site_id}")

        catalog = []
        for day in pd.date_range(start_date, end_date, freq="D"):
            date = day.strftime("%Y-%m-%d")
            try:  # no 'time' parameter -> every issue on this date
                issues = _get_json(
                    session, f"{BASE_URL}regions/{region['id']}/forecasts",
                    params={"date": date})
            except (requests.RequestException, RuntimeError) as err:
                print(f"{date}: could not list forecasts ({err})")
                catalog.append({"date": date, "status": "list failed"})
                continue
            if not issues:
                print(f"{date}: no forecasts listed")
                catalog.append({"date": date, "status": "none issued"})

            for fc in sorted(issues, key=lambda f: f["time"]):
                hhmm = fc["time"].replace(":", "")[:4]
                path = save_folder / f"{prefix}_{date}T{hhmm}.json"
                old_daily = save_folder / f"{prefix}_{date}.json"
                entry = {"date": date, "time": fc["time"],
                         "forecast_id": str(fc["id"]),
                         "max_impact": fc.get("maxPredictedImpact"),
                         "file": path.name}

                if path.exists() or (hhmm == "0000" and old_daily.exists()):
                    entry["status"] = "on disk"
                    if not path.exists():
                        entry["file"] = old_daily.name
                    catalog.append(entry)
                    continue

                url = (f"{BASE_URL}regions/{region['id']}/forecasts/"
                       f"{fc['id']}/sites/{site_id}/waterLevels")
                try:
                    rows = _get_json(session, url)
                    if not rows:
                        raise ValueError("empty response")
                    path.write_text(json.dumps(_to_dict_of_lists(rows),
                                               indent=4))
                    entry["status"] = "downloaded"
                    print(f"{date} {fc['time']}: saved {path.name}")
                except (requests.RequestException, RuntimeError,
                        ValueError) as err:
                    entry["status"] = f"failed: {err}"
                    print(f"{date} {fc['time']}: failed ({err})")
                catalog.append(entry)
                time.sleep(pause_s)
            time.sleep(pause_s)

    catalog = pd.DataFrame(catalog).fillna("").astype(str)
    catalog_path = save_folder / f"{prefix}_forecast_catalog.csv"
    # Merge with any earlier catalog so re-runs keep a full record.
    if catalog_path.exists():
        old = pd.read_csv(catalog_path, dtype=str, keep_default_na=False)
        catalog = (pd.concat([old, catalog])
                   .drop_duplicates(["date", "time"], keep="last")
                   .sort_values(["date", "time"], ignore_index=True))
    catalog.to_csv(catalog_path, index=False)

    counts = catalog["status"].str.split(":").str[0].value_counts()
    print("\nSummary:", ", ".join(f"{k}: {v}" for k, v in counts.items()))
    return catalog
