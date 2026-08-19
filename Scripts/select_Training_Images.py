import os
import shutil

# Configuration

JPG_SOURCE_DIR = "E:/cvolpano/shorescan_processing/results/Training"
PNG_SOURCE_DIR = "E:/cvolpano/shorescan_processing/images/Processed"
SUBFOLDER_NAME = "filtered"

JPG_PREFIX = "overlay_"


def main():
    jpg_source_dir = os.path.abspath(JPG_SOURCE_DIR)
    png_dir = os.path.abspath(PNG_SOURCE_DIR)
    source_dir = png_dir
    dest_dir = os.path.join(source_dir, SUBFOLDER_NAME)

    # Collect all files in source dirs
    result_files = os.listdir(jpg_source_dir)
    png_files = os.listdir(source_dir)

    png_files = [f for f in png_files if f.endswith(".png")]
    jpg_files = [f for f in result_files if f.endswith(".jpg")]

    # Build set of jpg base names (strip "overlay_" prefix and ".jpg" extension)
    jpg_basenames = set()
    for f in jpg_files:
        name = f
        if name.startswith(JPG_PREFIX):
            name = name[len(JPG_PREFIX):]
        name = os.path.splitext(name)[0]
        jpg_basenames.add(name)

    orphans = []
    for png in png_files:
        base_name = os.path.splitext(png)[0]  # strip ".png"

        # Check if a matching jpg (overlay_<base_name>.jpg) exists
        if base_name not in jpg_basenames:
            orphans.append(png)

    if not orphans:
        print("No orphaned png files found. Nothing to move.")
        return

    os.makedirs(dest_dir, exist_ok=True)

    print(f"Found {len(orphans)} orphaned png file(s). Moving to '{dest_dir}':\n")
    for png in orphans:
        src_path = os.path.join(source_dir, png)
        dst_path = os.path.join(dest_dir, png)
        shutil.move(src_path, dst_path)
        print(f"  Moved: {png}")

    print("\nDone.")


if __name__ == "__main__":
    main()