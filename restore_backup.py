import os
import datetime
import subprocess
import sys

def list_backups(backup_folder):
    """List all backup files in the backup folder, sorted by date descending."""
    if not os.path.exists(backup_folder):
        print(f"Backup folder '{backup_folder}' does not exist.")
        return []

    backups = [
        f for f in os.listdir(backup_folder)
        if os.path.isfile(os.path.join(backup_folder, f)) and f.startswith('db_backup_') and f.endswith('.sqlite3')
    ]

    if not backups:
        print("No backup files found.")
        return []

    # Sort backups by timestamp in filename descending
    backups.sort(reverse=True)
    return backups

def display_backups(backups):
    """Display the list of backups to the user."""
    print("\nAvailable Backups:")
    for idx, backup in enumerate(backups, 1):
        # Extract timestamp from filename
        timestamp_str = backup.replace('db_backup_', '').replace('.sqlite3', '')
        try:
            timestamp = datetime.datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
            formatted_time = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            formatted_time = "Unknown Date"
        print(f"{idx}. {backup} (Created on: {formatted_time})")
    print()

def get_user_choice(num_backups):
    """Prompt the user to select a backup to restore."""
    while True:
        try:
            choice = input(f"Enter the number of the backup to restore (1-{num_backups}), or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                print("Restore operation canceled.")
                sys.exit(0)
            choice_num = int(choice)
            if 1 <= choice_num <= num_backups:
                return choice_num - 1  # zero-based index
            else:
                print(f"Please enter a number between 1 and {num_backups}.")
        except ValueError:
            print("Invalid input. Please enter a valid number.")

def confirm_restore(backup_file):
    """Ask the user to confirm the restore operation."""
    while True:
        confirm = input(f"Are you sure you want to restore '{backup_file}'? This will overwrite the current database. (y/n): ").strip().lower()
        if confirm in ('y', 'yes'):
            return True
        elif confirm in ('n', 'no'):
            return False
        else:
            print("Please enter 'y' or 'n'.")

def restore_backup(selected_backup_path, original_db_path):
    """Replace the original database with the selected backup."""
    try:
        # Optional: Create a backup of the current database before restoring
        if os.path.exists(original_db_path):
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            current_backup = f"{original_db_path}.current_backup_{timestamp}"
            os.rename(original_db_path, current_backup)
            print(f"Current database backed up as '{current_backup}'.")

        # Copy the selected backup to the original database path
        subprocess.run(['cp', selected_backup_path, original_db_path], check=True)
        print(f"Successfully restored '{original_db_path}' from '{selected_backup_path}'.")
    except subprocess.CalledProcessError as e:
        print(f"Error during restoration: {e}")
    except Exception as ex:
        print(f"An unexpected error occurred: {ex}")

def main():
    # Define paths
    backup_folder = '/home/jls/Desktop/SampleDatabase/backups'
    original_db_path = '/home/jls/Desktop/SampleDatabase/db.sqlite3'

    # List available backups
    backups = list_backups(backup_folder)
    if not backups:
        sys.exit(1)

    # Display backups
    display_backups(backups)

    # Get user choice
    choice_idx = get_user_choice(len(backups))
    selected_backup = backups[choice_idx]
    selected_backup_path = os.path.join(backup_folder, selected_backup)

    # Confirm restoration
    if confirm_restore(selected_backup):
        restore_backup(selected_backup_path, original_db_path)
    else:
        print("Restore operation canceled.")

if __name__ == "__main__":
    main()
