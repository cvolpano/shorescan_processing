#!/bin/bash

BUCKET="cmgp-coastcam/cameras/caco-03/products"
TXT_FILE="/c/Users/cvolpano/shorescan_processing/Scripts/missing_CACO03_c2.txt"
# C:\Users\cvolpano\shorescan_processing\Scripts
DOWNLOAD_DIR="/e/cvolpano/DATA/CoastCam/MarconiTimestacks/"  # Git Bash path format
PARALLEL_JOBS=5   # Number of simultaneous downloads

# Create download directory if it doesn't exist
mkdir -p "$DOWNLOAD_DIR"

# Parallel download using xargs, stripping Windows carriage returns
cat "$TXT_FILE" | tr -d '\r' | sed 's/[[:space:]]*$//' | grep -v '^$' | \
xargs -n 1 -P "$PARALLEL_JOBS" -I {} \
aws s3 cp "s3://$BUCKET/{}" "$DOWNLOAD_DIR/" && \
echo "✅ All downloads completed!"
