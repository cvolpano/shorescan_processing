'''
utils_runup.py
This module provides functions for defining the U,V coordinates for an ARGUS-style camera and extracting individual transect images from a ras image.

Dependencies:
-------------
- os
- json
- yaml
- opencv (cv2)
- utm
- glob
- datetime
- pandas
- numpy
- pathlib
- tkinter
- plotly
- sklearn

'''
# Custom Modules
from RunUpTimeseriesFunctions_CHI import *
from utils_CIRN import *

# External Libraries
import os
import json
import yaml
import cv2
import utm
import glob
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pathlib import Path

from tkinter import Tk, filedialog
from tkinter.filedialog import askdirectory
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression


from tkinter import Tk, filedialog, messagebox
## ------------------- timestack runup stuff -------------------

def get_runup(config = None, timestackDir = None, overlayDir = None, site_settingsPath = None):
    """
    Processes extracted runup data, computes shoreline elevations, runup statistics and saves to netCDF.

    :param config: (dict, optional) Configuration dictionary containing paths and values.
    :param timestackDir: (str, optional) Path to the timestacks folder.
    :param overlayDir: (str, optional) Output folder for overlays (default: 'timestackDir/overlays').
    :param site_settingsPath: (str, optional) Path to site settings file.

    :return: None
    """
    config = config or {}  # Ensure config is always a dictionary

    timestackDir = config.get("timestackDir", timestackDir)
    overlayDir = config.get("overlayDir", overlayDir)
    site_settingsPath = config.get("site_settingsPath", site_settingsPath)

    # Ensure timestackDir is set
    if not timestackDir:
        raise ValueError("A timestack directory must be provided either as an argument or in the config.")
    overlayDir = overlayDir or os.path.join(timestackDir, "overlays")

    datastore = ImageDatastore(timestackDir)
    datastore.load_images()
    # Remove all non-RAS image types
    for img_type in ['bright', 'dark', 'var', 'timex', 'snap']:
        datastore.remove_images_by_type(img_type)

    # Filter unmatched images and extract metadata
    datastore.filter_unmatched_images(overlayDir)
    datastore.extract_metadata()
    datastore.image_stats()

    for site, cameras in datastore.images.items():
        for camera, years in cameras.items():
            for year, months in years.items():
                for month, days in months.items():
                    for day, times in days.items():
                        for time, images_by_type in times.items():
                            for image_type, images in images_by_type.items():
                                for img in images:
                                    print(img['path'])

                                    # Extract metadata
                                    metadata = img.get('metadata', {})
                                    
                                    # Extract 'extrinsics' and 'intrinsics'
                                    extrinsics = metadata.get("extrinsics", None)
                                    intrinsics = metadata.get("intrinsics", None)
                                    
                                    # Extract 'transect' and its 'U' and 'V'
                                    transect = metadata.get("transect", {})
                                    U = np.array(transect.get("U", []))
                                    V = np.array(transect.get("V", []))
                                    transect_date = transect.get("transect_date", [])

                                    # Get corresponding runup data
                                    runup_file = os.path.join(overlayDir, f'runup_{Path(img["path"]).stem}.txt')
                                    if os.path.isfile(runup_file):
                                        runup_data = np.genfromtxt(runup_file, delimiter=None)  # Auto-detect delimiter
                                        # Skip files that are **entirely NaN**
                                        if np.all(np.isnan(runup_data)):
                                            print(f"Skipping {runup_file} (all values are NaN)")
                                            continue  # Don't plot this file
                                        else:
                                            h_runup_id = np.round(len(U) - runup_data).astype(int)  
                                    else:
                                        print(f"No runup data exists for {Path(img['path']).stem}. Please rerun extract_runup.")
                                        continue

                                    # Extract date and transect number
                                    fileName = Path(img['path']).stem.split('.')
                                    date = fileName[0]
                                    try:
                                        transectNum = fileName[8].split('_')[1][-1]
                                    except IndexError:
                                        print(f"Could not determine transect number for {img['path']}")
                                        continue

                                    # Get DEM and compute shoreline elevation
                                    DEM = 0#get_DEM(date = date, site = site, camNum = camera, transectNum = transectNum)
                                    xyz = np.zeros((3,3))#dist_uv_to_xyz(intrinsics, extrinsics, np.column_stack((U, V)), 'z', DEM['z'])
                                    Hrunup = U#xyz[h_runup_id, 0]
                                    Zrunup = V#xyz[h_runup_id, 2]
                                    
                                    # Store results in netCDF
                                    sites = get_site_settings(file_path = site_settingsPath)
                                    site_dict = sites.get(site, {})
                                    if "siteInfo" not in site_dict:
                                        print(f"Missing site info for {site}. Skipping.")
                                        continue
                                    site_dict["siteInfo"]["camNum"] = camera
                                    site_dict["siteInfo"]["rNumber"] = transectNum
                                    write_netCDF(site_dict, img['path'], U, V, transect_date, xyz,  Hrunup, Zrunup)
                                
    return 

