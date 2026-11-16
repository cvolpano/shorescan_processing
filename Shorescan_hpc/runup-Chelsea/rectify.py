import sys

if 'CODES' not in sys.path:
    sys.path.append('CODES')

from ImageHandler import ImageDatastore

# Set up datastore for all files in imageDir
datastore = ImageDatastore(configPath = 'config.json')
datastore.image_stats()
# Only keep image products
datastore.keep_images_by_type(['snap', 'timex', 'var', 'bright', 'dark'])
datastore.image_stats()

# Load all images to datastore
#datastore.initialize_image_handlers()

# Rectify each image onto grid provided in productsPath
datastore.apply_to_all_images('rectify_image')

# Save rectified image to netcdf
datastore.apply_to_all_images('save_to_netcdf')

# Create video of brightest oblique images - can also add start_time and end_time
datastore.create_video(image_type = 'bright', frame_rate = 12, camera = '2')#, end_time=datetime(2024, 8,17,00,00,00, tzinfo=timezone.utc))

# Rectify images, merge camers and save full image with text overlap of site, camera, time. Does not store rectified/merged images.
datastore.merge_images_fast()
