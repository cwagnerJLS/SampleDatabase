import subprocess
import datetime
import os

def backup_database():
    # Define paths and remote settings
    local_db_path = '/home/jls/Desktop/SampleDatabase/db.sqlite3'
    backup_folder = '/home/jls/Desktop/SampleDatabase/backups'
    remote = 'TestLabSamples'
    remote_folder = 'Sample Documentation'

    # Ensure the backup folder exists
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)

    # Create a timestamped copy of the database
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f'db_backup_{timestamp}.sqlite3'
    backup_file_path = os.path.join(backup_folder, backup_file)

    # Copy the database file to the backup location
    subprocess.run(['cp', local_db_path, backup_file_path], check=True)

    # Upload the backup file to OneDrive
    target_folder = f"{remote}:{remote_folder}"
    try:
        subprocess.run(['rclone', 'copy', backup_file_path, target_folder], check=True)
        print(f"Successfully backed up {backup_file_path} to {remote_folder}")
    except subprocess.CalledProcessError as e:
        print(f"Error uploading file: {e}")
    except FileNotFoundError:
        print("Make sure rclone is installed and accessible from your PATH.")

    # Optional: Remove old backups locally (e.g., older than 7 days)
    cleanup_local_backups(backup_folder, days=7)

def cleanup_local_backups(folder, days=7):
    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=days)
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        if os.path.isfile(file_path):
            file_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
            if file_time < cutoff:
                os.remove(file_path)
                print(f"Deleted old backup: {file_path}")

if __name__ == "__main__":
    backup_database()
