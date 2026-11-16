import sys

if 'CODES' not in sys.path:
    sys.path.append('CODES')

from ImageHandler import ImageDatastore, ImageDatastore

datastore = ImageDatastore(configPath = 'config.json')
datastore.keep_images_by_type([ 'bright'])
datastore.image_stats()
datastore.apply_to_all_images('rectify_image', dem_flag = True)
datastore.process_shorelines(make_plots=False, save_flag = True)
datastore.merge_images()


datastore_timestack = ImageDatastore(configPath = config)
datastore_timestack.remove_images_by_type(['snap', 'timex', 'var', 'bright', 'dark'])
datastore_timestack.image_stats()
datastore_timestack.get_runup_from_timestacks(segformer_flag=True, save_flag=True)







import xarray as xr
import numpy as np
import rioxarray
import rasterio
c1={}
c1['shoreline'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c1.bright.nc')
c1['t2'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c1.ras_transect2.nc')
c1['t3'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c1.ras_transect3.nc')
c1['t4'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c1.ras_transect4.nc')
c1['t5'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c1.ras_transect5.nc')
c1['t6'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c1.ras_transect6.nc')

c2 = {}
c2['shoreline'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c2.bright.nc')
c2['t0'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c2.ras_transect0.nc')
c2['t1'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c2.ras_transect1.nc')
c2['t2'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c2.ras_transect2.nc')
c2['t3'] = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.c2.ras_transect3.nc')

rec_image = xr.open_dataset('DATA/DATA/results/netcdf/1729620000.Tue.Oct.22_18_00_00.GMT.2024.CACO03.bright_merged.nc')
demPath = '/mnt/c/Users/alange/Desktop/DATA/CODES/GitHub/ShoreScan/ShoreScan_clean_example/DATA/DATA/DEM/2024-024-FA_10_Marconi_YSMP_Ortho_5cm.tif'
with rasterio.open(demPath) as src:
    red = src.read(1)  # First band, typically Red
    green = src.read(2)  # Second band, typically Green
    blue = src.read(3)  # Third band, typically Blue
    bounds = src.bounds

rgb = np.stack([red, green, blue], axis=-1)
rgb = (255 * (rgb / np.max(rgb))).astype(np.uint8)

#demPath = '/mnt/c/Users/alange/Desktop/DATA/CODES/GitHub/ShoreScan/ShoreScan_clean_example/DATA/DATA/DEM/2024-024-FA_10_Marconi_YSMP_DSM_25cm.tif'
#dem = rioxarray.open_rasterio(demPath, masked=True)
#x = dem['x'].values
#y = np.flipud(dem['y'].values)
#X,Y=np.meshgrid(x,y)
#z = np.flipud(np.squeeze(dem.values))





fig, axs = plt.subplots(1, 2, figsize=(14, 7))  # 1 row, 2 columns

# --- Plot for c2 ---
axs[0].imshow(c2['shoreline']['I'], origin='upper')
axs[0].scatter(c2['t0']['U_transect'], c2['t0']['V_transect'], label='t0', color = 'red')
axs[0].scatter(c2['t1']['U_transect'], c2['t1']['V_transect'], label='t1', color = 'blue')
axs[0].scatter(c2['t2']['U_transect'], c2['t2']['V_transect'], label='t2', color = 'green')
axs[0].scatter(c2['t3']['U_transect'], c2['t3']['V_transect'], label='t3', color = 'black')
axs[0].set_title("c2 Shoreline + Transects")
axs[0].legend()
axs[0].axis('off')

# --- Plot for c1 ---
axs[1].imshow(c1['shoreline']['I'], origin='upper')
axs[1].scatter(c1['t2']['U_transect'], c1['t2']['V_transect'], label='t2', color = 'green')
axs[1].scatter(c1['t3']['U_transect'], c1['t3']['V_transect'], label='t3', color = 'black')
axs[1].scatter(c1['t4']['U_transect'], c1['t4']['V_transect'], label='t4')
axs[1].scatter(c1['t5']['U_transect'], c1['t5']['V_transect'], label='t5')
axs[1].scatter(c1['t6']['U_transect'], c1['t6']['V_transect'], label='t6')
axs[1].set_title("c1 Shoreline + Transects")
axs[1].legend()
axs[1].axis('off')

plt.tight_layout()
plt.show()





transects = [('t0', c2), ('t1', c2), ('t2', c2), ('t3', c1), ('t4', c1), ('t5', c1), ('t6', c1)]

yvals = []
twl_profiles = []

# Collecting data
for tkey, source in transects:
    y = source[tkey]['localY_transect'][0]
    twl = source[tkey]['TWL']
    yvals.append(y)
    twl_profiles.append(twl)

twl_profiles = np.array(twl_profiles, dtype=object)






import matplotlib.pyplot as plt
import numpy as np

num_columns = np.shape(twl_profiles)[1]

# Compute the mean and 2%/20%/80%/98% levels for each column
mean_values = np.median(twl_profiles, axis=0)
percentile_2 = np.percentile(twl_profiles, 2, axis=0).astype(np.float64)
percentile_25 = np.percentile(twl_profiles, 25, axis=0).astype(np.float64)
percentile_75 = np.percentile(twl_profiles, 75, axis=0).astype(np.float64)
percentile_98 = np.percentile(twl_profiles, 98, axis=0).astype(np.float64)

# Ensure percentiles are finite by masking any invalid values (e.g., NaNs or infs)
percentile_2 = np.ma.masked_invalid(percentile_2)
percentile_25 = np.ma.masked_invalid(percentile_25)
percentile_75 = np.ma.masked_invalid(percentile_75)
percentile_98 = np.ma.masked_invalid(percentile_98)

# Create a larger figure with adjusted spacing for better visibility
plt.figure(figsize=(20, 6))  # Increase the width to accommodate 1200 columns

# Shade between 2% and 98% percentiles
plt.fill_between(np.arange(num_columns), percentile_2, percentile_98, color='lightblue', alpha=1, label='2%-98% Exceedance')

# Shade between 20% and 80% percentiles
plt.fill_between(np.arange(num_columns), percentile_25, percentile_75, color='blue', alpha=0.3, label='25%-75% Exceedance')

# Plot the mean line across all columns
plt.plot(mean_values, color='blue', label='Median', linewidth=2)


# Highlight outliers: values smaller than the 2% percentile and greater than the 98% percentile are considered outliers
outliers_lower = np.where(twl_profiles < percentile_2, twl_profiles, np.nan).T # Mask values below the 2nd percentile
outliers_upper = np.where(twl_profiles > percentile_98, twl_profiles, np.nan).T  # Mask values above the 98th percentile

outliers_x = np.arange(num_columns)
for i in range(twl_profiles.shape[1]):
    plt.scatter(outliers_x, outliers_lower[:,1], c='black', s=10)
    plt.scatter(outliers_x, outliers_upper[:,1], c='black', s=10)

# Set labels and title
plt.xlabel('Time')
plt.ylabel('TWL Elevation (NAVD88m)')
plt.title('TWL Profiles ')

# Add a legend
plt.legend()

# Display the plot
plt.tight_layout()
plt.show()







import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.collections import LineCollection
import numpy as np

transects = [('t0', c2), ('t1', c2), ('t2', c2), ('t3', c1), ('t4', c1), ('t5', c1), ('t6', c1)]

every_count = 1
with_timeseries = True
animate = False  # Toggle this to True/False for animation
save_gif = False  # Toggle this to save

yvals = []
twl_profiles = []

# Collecting data
for tkey, source in transects:
    y = source[tkey]['localY_transect'][0]
    twl = source[tkey]['TWL']
    yvals.append(y)
    twl_profiles.append(twl)

twl_profiles = np.array(twl_profiles, dtype=object)

# Get the min and max TWL values
vmin = np.min([np.min(p) for p in twl_profiles])
vmax = np.max([np.max(p) for p in twl_profiles])

fig, ax = plt.subplots(figsize=(10, 6))

# Scatter points
sc = []
for yval, twl in zip(yvals, twl_profiles):
    s = ax.scatter(np.full_like(twl, yval), twl, c=twl, cmap='gist_earth', vmin=vmin, vmax=vmax,
                   s=20, edgecolors='black', linewidth=0.4)
    sc.append(s)

# Colorbar always (from first scatter)
cbar = plt.colorbar(sc[0], ax=ax, label='TWL (m)')

# Labels and grid
ax.set_xlabel("Local Y (Transect Position)")
ax.set_ylabel("TWL Elevation (m)")
ax.grid(True)

# Animation setup
if with_timeseries and animate:
    max_len = max(len(profile) for profile in twl_profiles)
    linecoll = LineCollection([], cmap='gist_earth', norm=plt.Normalize(vmin=vmin, vmax=vmax), linewidth=3, alpha=0.7)
    ax.add_collection(linecoll)

    def update(frame):
        y_row, twl_row = [], []
        for yval, twl in zip(yvals, twl_profiles):
            if frame < len(twl):
                y_row.append(yval)
                twl_row.append(twl[frame])

        if len(y_row) > 1:
            segments = [((y_row[j], twl_row[j]), (y_row[j+1], twl_row[j+1])) for j in range(len(y_row)-1)]
            twl_colors = [(twl_row[j] + twl_row[j+1]) / 2 for j in range(len(twl_row)-1)]

            linecoll.set_segments(segments)
            linecoll.set_array(np.array(twl_colors))
        else:
            linecoll.set_segments([])

        ax.set_title(f"TWL Profiles - Frame {frame}")
        return linecoll,

    ani = FuncAnimation(fig, update, frames=range(0, max_len, every_count), interval=300, blit=False)

    # Save GIF
    if save_gif:
        from matplotlib.animation import PillowWriter
        ani.save("twl_profiles.gif", writer=PillowWriter(fps=20))
        print("Saved as twl_profiles.gif")

elif with_timeseries:
    # Static lines (non-animated)
    max_len = max(len(profile) for profile in twl_profiles)
    for i in range(0, max_len, every_count):
        y_row = []
        twl_row = []
        for yval, twl in zip(yvals, twl_profiles):
            if i < len(twl):
                y_row.append(yval)
                twl_row.append(twl[i])

        if len(y_row) > 1:
            segments = [((y_row[j], twl_row[j]), (y_row[j+1], twl_row[j+1])) for j in range(len(y_row)-1)]
            twl_colors = [(twl_row[j] + twl_row[j+1]) / 2 for j in range(len(twl_row)-1)]

            lc = LineCollection(segments, cmap='gist_earth', norm=plt.Normalize(vmin=vmin, vmax=vmax))
            lc.set_array(np.array(twl_colors))
            lc.set_linewidth(3)
            lc.set_alpha(0.7)
            ax.add_collection(lc)

plt.tight_layout()
plt.show()









import matplotlib.pyplot as plt

all_z = np.concatenate([c1['t2']['TWL'], c1['t3']['TWL'], c1['t4']['TWL'], c1['t5']['TWL'], c1['t6']['TWL'], c2['t0']['TWL'], c2['t1']['TWL'], c2['t2']['TWL'], c2['t3']['TWL']])

vmin = np.min(all_z)
vmax = np.max(all_z)

# Create two subplots, side by side
fig, axs = plt.subplots(1, 2, figsize=(12, 6))

# Plot 1: UTM coordinates
#axs[0].imshow(grid['Ir'].values, extent=[min(grid['eastings_grid'].values), max(grid['eastings_grid'].values), min(grid['northings_grid'].values), max(grid['northings_grid'].values)], aspect='auto', alpha=0.5)

axs[0].scatter(c1['shoreline']['eastings_shoreline'], c1['shoreline']['northings_shoreline'], c=c1['shoreline']['elevation_shoreline'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Shoreline')
axs[0].scatter(c2['shoreline']['eastings_shoreline'], c2['shoreline']['northings_shoreline'], c=c2['shoreline']['elevation_shoreline'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Shoreline')
sc2=axs[0].scatter(c1['t2']['Hrunup_utm'].values[:, 0], c1['t2']['Hrunup_utm'].values[:, 1], c=c1['t2']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 2')
axs[0].scatter(c1['t3']['Hrunup_utm'].values[:, 0], c1['t3']['Hrunup_utm'].values[:, 1], c=c1['t3']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 3')
axs[0].scatter(c1['t4']['Hrunup_utm'].values[:, 0], c1['t4']['Hrunup_utm'].values[:, 1], c=c1['t4']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 4')
axs[0].scatter(c1['t5']['Hrunup_utm'].values[:, 0], c1['t5']['Hrunup_utm'].values[:, 1], c=c1['t5']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 5')
axs[0].scatter(c1['t6']['Hrunup_utm'].values[:, 0], c1['t6']['Hrunup_utm'].values[:, 1], c=c1['t6']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 6')
axs[0].scatter(c2['t0']['Hrunup_utm'].values[:, 0], c2['t0']['Hrunup_utm'].values[:, 1], c=c2['t0']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 2')
axs[0].scatter(c2['t1']['Hrunup_utm'].values[:, 0], c2['t1']['Hrunup_utm'].values[:, 1], c=c2['t1']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 3')
axs[0].scatter(c2['t2']['Hrunup_utm'].values[:, 0], c2['t2']['Hrunup_utm'].values[:, 1], c=c2['t2']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 4')
axs[0].scatter(c2['t3']['Hrunup_utm'].values[:, 0], c2['t3']['Hrunup_utm'].values[:, 1], c=c2['t3']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 5')
#axs[0].legend()
axs[0].set_title('Oct 22nd 2024 1800 - CACO03 c1 (UTM)')
axs[0].set_xlabel('Eastings (m)')
axs[0].set_ylabel('Northings (m)')

# Plot 2: Local coordinates
axs[1].imshow(np.flipud(rec_image['Ir'].values), extent=[np.min(rec_image['localX_grid'].values), np.max(rec_image['localX_grid'].values), np.min(rec_image['localY_grid'].values), np.max(rec_image['localY_grid'].values)], aspect='auto')


axs[1].scatter(c1['shoreline']['localX_shoreline'], c1['shoreline']['localY_shoreline'], c=c1['shoreline']['elevation_shoreline'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Shoreline')
axs[1].scatter(c2['shoreline']['localX_shoreline'], c2['shoreline']['localY_shoreline'], c=c2['shoreline']['elevation_shoreline'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Shoreline')
axs[1].scatter(c1['t2']['Hrunup_local'].values[:, 0], c1['t2']['Hrunup_local'].values[:, 1], c=c1['t2']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 2')
axs[1].scatter(c1['t3']['Hrunup_local'].values[:, 0], c1['t3']['Hrunup_local'].values[:, 1], c=c1['t3']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 3')
axs[1].scatter(c1['t4']['Hrunup_local'].values[:, 0], c1['t4']['Hrunup_local'].values[:, 1], c=c1['t4']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 4')
axs[1].scatter(c1['t5']['Hrunup_local'].values[:, 0], c1['t5']['Hrunup_local'].values[:, 1], c=c1['t5']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 5')
axs[1].scatter(c1['t6']['Hrunup_local'].values[:, 0], c1['t6']['Hrunup_local'].values[:, 1], c=c1['t6']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 6')
axs[1].scatter(c2['t0']['Hrunup_local'].values[:, 0], c2['t0']['Hrunup_local'].values[:, 1], c=c2['t0']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 2')
axs[1].scatter(c2['t1']['Hrunup_local'].values[:, 0], c2['t1']['Hrunup_local'].values[:, 1], c=c2['t1']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 3')
axs[1].scatter(c2['t2']['Hrunup_local'].values[:, 0], c2['t2']['Hrunup_local'].values[:, 1], c=c2['t2']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 4')
axs[1].scatter(c2['t3']['Hrunup_local'].values[:, 0], c2['t3']['Hrunup_local'].values[:, 1], c=c2['t3']['TWL'], cmap='gist_earth', vmin=vmin, vmax=vmax, edgecolors='black', linewidths=0.1, label='Transect 5')

#axs[1].legend()
axs[1].set_title('Oct 22nd 2024 1800 - CACO03 c1 (Local)')
axs[1].set_xlabel('Local X (m)')
axs[1].set_ylabel('Local Y (m)')
axs[1].set_xlim([25,75])
axs[1].set_ylim([-10, 150])
cbar = fig.colorbar(sc2, ax=axs[1])
cbar.set_label('TWL Elevation (m)')

# Adjust the layout
plt.tight_layout()

# Show the plot
plt.show()




import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Color limits from all TWL values
all_z = np.concatenate([
    c1['t2']['TWL'], c1['t3']['TWL'], c1['t4']['TWL'], c1['t5']['TWL'], c1['t6']['TWL'],
    c2['t0']['TWL'], c2['t1']['TWL'], c2['t2']['TWL'], c2['t3']['TWL']
])
vmin, vmax = np.min(all_z), np.max(all_z)

# Create subplots (2 columns)
fig = make_subplots(rows=1, cols=2, subplot_titles=["UTM Coordinates", "Local Coordinates"])

# ---- UTM Scatter ----
def add_utm_transects(fig, data_group, col):
    for tkey in ['t2', 't3', 't4', 't5', 't6', 't0', 't1', 't2', 't3']:
        if tkey in data_group:
            data = data_group[tkey]
            fig.add_trace(go.Scattergl(
                x=data['Hrunup_utm'][:, 0],
                y=data['Hrunup_utm'][:, 1],
                mode='markers',
                marker=dict(
                    color=data['TWL'],
                    colorscale='Earth',
                    reversescale = True,
                    cmin=vmin,
                    cmax=vmax,
                    size=6,
                    line=dict(width=0.1, color='black')
                ),
                showlegend=False
            ), row=1, col=col)

# ---- Local Scatter ----
def add_local_transects(fig, data_group, col):
    for tkey in ['t2', 't3', 't4', 't5', 't6', 't0', 't1', 't2', 't3']:
        if tkey in data_group:
            data = data_group[tkey]
            fig.add_trace(go.Scattergl(
                x=data['Hrunup_local'][:, 0],
                y=data['Hrunup_local'][:, 1],
                mode='markers',
                marker=dict(
                    color=data['TWL'],
                    colorscale='Earth',
                    reversescale = True,
                    cmin=vmin,
                    cmax=vmax,
                    size=6,
                    line=dict(width=0.1, color='black')
                ),
                showlegend=False
            ), row=1, col=col)

# ---- Shoreline ----
def add_shoreline(fig, shoreline, xkey, ykey, elev_key, col):
    fig.add_trace(go.Scattergl(
        x=shoreline[xkey],
        y=shoreline[ykey],
        mode='markers',
        marker=dict(
            color=shoreline[elev_key],
            colorscale='Earth',
                    reversescale = True,
            cmin=vmin,
            cmax=vmax,
            size=6,
            line=dict(width=0.1, color='black')
        ),
        showlegend=False
    ), row=1, col=col)

# ---- Background image in Local Coordinates ----
def add_image_background(fig, img_data, x_coords, y_coords, col):
    fig.add_layout_image(
        dict(
            source=f"data:image/png;base64,{img_data}",
            xref=f"x{col}",
            yref=f"y{col}",
            x=np.min(x_coords),
            y=np.max(y_coords),
            sizex=np.ptp(x_coords),
            sizey=np.ptp(y_coords),
            sizing="stretch",
            opacity=1.0,
            layer="below"
        )
    )

# Add UTM
add_shoreline(fig, c1['shoreline'], 'eastings_shoreline', 'northings_shoreline', 'elevation_shoreline', col=1)
add_shoreline(fig, c2['shoreline'], 'eastings_shoreline', 'northings_shoreline', 'elevation_shoreline', col=1)
add_utm_transects(fig, c1, col=1)
add_utm_transects(fig, c2, col=1)

# Add Local
add_shoreline(fig, c1['shoreline'], 'localX_shoreline', 'localY_shoreline', 'elevation_shoreline', col=2)
add_shoreline(fig, c2['shoreline'], 'localX_shoreline', 'localY_shoreline', 'elevation_shoreline', col=2)
add_local_transects(fig, c1, col=2)
add_local_transects(fig, c2, col=2)

# Add image background for local
# Convert image to base64
import base64
from PIL import Image
import io

rgb_flipped = rgb.astype(np.uint8)
im_rgb = Image.fromarray(rgb_flipped)
buffer_rgb = io.BytesIO()
im_rgb.save(buffer_rgb, format="PNG")
img_str_rgb = base64.b64encode(buffer_rgb.getvalue()).decode()

add_image_background(
    fig,
    img_data=img_str_rgb,
    x_coords=[bounds.left, bounds.right],
    y_coords=[bounds.bottom, bounds.top],
    col=1
)

# Flip image to match matplotlib's imshow
img = np.flipud(rec_image['Ir'].values).astype(np.uint8)
im = Image.fromarray(img)
buffer = io.BytesIO()
im.save(buffer, format="PNG")
img_str = base64.b64encode(buffer.getvalue()).decode()

add_image_background(
    fig,
    img_data=img_str,
    x_coords=rec_image['localX_grid'].values,
    y_coords=rec_image['localY_grid'].values,
    col=2
)


# Update axes
fig.update_xaxes(title_text="Eastings (m)", row=1, col=1)
fig.update_yaxes(title_text="Northings (m)", row=1, col=1)
fig.update_xaxes(title_text="Local X (m)", row=1, col=2, range=[25, 75])
fig.update_yaxes(title_text="Local Y (m)", row=1, col=2, range=[-10, 150])

# Colorbar
fig.update_layout(
    height=700,
    width=1300,
    title_text="Oct 22nd 2024 1800 - CACO03",
    coloraxis=dict(
        colorscale='Earth',
        reversescale=True,
        cmin=vmin,
        cmax=vmax,
        colorbar=dict(title="TWL Elevation (m)", tickvals=[vmin, vmax])
    )
)

fig.show()




import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import ast
import utm

origin = np.array([c1['shoreline'].attrs['origin_easting'], c1['shoreline'].attrs['origin_northing']])
origin[0], origin[1] = utm.to_latlon(origin[0], origin[1], 19, 'N')

extrinsics = ast.literal_eval(c1['shoreline'].attrs['extrinsics'])

lat, lon = utm.to_latlon(extrinsics['x'], extrinsics['y'], 19, 'N')
camera = np.array([lat, lon, extrinsics['z']])

def xr_to_pd_shoreline(ds, name, zone_number=19, zone_letter='N'):
    df = pd.DataFrame()
    df['TWL'] = ds['elevation_shoreline'].values
    df['eastings'] = ds['eastings_shoreline'].values
    df['northings'] = ds['northings_shoreline'].values
    df['latitude'], df['longitude'] = utm.to_latlon(df['eastings'], df['northings'], zone_number, zone_letter)
    df['source'] = name
    return df

def xr_to_pd_runup(ds, name, zone_number=19, zone_letter='N'):
    df = ds['TWL'].to_dataframe().reset_index()
    df['eastings'] = ds['Hrunup_utm'].values[:,0]
    df['northings'] = ds['Hrunup_utm'].values[:,1]
    df['latitude'], df['longitude'] = utm.to_latlon(df['eastings'], df['northings'], zone_number, zone_letter)
    df['source'] = name
    return df

dfs = [xr_to_pd_shoreline(c1['shoreline'], 'c1_shoreline'), xr_to_pd_shoreline(c2['shoreline'], 'c1_shoreline'), 
      xr_to_pd_runup(c1['t2'], 'c1_t2'), xr_to_pd_runup(c1['t3'], 'c1_t3'),
      xr_to_pd_runup(c1['t4'], 'c1_t4'), xr_to_pd_runup(c1['t5'], 'c1_t5'),
      xr_to_pd_runup(c1['t6'], 'c1_t6'), xr_to_pd_runup(c2['t0'], 'c2_t0'),
      xr_to_pd_runup(c2['t1'], 'c2_t1'), xr_to_pd_runup(c2['t2'], 'c2_t2'),
      xr_to_pd_runup(c2['t3'], 'c2_t3')]

combined_df = pd.concat(dfs, ignore_index=True)

camera_df = pd.DataFrame({
    'latitude': [camera[0]],
    'longitude': [camera[1]],
    'TWL': [camera[2]],  # TWL can be an arbitrary value or set to 0 for just marking the point
    'source': ['Origin']  # A label for the origin
})
# Create the scatter plot using scatter_geo
fig = px.scatter_map(combined_df, lat="latitude", lon="longitude", 
                     color = "TWL",
                     color_continuous_scale="earth_r", 
                     title="Shoreline and Transect Locations Colored by TWL", zoom=10)

origin_map = px.scatter_map(camera_df, lat="latitude", lon="longitude", 
                            color_discrete_sequence=["crimson"], title="Origin Point")
# Extract the trace from the origin map
origin_trace = origin_map.data[0]

# Add the origin trace to the main figure
fig.add_trace(origin_trace)

fig.update_layout(
    map_style="white-bg",
    width=500,  # Adjust these values to control the size
    height=500,
    mapbox_center={"lat": origin[0], "lon": origin[1]},
    map_layers=[
        {
            "below": 'traces',
            "sourcetype": "raster",
            "sourceattribution": "United States Geological Survey",
            "source": [
                "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
            ]
        }
      ])
fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})

fig.update_layout(map_bounds={"west": -69.968, "east": -69.96, "south": 41.5, "north": 42.5})

fig.show()

