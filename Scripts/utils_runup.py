


# utils_runup from Athina's shorescan code to get the TWL forecast data from the USGS TWL&CC viewer API based on coordinates and timestamp. 
# If any required parameter is missing, the function prompts for it interactively.

import json
import os
import time
from datetime import datetime
from math import cos, degrees, radians

import numpy as np
import pandas as pd
import requests

from geopy.distance import geodesic

from sklearn.linear_model import LinearRegression


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

import requests
import time


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
            retry_after = response.headers.get("X-Retry-After", "2")  # Default to 2 seconds if not set
            try:
                retry_after = float(retry_after)  # Convert the value to a float
            except ValueError:
                retry_after = 2  # In case the value cannot be converted, use a default value of 2 seconds
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
            print(f'Getting water level forecast for {region_name}, site ID {site_id}, timestamp {user_time.date()}')
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