def get_DEM(date, site, camNum, transectNum):
    """
     df = pd.read_csv('Marconi 2024-10-23.csv')
    t = np.linspace(0, 1, len(df))
    t_fine = np.linspace(0, 1, 50)
    E_fine = interp1d(t, df['Easting'], kind='cubic')(t_fine)
    N_fine = interp1d(t, df['Northing'], kind='cubic')(t_fine)
    Z_fine = interp1d(t, df['Elevation'], kind='cubic')(t_fine)
    
    F = griddata((E_fine, N_fine), Z_fine, (xyz[:, 0], xyz[:, 1]), method='linear')
    DEM_z = pd.Series(F).rolling(window=25, win_type='gaussian', center=True).mean(std=2).values
    """
    return




## ------------------- Save data --------------------
def write_netCDF(site, img_path, U, V, transect_date, xyz, Hrunup, Zrunup):
        
    #history = f"{datetime.now(timezone.utc).isoformat()} Using Python version {sys.version}, netCDF4 version {nc.__version__}, NumPy version {np.__version__}"

    # ----------------- U,V -----------------
    U = U
    V = V

    # ----------------- Camera -----------------
    ECamera = float(yamlData['x'])
    NCamera = float(yamlData['y'])
    zCamera = float(yamlData['z'])

    # ----------------- UTM -----------------
    UTM_E = xyz[:,0]
    UTM_N = xyz[:,1]


    # ----------------- Lat/Lon -----------------
    lat, lon = utm.to_latlon(UTM_E, UTM_N, int(site["siteInfo"]["utmZone"][0:2]), site["siteInfo"]["utmZone"][2:3])

    # ----------------- z -----------------
    z = xyz[:,2]

    # ----------------- X,Y -----------------
    X = U
    Y = V
    # ----------------- Time  -----------------
    t_sec = np.around(np.arange(0, sample_period_length*60, 1/sample_frequency_Hz)[:RAW.shape[0]], decimals=3) # timeseries in seconds
    T = np.array([fileDatetime + timedelta(seconds = t) for t in t_sec])

    # ----------------- Runup -----------------
    Hrunup = np.array(Hrunup)
    Zrunup = np.array(Zrunup)

    # ----------------- TWL stats -----------------
    # window length with 8 windows
    #window_length = np.floor(len(twl) / 8).astype(int) - 1
    #window_length = window_length.item()
    nperseg = 1 #<< window_length.bit_length() # next power of two for length
    
    
    try:
        TWLstats = runupStatistics_CHI(Zrunup, t_sec, nperseg, site["sampling"]["freqLimits"][1])
    except Exception as e:
        print(f"Error running runup(): {e}")  # Print error message
        TWLstats = {}  # Fallback to an empty dictionary to prevent crashes


    return

def load_json_file(data_filepath=None):
    """
    Load data from a JSON file. Either prompt the user to select the file or use the provided filepath.
    :param data_filepath: Optional path to the JSON file. If not provided, prompt user to select.
    :return: Parsed data from the JSON file.
    """
    if data_filepath:
        # Use the provided file path
        if not os.path.exists(data_filepath):
            print(f"File does not exist: {data_filepath}")
            return None
        with open(data_filepath, 'r') as file:
            data = json.load(file)
        return data
    else:
        # Prompt user to select a file
        root = Tk()
        root.withdraw()  # Hide the Tkinter root window

        # Open file dialog to select a file
        data_filepath = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])

        if not data_filepath:
            print("No file selected.")
            return None

        # Load and return the data from the JSON file
        with open(data_filepath, 'r') as file:
            data = json.load(file)
        return data, data_filepath

