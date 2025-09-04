import subprocess
import datetime
import os
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from samples.sharepoint_config import SHAREPOINT_REMOTE_NAME
from samples.logging_config import get_logger

class Command(BaseCommand):
    help = 'Backup the database and sync to SharePoint'
    
    def __init__(self):
        super().__init__()
        self.logger = get_logger(__name__, 'backup')
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to keep local backups (default: 7)'
        )
        parser.add_argument(
            '--no-sync',
            action='store_true',
            help='Skip syncing to SharePoint'
        )
    
    def handle(self, *args, **options):
        """Main backup process"""
        self.stdout.write(self.style.SUCCESS('Starting database backup...'))
        
        # Define paths
        local_db_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
        backup_folder = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', '_Backups')
        
        # Ensure the backup folder exists
        os.makedirs(backup_folder, exist_ok=True)
        
        # Create a timestamped copy of the database
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f'db_backup_{timestamp}.sqlite3'
        backup_file_path = os.path.join(backup_folder, backup_file)
        
        try:
            # Copy the database file to the backup location
            subprocess.run(['cp', local_db_path, backup_file_path], check=True)
            self.logger.info(f"Database backed up to {backup_file_path}")
            self.stdout.write(self.style.SUCCESS(f'Database backed up to {backup_file_path}'))
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error copying database: {e}")
            self.stdout.write(self.style.ERROR(f'Error copying database: {e}'))
            return
        except FileNotFoundError:
            self.logger.error("The source database file was not found.")
            self.stdout.write(self.style.ERROR('The source database file was not found.'))
            return
        
        # Remove old backups locally
        self.cleanup_local_backups(backup_folder, days=options['days'])
        
        # Sync the local backup folder to SharePoint (mirrors the folder exactly)
        if not options['no_sync']:
            self.sync_to_sharepoint(backup_folder)
        
        self.stdout.write(self.style.SUCCESS('Backup process completed successfully'))
    
    def cleanup_local_backups(self, folder, days=7):
        """Remove local backups older than specified days"""
        now = datetime.datetime.now()
        cutoff = now - datetime.timedelta(days=days)
        
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            if os.path.isfile(file_path):
                file_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_time < cutoff:
                    try:
                        os.remove(file_path)
                        self.logger.info(f"Deleted old backup: {file_path}")
                        self.stdout.write(f'Deleted old backup: {filename}')
                    except Exception as e:
                        self.logger.error(f"Error deleting file {file_path}: {e}")
    
    def sync_to_sharepoint(self, backup_folder):
        """Sync local backup folder to SharePoint, making it an exact mirror"""
        try:
            result = subprocess.run([
                settings.RCLONE_EXECUTABLE,
                'sync',
                backup_folder,
                f'{SHAREPOINT_REMOTE_NAME}:_Backups',
                '--delete-during'  # Remove files from SharePoint that aren't in local folder
            ], 
            check=True, 
            capture_output=True, 
            text=True)
            
            if result.stdout:
                self.logger.debug(f"rclone stdout: {result.stdout}")
            
            self.logger.info("Successfully synced backups to SharePoint")
            self.stdout.write(self.style.SUCCESS('Successfully synced backups to SharePoint'))
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to sync to SharePoint: {e.stderr}")
            self.stdout.write(self.style.ERROR(f'Failed to sync to SharePoint: {e.stderr}'))
        except Exception as e:
            self.logger.error(f"Unexpected error syncing to SharePoint: {e}")
            self.stdout.write(self.style.ERROR(f'Unexpected error syncing to SharePoint: {e}'))