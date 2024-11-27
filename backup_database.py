import subprocess
import datetime
import os
import logging


def backup_database():
    # Define paths
    local_db_path = '/home/jls/Desktop/SampleDatabase/db.sqlite3'
    backup_folder = '/home/jls/Desktop/SampleDatabase/OneDrive_Sync/_Backups'

    # Ensure the backup folder exists
    os.makedirs(backup_folder, exist_ok=True)

    # Create a timestamped copy of the database
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f'db_backup_{timestamp}.sqlite3'
    backup_file_path = os.path.join(backup_folder, backup_file)

    try:
        # Copy the database file to the backup location
        subprocess.run(['cp', local_db_path, backup_file_path], check=True)
        logging.info(f"Database backed up to {backup_file_path}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Error copying database: {e}")
        return
    except FileNotFoundError:
        logging.error("The source database file was not found.")
        return

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
                try:
                    os.remove(file_path)
                    logging.info(f"Deleted old backup: {file_path}")
                except Exception as e:
                    logging.error(f"Error deleting file {file_path}: {e}")


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        filename='/home/jls/Desktop/SampleDatabase/backup.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    backup_database()