def select_variables_for_plot(data, x_variable=None, y_variables=None):
    """
    Prompt the user to select variables from the loaded JSON data for plotting.
    :param data: The parsed JSON data.
    :param x_variable: Optional X-axis variable provided as argument.
    :param y_variables: Optional list of Y-axis variables provided as argument.
    :return: The selected variables for X and Y axes.
    """
    # Extract variable names from the data keys
    if not data:
        print("No data available.")
        return None, None

    variables = list(data.keys())

    if x_variable is None:
        print("\nAvailable Variables:")
        for i, var in enumerate(variables, 1):
            print(f"{i}: {var}")
        
        # Prompt the user to select the X-axis variable
        x_choice = int(input(f"Select the X-axis variable (1-{len(variables)}): ")) - 1

        # Check for valid X-axis choice
        if x_choice not in range(len(variables)):
            print("Invalid choice for X-axis. Please select a valid index.")
            return None, None

        x_variable = variables[x_choice]

    # If y_variables is not provided, prompt for Y variable selection
    if y_variables is None:
        print(f"Select one or more Y-axis variables (comma-separated, e.g., 1,3,5): ")
        y_choices = input(f"Select Y-axis variables (1-{len(variables)}): ").split(',')

        # Convert Y choices to indices and validate
        y_variables = []
        for choice in y_choices:
            try:
                index = int(choice.strip()) - 1
                if index in range(len(variables)):
                    y_variables.append(variables[index])
                else:
                    print(f"Invalid Y-axis choice: {choice}")
            except ValueError:
                print(f"Invalid input: {choice}. Skipping.")

        if not y_variables:
            print("No valid Y-axis variables selected.")
            return None, None

    return x_variable, y_variables

def plot_line_with_dots_plotly(data, x_variable, y_variables, file_name, save_path):
    """
    Create interactive line plots with dots for the selected X variable and multiple Y variables using Plotly.
    :param data: The parsed JSON data.
    :param x_variable: The variable to be used for the X-axis.
    :param y_variables: The list of variables to be used for the Y-axis.
    :param file_name: The file name to be included in the title.
    :param save_path: The path where the PNG file should be saved.
    """
    # Convert the data into a format suitable for Plotly (Pandas DataFrame)
    df = pd.DataFrame(data)

    # Create a Plotly line plot with markers for each Y variable
    fig = px.line(df, x=x_variable, y=y_variables, title=f"File: {file_name}: {x_variable} vs Y Variables", markers=True)

    # Update layout for better readability
    fig.update_layout(
        title=f"File: {file_name}: {x_variable} vs Y Variables",
        xaxis_title=x_variable,
        yaxis_title="Y Variables",
        template="plotly",
        legend_title="Y Variables",
    )
    
    # Save the plot as a PNG file in the same directory as the input JSON file
    fig.write_image(save_path, format = 'png')

    # Show the plot
    fig.show()

def plot_from_json(x_variable=None, y_variables=None, data_filepath=None):
    """
    Main function that integrates the file loading, variable selection, and plotting.
    If arguments are not provided, the user is prompted to input them.
    :param x_variable: Optional X-axis variable to pass directly.
    :param y_variables: Optional list of Y-axis variables to pass directly.
    :param data_filepath: Optional file path to the JSON data. If not provided, user is prompted.
    """
    data, data_filepath = load_json_file(data_filepath)

    if data is None:
        return

    # Adjust the structure to match 'water_level' which is a dictionary of lists
    water_level = data

    # Get file name from file path
    file_name = os.path.basename(data_filepath) if data_filepath else 'Unknown File'
    # Remove '.json' from the file name and add '.png'
    save_file_name = file_name.replace('.json', '.png') 
    # Get the directory of the input file for saving the PNG file
    save_directory = os.path.dirname(data_filepath) if data_filepath else os.getcwd()
    save_path = os.path.join(save_directory, save_file_name)
    print(f'save_path:{save_path}')
    # Select variables for plotting (either from arguments or interactively)
    x_variable, y_variables = select_variables_for_plot(water_level, x_variable, y_variables)

    if x_variable and y_variables:
        plot_line_with_dots_plotly(water_level, x_variable, y_variables, file_name, save_path)
