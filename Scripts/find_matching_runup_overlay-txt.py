import os
import shutil

# Configuration
JPG_SOURCE_DIR ="E:/cvolpano/shorescan_processing/results/runup"
# "//wsl.localhost/Ubuntu/home/cvolpano/runup-Chelsea/DATA/DATA/results/runup"  # change to your folder path if needed
NC_SOURCE_DIR  = "E:/cvolpano/Linux_file_backup/ShoreScan/runup-Chelsea/DATA/DATA/results/netcdf/filtered"
# "//wsl.localhost/Ubuntu/home/cvolpano/runup-Chelsea/DATA/DATA/results/netcdf"
OUTPUT_DIR = "E:/cvolpano/shorescan_processing/results/netcdf/filtered"
SUBFOLDER_NAME = "filtered2"
TXT_PREFIX = "runup_"

JPG_PREFIX = "overlay_"


def main():
    jpg_source_dir = os.path.abspath(JPG_SOURCE_DIR)
    netcdf_dir = os.path.abspath(NC_SOURCE_DIR)
    source_dir = netcdf_dir
    dest_dir = os.path.join(OUTPUT_DIR, SUBFOLDER_NAME)
    

    # Collect all files in source dir
    result_files = os.listdir(jpg_source_dir)
    netcdf_files = os.listdir(netcdf_dir)
    txt_files = [f for f in result_files if f.startswith(TXT_PREFIX) and f.endswith(".txt")]
    jpg_files = set(f for f in result_files if f.startswith(JPG_PREFIX) and f.endswith(".jpg"))
    nc_files = [n for n in netcdf_files if n.endswith('.nc')]

    # Build set of jpg "suffixes" (the part after the prefix) for matching
    jpg_suffixes = set(f[len(JPG_PREFIX):] for f in jpg_files)

    orphans = []
    for nc in nc_files:
        # suffix = txt[len(TXT_PREFIX):-4]  # strip prefix and .txt
        suffix = nc[0:-3]
        expected_jpg_suffix = suffix + ".jpg"
        if expected_jpg_suffix not in jpg_suffixes:
            orphans.append(nc)
            # orphans.append(txt)
        
    if not orphans:
        print("No orphaned txt files found. Nothing to move.")
        return

    os.makedirs(dest_dir, exist_ok=True)

    print(f"Found {len(orphans)} orphaned txt file(s). Moving to '{dest_dir}':\n")
    for txt in orphans:
        src_path = os.path.join(source_dir, txt)
        dst_path = os.path.join(dest_dir, txt)
        shutil.move(src_path, dst_path)
        print(f"  Moved: {txt}")

    print("\nDone.")

if __name__ == "__main__":
    main()