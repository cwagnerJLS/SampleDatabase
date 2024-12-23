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

# Use flock to ensure only one instance runs
exec 200>/var/lock/auto_sync.lock
flock -n 200 || { echo "$(date): Another instance is already running. Exiting."; exit 1; }

cleanup() {
    echo "$(date): Cleaning up..."
    flock -u 200
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

###############################################################################
#                           HELPER FUNCTIONS
###############################################################################

# 1. Full sync logic:
#    - a) Sync excluding Excel
#    - b) Sync Excel to handle additions and deletions
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

    # PART (B): Sync Excel files to handle additions and deletions
    if rclone sync "$WATCH_DIR" "$REMOTE" \
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

# 3. Remove a folder entry from CSV and purge from remote
remove_from_csv_and_purge_remote() {
    local folder_name="$1"
    if [[ -z "$folder_name" ]]; then
        return 0
    fi
    # Remove any line that starts with folder_name,
    # e.g. "7000,https://..." becomes removed.
    grep -v "^${folder_name}," "$OPPORTUNITY_CSV" 2>/dev/null > "${OPPORTUNITY_CSV}.tmp" || true
    mv "${OPPORTUNITY_CSV}.tmp" "$OPPORTUNITY_CSV"
    echo "$(date): Removed folder ${folder_name} from CSV"

    # Purge the folder from remote
    echo "$(date): Purging folder ${folder_name} from remote..."
    if rclone purge "${REMOTE}${folder_name}" --log-file="$LOG_FILE_MAIN" -vv; then
        echo "$(date): Successfully purged ${folder_name} from remote."
    else
        echo "$(date): Error purging ${folder_name} from remote. Check $LOG_FILE_MAIN for details."
    fi
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
            echo "$(date): 4-digit folder $folder_name deleted. Removing from CSV and purging remote..."
            remove_from_csv_and_purge_remote "$folder_name"
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

    # 1) Check if it's a new or deleted 4-digit folder
    manage_opportunity "$changed_path" "$event"

    # 2) Handle deletions of Excel files
    if [[ $event == *DELETE* ]] || [[ $event == *MOVED_FROM* ]]; then
        if [[ "$changed_path" =~ \.xlsm?$ ]]; then
            # Extract the folder path and file name
            local_folder=$(dirname "$changed_path")
            local_file=$(basename "$changed_path")

            # Determine the remote path
            remote_file="${REMOTE}${local_folder#$WATCH_DIR/}/$local_file"

            echo "$(date): Detected deletion of Excel file $local_file. Deleting from remote..."
            if rclone delete "$REMOTE${local_folder#$WATCH_DIR/}/$local_file" --log-file="$LOG_FILE_EXCEL" -vv; then
                echo "$(date): Successfully deleted $remote_file from remote."
            else
                echo "$(date): Error deleting $remote_file from remote. Check $LOG_FILE_EXCEL for details."
            fi
        fi
    fi

    # 3) Debounce and trigger sync for non-folder changes
    if [[ ! "$changed_path" =~ ^$WATCH_DIR/[0-9]{4}$ ]]; then
        sleep "$SYNC_DELAY"
        sync_main

        # Sync Excel deletions if any
        sync_main  # Already handled deletions above; no need for a separate sync_excel
    fi
done

cleanup