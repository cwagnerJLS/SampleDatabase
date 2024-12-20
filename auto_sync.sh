#!/bin/bash

# Define directories and remote
WATCH_DIR="/home/jls/Desktop/SampleDatabase/OneDrive_Sync"
REMOTE="TestLabSamples:"
LOG_FILE="/home/jls/Desktop/SampleDatabase/rclone_sync.log"
SYNC_DELAY=2 # Delay in seconds to debounce multiple changes

# Function to sync the main directory excluding all Excel files
sync_main() {
    echo "$(date): Change detected in main directory. Syncing..." | tee -a "$LOG_FILE"

    # Perform the main sync excluding all Excel files
    if rclone sync "$WATCH_DIR" "$REMOTE" \
        --progress \
        --log-file="$LOG_FILE" \
        --exclude "*.xls" \
        --exclude "*.xlsx" \
        --exclude "*.xlsm" \
        --checkers 4 \
        --transfers 4 \
        -vv; then
        echo "$(date): Main sync completed successfully." | tee -a "$LOG_FILE"
    else
        echo "$(date): Error during main sync. Check $LOG_FILE for details." | tee -a "$LOG_FILE"
    fi

    # Perform a separate sync for all Excel files with ignore-size and ignore-checksum
    if rclone copy "$WATCH_DIR" "$REMOTE" \
        --progress \
        --log-file="$LOG_FILE" \
        --include "*.xls" \
        --include "*.xlsx" \
        --include "*.xlsm" \
        --checkers 4 \
        --transfers 4 \
        -vv \
        --ignore-size \
        --ignore-checksum; then
        echo "$(date): Excel files sync completed successfully." | tee -a "$LOG_FILE"
    else
        echo "$(date): Error during Excel files sync. Check $LOG_FILE for details." | tee -a "$LOG_FILE"
    fi
}

# Watch for changes in the main directory and sync with debounce
inotifywait -m -r -e modify,create,delete,move "$WATCH_DIR" --format '%w%f' |
while read change; do
    # Avoid triggering sync multiple times in rapid succession
    if [[ -z "$SYNC_PID_MAIN" || ! -d "/proc/$SYNC_PID_MAIN" ]]; then
        sync_main &
        SYNC_PID_MAIN=$!
        sleep $SYNC_DELAY
    fi
done
