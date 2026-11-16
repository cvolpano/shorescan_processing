"""
utils_runup.py

This module provides functions for computing runup statistics and getting TWL from the USGS TWL&CC forecast.

"""

import json
import os
import time
from datetime import datetime
from math import cos, degrees, radians

import numpy as np
import pandas as pd
import requests
import scipy.io
import scipy.signal
from geopy.distance import geodesic
from scipy.signal import find_peaks


## ----------- TWL forecast -----------
def bounding_box(lat, lon, distance_m):
    """
    Calculate the bounding box for a given lat, lon, and distance in meters.
    :param lat: Latitude of the center point (in decimal degrees).
    :param lon: Longitude of the center point (in decimal degrees).
    :param distance_m: Distance in meters for the bounding box.
    :return: Dictionary with min_lat, max_lat, min_lon, max_lon.
    """
    # Earth's radius in meters
    R = 6378137

    # Offsets in radians
    d_lat = distance_m / R
    d_lon = distance_m / (R * cos(radians(lat)))

    # Calculate the bounding box
    min_lat = lat - degrees(d_lat)
    max_lat = lat + degrees(d_lat)
    min_lon = lon - degrees(d_lon)
    max_lon = lon + degrees(d_lon)

    return {
        "min_lat": min_lat,
        "max_lat": max_lat,
        "min_lon": min_lon,
        "max_lon": max_lon
    }

def get_valid_latitude():
    """
    Prompt the user to enter a valid latitude value between -90 and 90.
    :return: A valid latitude value as a float.
    """
    while True:
        try:
            lat = float(input("Enter latitude: "))
            if -90 <= lat <= 90:
                return lat
            else:
                print("Invalid latitude. Please enter a value between -90 and 90.")
        except ValueError:
            print("Invalid input. Please enter a numeric value for latitude.")

def get_valid_longitude():
    """
    Prompt the user to enter a valid longitude value between -180 and 180.
    :return: A valid longitude value as a float.
    """
    while True:
        try:
            lon = float(input("Enter longitude: "))
            if -180 <= lon <= 180:
                return lon
            else:
                print("Invalid longitude. Please enter a value between -180 and 180.")
        except ValueError:
            print("Invalid input. Please enter a numeric value for longitude.")

def validate_lat_lon(lat, lon):
    """
    Validate that the provided lat and lon are within valid ranges.
    :param lat: Latitude value.
    :param lon: Longitude value.
    :return: Validated lat and lon.
    """
    if lat is not None:
        if not (-90 <= lat <= 90):
            raise ValueError("Latitude must be between -90 and 90.")
    if lon is not None:
        if not (-180 <= lon <= 180):
            raise ValueError("Longitude must be between -180 and 180.")
    return lat, lon

