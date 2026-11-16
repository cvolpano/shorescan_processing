import sys
import json

if 'CODES' not in sys.path:
    sys.path.append('CODES')

from ImageHandler import ImageDatastore

with open('config.json', "r") as f:
    config = json.load(f)
    

# # Split .tiff files from i2RGUS into individual transects
# if config.get('split_tiff', False) is True:
#     import utils_runup
#     utils_runup.split_tiff(config)

# # Set up datastore for all files in imageDir
datastore = ImageDatastore(configPath = config)

# Remove image products -> keep transects
datastore.remove_images_by_type(['snap', 'timex', 'var', 'bright', 'dark'])
datastore.image_stats()


# Get runup from segformer model (segformerCodeDir/segformerModel), rectify onto DEM (demPath) and save to netcdf
datastore.get_runup_from_timestacks(segformer_flag=True, save_flag=True)
