import os
import shutil
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from pathlib import Path

# === SETTINGS ===
image_folder = 'DATA/DATA/results/runup/'
valid_extensions = ['.jpg', '.jpeg', '.png']
backup_deleted = True
window_position = (100, 100)  # Fixed position on screen
window_size = (1300, 1000)  # Size in pixels

# Setup deleted folder if needed
deleted_folder = os.path.join(image_folder, 'deleted')
if backup_deleted and not os.path.exists(deleted_folder):
    os.makedirs(deleted_folder)

# Get list of images
images = sorted([
    f for f in os.listdir(image_folder)
    if os.path.splitext(f)[1].lower() in valid_extensions
])

# Main image loop
for index, img_file in enumerate(images):
    img_path = os.path.join(image_folder, img_file)
    img = mpimg.imread(img_path)

    fig = plt.figure(figsize=(window_size[0] / 100, window_size[1] / 100))
    mng = plt.get_current_fig_manager()
    try:
        mng.window.wm_geometry(f"+{window_position[0]}+{window_position[1]}")
    except:
        pass  # Not all backends support this

    plt.imshow(img)
    plt.axis('off')
    img_name = Path(img_path).name
    plt.title(f'{img_name} ({index + 1}/{len(images)})\n→ = keep | ← = delete | Esc = exit')

    # Use dict to track state
    state = {'done': False}

    def on_key(event):
        if event.key == 'left':
            plt.close()
            if backup_deleted:
                shutil.move(img_path, os.path.join(deleted_folder, img_file))
                print(f"Moved to deleted: {img_file}")
            else:
                os.remove(img_path)
                print(f"Deleted: {img_file}")
            state['done'] = True
        elif event.key == 'right':
            plt.close()
            print(f"Kept: {img_file}")
            state['done'] = True
        elif event.key == 'escape':
            plt.close()
            print("Exiting viewer.")
            exit()

    fig.canvas.mpl_connect('key_press_event', on_key)

    # Wait until a key is pressed
    while not state['done']:
        plt.pause(0.1)


"""
import os
import shutil
import re
from pathlib import Path

# === Settings ===
image_folder = 'DATA/DATA/results/runup/deleted'       # Folder with overlay_xxx.jpg files
runup_folder = 'DATA/DATA/results/runup/'
netcdf_folder = 'DATA/DATA/results/netcdf/'

# Get all overlay image files
all_files = os.listdir(image_folder)
overlay_images = [f for f in all_files if f.lower().startswith('overlay_') and f.lower().endswith('.jpg')]


# Check and process each overlay image
for img_file in overlay_images:
    # Extract the xxx identifier from the image filename
    name_no_ext = Path(img_file).stem  # removes .jpg
    if not name_no_ext.startswith('overlay_'):
        continue

    xxx = name_no_ext.replace('overlay_', '', 1)

    # Match corresponding runup and netcdf files
    runup_txt = f'runup_{xxx}.txt'
    runup_path = os.path.join(runup_folder, runup_txt)
    if os.path.exists(runup_path):
        shutil.move(runup_path, os.path.join(runup_folder, 'deleted', runup_txt))
        print(f"Moved: {runup_txt} → runup/deleted/")

    netcdf_file = f'{xxx}.nc'
    netcdf_path = os.path.join(netcdf_folder, netcdf_file)
    if os.path.exists(netcdf_path):
        shutil.move(netcdf_path, os.path.join(netcdf_folder, 'deleted', netcdf_file))
        print(f"Moved: {netcdf_file} → netcdf/deleted/")
"""