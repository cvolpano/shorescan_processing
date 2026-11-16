#!/bin/bash

BUCKET="cmgp-coastcam/cameras/caco-03/products"
TXT_FILE="/c/Users/cvolpano/shorescan_processing/Scripts/missing.txt/missing.txt"
DOWNLOAD_DIR="/e/cvolpano/DATA/CoastCam/MarconiTimestacks"

mkdir -p "$DOWNLOAD_DIR"

while IFS= read -r key; do
    clean_key=$(echo "$key" | tr -d '\r' | xargs)  # remove \r and trim spaces
    echo "DEBUG: [$clean_key]"
    aws s3 cp "s3://$BUCKET/$clean_key" "$DOWNLOAD_DIR/"
done < "$TXT_FILE"
