#!/usr/bin/env bash
# filter_files_Dec.sh
# Purpose: Find files containing "Dec" and copy them to destination, preserving folder structure.

set -euo pipefail  # Safer bash settings

pattern="Dec"
source_dir="/mnt/f/results_11122026"   # Fixed quotes and path
dest_dir="/mnt/f/Shorescan_Data_Dec.2024"    # Use Linux-style paths for Bash

# Ensure destination directory exists
mkdir -p "$dest_dir"


# Search recursively and copy matching files with their folder structure
find "$source_dir" -type f -print0 | while IFS= read -r -d '' file; do
    if grep -qF "$pattern" "$file" 2>/dev/null; then
        # Preserve directory structure relative to source_dir
        cp --parents "$file" "$dest_dir"
    fi
done

echo "✅ Copy complete. Files containing '$pattern' are in: $dest_dir"