def make_request_with_retry(url, params=None):
    """
    Make a GET request and handle rate limiting.
    If the API rate limit is exceeded (HTTP 429), the function will wait for the duration provided
    in the 'X-Retry-After' header before retrying the request.
    """
    while True:
        response = requests.get(url, params=params)
        if response.status_code == 429:
            # Get the retry delay from the X-Retry-After header
            retry_after = response.headers.get("X-Retry-After", "1")  # Default to 1 second if not set
            try:
                retry_after = float(retry_after)  # Convert the value to a float
            except ValueError:
                retry_after = 1  # In case the value cannot be converted, use a default value of 1 second
            print(f"Rate limit exceeded. Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
        else:
            response.raise_for_status()  # If status is not 429, raise the usual exceptions
            return response.json()

def fetch_water_level_data(region_choice=None, site_id=None, lat=None, lon=None, timestamp=None,  distance_m=500,  save_folder=None):
    """
    Fetch water level data from the USGS TWL&CC viewer API based on coordinates and timestamp.
    If any required parameter is missing, the function prompts for it interactively.
    :param lat: Latitude of the location (optional if site_id is provided).
    :param lon: Longitude of the location (optional if site_id is provided).
    :param timestamp: Timestamp in "YYYY-MM-DD HH:MM:SS" format.
    :param region_choice: The selected region index.
    :param distance_m: Search radius in meters (default: 500).
    :param site_id: The site ID (optional if lat/lon are provided).
    :param save_folder: The folder where the data should be saved (optional).
    :return: Dictionary of water level data.
    """
    BASE_URL = "https://coastal.er.usgs.gov/hurricanes/research/twlviewer/api/"

    try:
        # Regions
        regions_url = f"{BASE_URL}regions"
        regions = make_request_with_retry(regions_url)
        if region_choice is None:
            print("Available Regions:")
            for i, region in enumerate(regions):
                print(f"{i + 1}: {region['fullName']}")
            region_choice = int(input("Select a region by number: "))
            if region_choice < 1 or region_choice > len(regions):
                raise ValueError("Invalid region choice.")
        selected_region = regions[region_choice - 1]
        region_id = selected_region['id']
        region_name = selected_region['fullName']

        # Timestamp
        if timestamp is None:
            timestamp = input("Enter timestamp (YYYY-MM-DD): ")
        user_time = datetime.strptime(timestamp, "%Y-%m-%d")

        if site_id is not None:
            file_name = f"{region_name.replace(' ', '_')}_{site_id}_{user_time.date()}.json"
            file_path = os.path.join(save_folder, file_name)
        
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                water_level = json.load(f)
        else:

            # Forecasts
            forecasts_url = f"{BASE_URL}regions/{region_id}/forecasts?date={user_time.date()}&time=00:00:00"
            forecasts = make_request_with_retry(forecasts_url)
            forecast_id = forecasts[0]['id']

            # Site ID
            if site_id is None:
                # Prompt for lat, lon, and timestamp if not provided
                if lat is None:
                    lat = get_valid_latitude()
                if lon is None:
                    lon = get_valid_longitude()
                
                bbox = bounding_box(lat, lon, distance_m)

                # Validate lat and lon
                lat, lon = validate_lat_lon(lat, lon)
                params = {
                    "siteLatitude": [f"gte_{bbox['min_lat']}", f"lte_{bbox['max_lat']}"],
                    "siteLongitude": [f"gte_{bbox['min_lon']}", f"lte_{bbox['max_lon']}"],
                }

                # Retrieve site data
                sites_url = f"{BASE_URL}regions/{region_id}/forecasts/{forecast_id}/sites?pageSize=100"
                sites = make_request_with_retry(sites_url, params=params)

                # Find the closest site
                closest_site = None
                min_distance = 20  # Minimum distance threshold in kilometers
                for site in sites:
                    site_coords = (site['siteLatitude'], site['siteLongitude'])
                    distance = geodesic((lat, lon), site_coords).kilometers
                    if distance < min_distance:
                        closest_site = site
                        min_distance = distance

                if not closest_site:
                    raise ValueError("No suitable site found near the provided coordinates.")

                site_id = closest_site['id']
            
                    # Determine file save path
            if save_folder is None:
                save_folder = "data_wl"
            
            os.makedirs(save_folder, exist_ok=True)

            file_name = f"{region_name.replace(' ', '_')}_{site_id}_{user_time.date()}.json"
            file_path = os.path.join(save_folder, file_name)
            
            print(file_path)

            # Fetch file
            water_levels_url = f"{BASE_URL}regions/{region_id}/forecasts/{forecast_id}/sites/{site_id}/waterLevels"
            data = make_request_with_retry(water_levels_url)
            water_level = {key: [] for key in data[0].keys()}

            for entry in data:
                for key, value in entry.items():
                    try:
                        water_level[key].append(float(value))
                    except ValueError:
                        water_level[key].append(value)

            # Save the data to the file
            with open(file_path, 'w') as json_file:
                json.dump(water_level, json_file, indent=4)

            print(f"Water level data saved to {file_path}")

        water_level['dateTime'] = pd.to_datetime(water_level['dateTime'])

        return water_level
    except Exception as e:
        print(f"Error processing {timestamp}: {e}")

## ----------- Runup statistics -----------
def runupStatistics_CHI(eta, t_sec, nperseg, f_lims=np.array([0.004, 0.04, 0.35]), grd=None):
    """
    Computes statistical parameters of runup from a water level time series.

    :param eta (ndarray): Runup time series (tide should be subtracted).
    :param t_sec (ndarray): Time array in seconds corresponding to eta.
    :param nperseg (int): Window length for spectral analysis.
    :param f_lims (ndarray): Array of frequency limits [min IG, IG/SS split, max SS] (default: [0.004, 0.04, 0.35]).
    :param grd (dict, optional): Bathymetric data along transect. Should contain:
        - 'x': Local cross-shore coordinates (in meters),
        - 'z': Elevation (in meters).

    :return: 
    dict: Dictionary of computed runup statistics, including:
        - "setup": Mean water level.
        - "eta2": 2% exceedance level from full time series.
        - "R2": 2% exceedance level from runup peaks.
        - "S2": Swash height (R2 - setup).
        - "Ts", "Tr": Swash and runup periods (time/ # of peaks).
        - "Tp": Peak wave period.
        - "Ss": Significant swash (4 * sqrt(var(eta))).
        - "Ssin": Significant incident swash.
        - "Ssig": Significant infragravity swash.
        - "Sst": Total significant swash.
        - "f", "S": Frequency array and spectral density.
        - "beta_S2006": Beach slope from ±2 std elevation band (if grd provided).
        - "beta_Z": Beach slope from total elevation range (if grd provided).

    Notes:
        - Modified from Dave's version of runupFullStats... and subroutines.
        - Hardcoded:
            - nbins = 20; number of bins for calculating CDF
            - MinPeakProminence = np.std(eta)/3; Minimum prominence for find peaks
            - distance=3; minimum distance between peaks
    """
    
    print('computing runup stats')
    RUstats = {
        "R2": [],
        "Tr": [],
        "S2": [],
        "Ts": [],
        "setup": [],
        "eta2": [],
        "f": [],
        "S": [],
        "Tp": [],
        "Ss": [],
        "Ssin": [],
        "Ssig": [],
        "Sst": [],
        "beta_S2006":[],
        "beta_Z": []
    }

    # sample rate
    dt = np.mean(np.diff(t_sec))

    # Minimum prominence for find peaks
    MinPeakProminence = np.std(eta) / 3

    # Number of bins for cummulative distribution function
    nbins = 20

    ## Setup
    setup = np.mean(eta)
    RUstats["setup"] = setup

    # 2# exceedence value of eta i.e. full time series not peaks
    # Do this using CDF.
    # Define bins.
    c, binCenters = CDF_by_bins(eta, nbins)
    id = np.argmin(np.abs(c - 0.98))
    eta2 = np.interp(0.98, c, binCenters)
    RUstats["eta2"] = eta2

    ## Runup and swash
    # Swash is defined as the range of values between successive zero
    # crossings.
    # find runup peaks
    peaks, _ = find_peaks(eta, prominence=MinPeakProminence, distance=3)
    # plt.plot(eta)
    # plt.plot(peaks, eta[peaks], "x")
    # plt.xlim([0,100])
    # plt.show()

    # 2# exceedence value runup and swash
    R = eta[peaks]
    c, binCenters = CDF_by_bins(R, nbins)
    R2 = np.interp(0.98, c, binCenters)
    # 2% excceedence
    RUstats["R2"] = R2
    RUstats["S2"] = R2 - np.mean(eta)

    # swash period (same as runup period?!)
    RUstats["Ts"] = t_sec[-1] / len(peaks)
    RUstats["Tr"] = t_sec[-1] / len(peaks)

    # Power Spectral Density
    f, S = scipy.signal.welch(
        eta, fs=1 / dt, window="hann", nperseg=nperseg, noverlap=nperseg * (3 / 4)
    )
    RUstats["f"] = f
    RUstats["S"] = S

    # Peak frequency
    fp = f[np.argmax(S)]
    # Peak period.
    Tp = 1 / fp
    RUstats["Tp"] = Tp

    # significant swash = Ss
    Ss = 4 * np.sqrt(np.std(eta))
    RUstats["Ss"] = Ss
    # incident and IG band significant swash = Ssin & Ssig
    df = np.mean(np.diff(f))

    inc = (f >= f_lims[1]) & (f < f_lims[2])
    ig = (f >= f_lims[0]) & (f < f_lims[1])
    # incident
    varin = sum(S[inc]) * df
    # IG
    varig = sum(S[ig]) * df
    # Total
    vartot = sum(S[ig | inc]) * df

    RUstats["Ssin"] = 4 * np.sqrt(varin)
    RUstats["Ssig"] = 4 * np.sqrt(varig)
    RUstats["Sst"] = 4 * np.sqrt(vartot)


    if grd is not None:
        stdEta = np.std(eta)

        maxEta = setup + 2 * stdEta
        minEta = setup - 2 * stdEta
        botRange = np.where((grd['z'] >= minEta) & (grd['z'] <= maxEta))[0]
        fitvars = np.polyfit(grd['x'][botRange], grd['z'][botRange], 1)
        beta = fitvars[0]
        RUstats["beta_S2006"] = beta

        maxEta = np.max(eta)
        minEta = np.min(eta)
        botRange = np.where((grd['z'] >= minEta) & (grd['z'] <= maxEta))[0]
        fitvars = np.polyfit(grd['x'][botRange], grd['z'][botRange], 1)
        beta = fitvars[0]
        RUstats["beta_Z"] = beta

    return RUstats

def CDF_by_bins(x, nbins):
    """
    Computes the empirical cumulative distribution function (CDF) of a dataset using histogram binning.

    :param x (ndarray): Input 1D array of data.
    :param nbins (int): Number of bins to use in histogram.

    :return: 
    - c (ndarray): Cumulative distribution values.
    - binCenters (ndarray): Centers of the bins used for the CDF.
    """
    # Do this using CDF.
    # Define bins.
    binWidth = (np.max(x) - np.min(x)) / nbins
    bins = np.arange(np.min(x), np.max(x), binWidth)
    binCenters = bins + 0.5 * binWidth
    c = np.zeros(len(bins))  # cdf
    for ii in np.arange(1, len(bins)).reshape(-1):
        c[ii] = sum(x < bins[ii]) / len(x)
    return c, binCenters

def runup_stats_CHI(Ibp, exc_value=None):
    """
    Computes the 2% runup (R2) from instantaneous beach position using the zero-downcrossing method.

    :param Ibp (xarray.DataArray): Instantaneous vertical beach position (in meters relative to still water level).
    :param exc_value (float, optional): Outlier threshold (exclude values with abs(Ibp) > exc_value). Default is None.

    :return: 
    xarray.DataArray: Scalar containing the 2% runup value (R2), with units in meters and metadata attributes.

    @author: rfonsecadasilva
    """
    if exc_value:
        bad_data = (
            xr.apply_ufunc(np.isnan, Ibp.where(lambda x: np.abs(x) > exc_value)).sum()
            / Ibp.size
            * 100
        ).values.item()
        if bad_data != 100:
            print(f"{100-bad_data:.1f} % of runup data is corrupted")
        Ibp = Ibp.where(lambda x: np.abs(x) < exc_value, drop=True)
    time_cross = Ibp.where(
        ((Ibp.shift(t=1) - Ibp.mean(dim="t")) * (Ibp - Ibp.mean(dim="t")) < 0)
        & (Ibp - Ibp.mean(dim="t") > 0),
        drop=True,
    )  # calculate crossing points for zero-downcrossing on swash

    R2 = (
        Ibp.groupby_bins("t", time_cross.t).max(dim="t").quantile(0.98).values
    )  # calculate 2% runup,dim="t_bins"
    print(R2)
    R2 = xr.DataArray(R2, dims=())

    R2.attrs["standard_name"], R2.attrs["long_name"], R2.attrs["units"] = (
        "2% runup",
        "2% runup",
        "m",
    )
    return R2
