#!/bin/bash

WATCH_DIR="/home/jls/Desktop/SampleDatabase/OneDrive_Sync"
REMOTE="TestLabSamples:"
LOG_FILE="/home/jls/Desktop/SampleDatabase/rclone_sync.log"

# Function to sync the directory
sync_to_remote() {
    echo "Change detected. Syncing to remote..."
    rclone sync "$WATCH_DIR" "$REMOTE" --progress --log-file="$LOG_FILE"
    echo "Sync completed."
}

# Watch for changes and sync
inotifywait -m -r -e modify,create,delete,move "$WATCH_DIR" --format '%w%f' |
while read change; do
    sync_to_remote
done
