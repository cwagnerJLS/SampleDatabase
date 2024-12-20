#!/bin/bash
set -e  # Exit on error

###############################################################################
#                          USER-DEFINED SETTINGS
###############################################################################
WATCH_DIR="/home/jls/Desktop/SampleDatabase/OneDrive_Sync"
REMOTE="TestLabSamples:"
LOG_DIR="/home/jls/Desktop/SampleDatabase/logs"
LOG_FILE_MAIN="$LOG_DIR/rclone_main_sync.log"
LOG_FILE_EXCEL="$LOG_DIR/rclone_excel_sync.log"
SYNC_DELAY=2  # Delay in seconds to debounce multiple changes

# CSV file where we track the 4-digit folder name (OpportunityNumber) and hyperlink
OPPORTUNITY_CSV="/home/jls/Desktop/SampleDatabase/Hyperlinks.csv"

###############################################################################
#                              INITIALIZATION
###############################################################################

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Create CSV if it doesn't exist; optionally add headers
if [[ ! -f "$OPPORTUNITY_CSV" ]]; then
    echo "OpportunityNumber,Hyperlink" > "$OPPORTUNITY_CSV"
    echo "$(date): Created $OPPORTUNITY_CSV with headers." | tee -a "$LOG_FILE_MAIN"
fi

# Redirect script output for debugging (optional; comment if undesired)
exec > >(tee -a "$LOG_FILE_MAIN") 2>&1

# Ensure only one instance of the script runs
PID_FILE="/tmp/rclone_sync.pid"
if [[ -f "$PID_FILE" ]]; then
    echo "$(date): Another instance is already running. Exiting."
    exit 1
fi
echo $$ > "$PID_FILE"

cleanup() {
    echo "$(date): Cleaning up..."
    rm -f "$PID_FILE"
    exit 0
}
trap cleanup SIGINT SIGTERM

###############################################################################
#                           HELPER FUNCTIONS
###############################################################################

# 1. Full sync logic:
#    - a) Sync excluding Excel
#    - b) Copy Excel ignoring size/checksum
sync_main() {
    echo "$(date): ===== SYNC START ====="

    # PART (A): Main sync (exclude Excel)
    if rclone sync "$WATCH_DIR" "$REMOTE" \
        --progress \
        --log-file="$LOG_FILE_MAIN" \
        --exclude "*.xls" \
        --exclude "*.xlsx" \
        --exclude "*.xlsm" \
        --checkers 4 \
        --transfers 4 \
        -vv
    then
        echo "$(date): Main sync completed successfully."
    else
        echo "$(date): Error during main sync. Check $LOG_FILE_MAIN for details."
    fi

    # PART (B): Separate sync for Excel files
    if rclone copy "$WATCH_DIR" "$REMOTE" \
        --progress \
        --log-file="$LOG_FILE_EXCEL" \
        --include "*.xls" \
        --include "*.xlsx" \
        --include "*.xlsm" \
        --checkers 4 \
        --transfers 4 \
        --ignore-size \
        --ignore-checksum \
        -vv
    then
        echo "$(date): Excel files sync completed successfully."
    else
        echo "$(date): Error during Excel sync. Check $LOG_FILE_EXCEL for details."
    fi

    echo "$(date): ===== SYNC END ====="
}

# 2. Ensure all local 4-digit folders have hyperlinks in CSV
ensure_all_folders_linked() {
    echo "$(date): Ensuring all 4-digit folders in $WATCH_DIR are in $OPPORTUNITY_CSV..."

    # Find all immediate subfolders that match 4 digits (no recursion).
    # If you want to go deeper, remove `-maxdepth 1`.
    mapfile -t local_folders < <(
        find "$WATCH_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
        | grep -E '^[0-9]{4}$'
    )

    for folder_name in "${local_folders[@]}"; do
        # Check if folder_name is already in CSV
        if ! grep -q "^${folder_name}," "$OPPORTUNITY_CSV"; then
            # It's not in the CSV, so let's try to generate a link
            echo "$(date): Generating link for folder $folder_name"
            local link
            link=$(rclone link "${REMOTE}${folder_name}" --onedrive-link-scope=organization 2>>"$LOG_FILE_MAIN" | tail -n 1)

            if [[ -n "$link" ]]; then
                echo "$(date): Folder $folder_name => $link"
                # Remove stale entry if it somehow exists
                grep -v "^${folder_name}," "$OPPORTUNITY_CSV" 2>/dev/null > "${OPPORTUNITY_CSV}.tmp" || true
                mv "${OPPORTUNITY_CSV}.tmp" "$OPPORTUNITY_CSV"

                # Append new row: OpportunityNumber,Hyperlink
                echo "${folder_name},${link}" >> "$OPPORTUNITY_CSV"
            else
                echo "$(date): Could NOT retrieve link for folder $folder_name. Is it on OneDrive yet?"
            fi
        fi
    done
}

# 3. Remove a folder entry from CSV
remove_from_csv() {
    local folder_name="$1"
    if [[ -z "$folder_name" ]]; then
        return 0
    fi
    # Remove any line that starts with folder_name,
    # e.g. "7000,https://..." becomes removed.
    grep -v "^${folder_name}," "$OPPORTUNITY_CSV" 2>/dev/null > "${OPPORTUNITY_CSV}.tmp" || true
    mv "${OPPORTUNITY_CSV}.tmp" "$OPPORTUNITY_CSV"
    echo "$(date): Removed folder ${folder_name} from CSV"
}

# 4. Manage creation/deletion of 4-digit folders
manage_opportunity() {
    local changed_path="$1"
    local event="$2"
    local folder_name
    folder_name=$(basename "$changed_path")

    # Only proceed if exactly 4 digits
    if [[ $folder_name =~ ^[0-9]{4}$ ]]; then
        # If the folder is created or moved in
        if [[ $event == *CREATE* ]] || [[ $event == *MOVED_TO* ]]; then
            echo "$(date): 4-digit folder $folder_name created. Sync first..."

            # 1) SYNC to ensure folder exists on OneDrive
            sync_main

            # 2) Now ensure all local 4-digit folders have a hyperlink
            ensure_all_folders_linked

        elif [[ $event == *DELETE* ]] || [[ $event == *MOVED_FROM* ]]; then
            echo "$(date): 4-digit folder $folder_name deleted. Removing from CSV..."
            remove_from_csv "$folder_name"
        fi
    fi
}

###############################################################################
#                             INOTIFY MONITORING
###############################################################################
# Format: '%w%f %e' => path + event type
# We watch recursively (-r) and monitor continuously (-m) for create/delete/move.
###############################################################################

inotifywait -m -r -e create,delete,moved_to,moved_from --format '%w%f %e' "$WATCH_DIR" |
while read -r changed_path event; do
    echo "$(date): Detected change => $changed_path : $event"

    # 1) Check if it’s a new or deleted 4-digit folder
    manage_opportunity "$changed_path" "$event"

    # 2) (Optional) Debounce any additional changes and run sync
    #    BUT in our approach, we run sync inside manage_opportunity for creation events.
    #    If you still want a fallback sync on ANY event, uncomment below lines:

    # if [[ -z "$SYNC_PID_MAIN" || ! -d "/proc/$SYNC_PID_MAIN" ]]; then
    #     echo "$(date): Triggering background sync_main due to event..."
    #     sync_main &
    #     SYNC_PID_MAIN=$!
    #     sleep "$SYNC_DELAY"
    # fi
done

cleanup
