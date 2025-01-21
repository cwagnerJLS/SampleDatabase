#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

###############################################################################
#                          USER-DEFINED SETTINGS
###############################################################################
WATCH_DIR="/home/jls/Desktop/SampleDatabase/OneDrive_Sync"
REMOTE="TestLabSamples:"
LOG_DIR="/home/jls/Desktop/SampleDatabase/logs"
LOG_FILE="$LOG_DIR/rclone_sync.log"
SYNC_DELAY=2  # Delay in seconds to debounce multiple changes

# CSV file where we track the 4-digit folder name (OpportunityNumber) and hyperlink
OPPORTUNITY_CSV="/home/jls/Desktop/SampleDatabase/Hyperlinks.csv"

# Folders on the remote to permanently ignore (will not sync or delete)
IGNORED_REMOTE_FOLDERS=("_Archive" "_Backups" "_Templates")

###############################################################################
#                              INITIALIZATION
###############################################################################

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Create CSV if it doesn't exist; optionally add headers
if [[ ! -f "$OPPORTUNITY_CSV" ]]; then
    echo "OpportunityNumber,Hyperlink" > "$OPPORTUNITY_CSV"
    echo "$(date): Created $OPPORTUNITY_CSV with headers." | tee -a "$LOG_FILE"
fi

# Redirect script output to log file
exec > >(tee -a "$LOG_FILE") 2>&1

# Use flock to ensure only one instance runs
LOCK_FILE="/tmp/auto_sync.lock"
exec 200>"$LOCK_FILE"
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

# Optional: Maintain .keep files in empty directories
add_placeholder_files_for_empty_directories() {
    echo "$(date): Checking for empty folders and adding .keep files..."
    find "$WATCH_DIR" -type d -empty -exec sh -c 'touch "$1/.keep"' _ {} \;
}

# Function to build --exclude flags for folders we want to ignore on the remote
build_ignored_folders_excludes() {
    local excludes=()
    for folder in "${IGNORED_REMOTE_FOLDERS[@]}"; do
        # Each of these --exclude statements ensures that folder (and its contents)
        # is skipped in both directions.
        excludes+=( "--exclude" "${folder}/**" )
    done
    echo "${excludes[@]}"
}

# Function to update CSV with current 4-digit folders
update_csv() {
    echo "$(date): Updating CSV tracking..."

    # Find all immediate subfolders that match 4 digits (no recursion)
    mapfile -t current_folders < <(
        find "$WATCH_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
        | grep -E '^[0-9]{4}$'
    )

    # Get list of folders currently in CSV
    mapfile -t csv_folders < <(
        tail -n +2 "$OPPORTUNITY_CSV" | cut -d',' -f1
    )

    # Add new folders to CSV
    for folder in "${current_folders[@]}"; do
        if [[ ! " ${csv_folders[@]} " =~ " ${folder} " ]]; then
            echo "$(date): Adding folder $folder to CSV."
            link=$(rclone link "${REMOTE}${folder}" --onedrive-link-scope=organization 2>>"$LOG_FILE" | tail -n 1)
            if [[ -n "$link" ]]; then
                echo "${folder},${link}" >> "$OPPORTUNITY_CSV"
                echo "$(date): Added folder $folder with link $link to CSV."
            else
                echo "$(date): Failed to retrieve link for folder $folder."
            fi
        fi
    done

    # Remove entries from CSV that no longer exist locally
    for folder in "${csv_folders[@]}"; do
        if [[ ! " ${current_folders[@]} " =~ " ${folder} " ]]; then
            echo "$(date): Removing folder $folder from CSV."
            grep -v "^${folder}," "$OPPORTUNITY_CSV" > "${OPPORTUNITY_CSV}.tmp" || true
            mv "${OPPORTUNITY_CSV}.tmp" "$OPPORTUNITY_CSV"
            echo "$(date): Removed folder $folder from CSV."
        fi
    done

    echo "$(date): CSV tracking updated."
}

###############################################################################
#                               SYNC LOGIC
###############################################################################
#
# Only sync image files inside a folder named "Samples" (in any 4-digit folder).
#

sync_main() {
    echo "$(date): ===== SYNC START ====="

    # Keep empty directories from vanishing
    add_placeholder_files_for_empty_directories

    # Build the array of --exclude statements for ignored remote folders
    IGNORE_EXCLUDES=( $(build_ignored_folders_excludes) )

    ###########################################################################
    # Sync only image files in "Samples" subfolders
    #
    #    --include "*/Samples/**/*.jpg"
    #    --include "*/Samples/**/*.jpeg"
    #    ...
    #    --exclude "*"
    #
    # This ensures we ONLY upload image files in any directory named "Samples",
    # ignoring all other files/folders.
    ###########################################################################
    echo "$(date): Syncing only image files within 'Samples' folders..."
    rclone sync "$WATCH_DIR" "$REMOTE" \
        --include "*/Samples/**/*.jpg" \
        --include "*/Samples/**/*.jpeg" \
        --include "*/Samples/**/*.png" \
        --include "*/Samples/**/*.gif" \
        --include "*/Samples/**/*.tif" \
        --include "*/Samples/**/*.tiff" \
        --include "*/Samples/**/*.bmp" \
        --exclude "*" \
        "${IGNORE_EXCLUDES[@]}" \
        --progress \
        --log-file="$LOG_FILE" \
        --checkers 4 \
        --transfers 4 \
        --create-empty-src-dirs \
        -vv \
    || echo "$(date): Error syncing image files in 'Samples' subfolders to remote."

    echo "$(date): ===== SYNC END ====="

    # Update CSV tracking after sync
    update_csv
}

###############################################################################
#                             INOTIFY MONITORING
###############################################################################
# Monitor file and folder changes using inotifywait

inotifywait -m -r -e create,delete,moved_to,moved_from --format '%w%f %e' "$WATCH_DIR" |
while read -r changed_path event; do
    echo "$(date): Detected change => $changed_path : $event"

    # Debounce to handle rapid consecutive changes
    sleep "$SYNC_DELAY"
    sync_main
done

cleanup
