import os
import datetime
import subprocess
import sys
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Restore database from a backup file'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--auto',
            action='store_true',
            help='Automatically restore the most recent backup without prompting'
        )
        parser.add_argument(
            '--backup-file',
            type=str,
            help='Specific backup file to restore (e.g., db_backup_20250901_020001.sqlite3)'
        )
    
    def handle(self, *args, **options):
        """Main restore process"""
        # Define paths
        backup_folder = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', '_Backups')
        original_db_path = os.path.join(settings.BASE_DIR, 'db.sqlite3')
        
        # List available backups
        backups = self.list_backups(backup_folder)
        if not backups:
            self.stdout.write(self.style.ERROR('No backup files found.'))
            return
        
        # Determine which backup to restore
        if options['backup_file']:
            # Use specified backup file
            if options['backup_file'] not in backups:
                self.stdout.write(self.style.ERROR(f"Backup file '{options['backup_file']}' not found."))
                return
            selected_backup = options['backup_file']
        elif options['auto']:
            # Use most recent backup
            selected_backup = backups[0]
            self.stdout.write(f"Auto-restoring most recent backup: {selected_backup}")
        else:
            # Interactive selection
            selected_backup = self.interactive_selection(backups)
            if not selected_backup:
                self.stdout.write(self.style.WARNING('Restore operation canceled.'))
                return
        
        selected_backup_path = os.path.join(backup_folder, selected_backup)
        
        # Confirm restoration (skip if auto mode)
        if not options['auto']:
            if not self.confirm_restore(selected_backup):
                self.stdout.write(self.style.WARNING('Restore operation canceled.'))
                return
        
        # Perform the restoration
        self.restore_backup(selected_backup_path, original_db_path)
    
    def list_backups(self, backup_folder):
        """List all backup files in the backup folder, sorted by date descending."""
        if not os.path.exists(backup_folder):
            return []
        
        backups = [
            f for f in os.listdir(backup_folder)
            if os.path.isfile(os.path.join(backup_folder, f)) and 
            f.startswith('db_backup_') and f.endswith('.sqlite3')
        ]
        
        # Sort backups by timestamp in filename descending (newest first)
        backups.sort(reverse=True)
        return backups
    
    def interactive_selection(self, backups):
        """Interactively display backups and get user selection"""
        self.stdout.write(self.style.WARNING('\nAvailable Backups:'))
        
        for idx, backup in enumerate(backups, 1):
            # Extract timestamp from filename
            timestamp_str = backup.replace('db_backup_', '').replace('.sqlite3', '')
            try:
                timestamp = datetime.datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                formatted_time = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                formatted_time = "Unknown Date"
            
            # Get file size
            file_path = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', '_Backups', backup)
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            
            self.stdout.write(f"{idx}. {backup} (Created: {formatted_time}, Size: {size_mb:.2f} MB)")
        
        self.stdout.write('')
        
        # Get user choice
        while True:
            try:
                choice = input(f"Enter the number of the backup to restore (1-{len(backups)}), or 'q' to quit: ").strip()
                if choice.lower() == 'q':
                    return None
                choice_num = int(choice)
                if 1 <= choice_num <= len(backups):
                    return backups[choice_num - 1]
                else:
                    self.stdout.write(f"Please enter a number between 1 and {len(backups)}.")
            except ValueError:
                self.stdout.write("Invalid input. Please enter a valid number.")
            except KeyboardInterrupt:
                self.stdout.write('')
                return None
    
    def confirm_restore(self, backup_file):
        """Ask the user to confirm the restore operation."""
        while True:
            try:
                confirm = input(
                    f"\nAre you sure you want to restore '{backup_file}'?\n"
                    f"This will overwrite the current database. (y/n): "
                ).strip().lower()
                
                if confirm in ('y', 'yes'):
                    return True
                elif confirm in ('n', 'no'):
                    return False
                else:
                    self.stdout.write("Please enter 'y' or 'n'.")
            except KeyboardInterrupt:
                self.stdout.write('')
                return False
    
    def restore_backup(self, selected_backup_path, original_db_path):
        """Replace the original database with the selected backup."""
        try:
            # Create a backup of the current database before restoring
            if os.path.exists(original_db_path):
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                current_backup = f"{original_db_path}.before_restore_{timestamp}"
                os.rename(original_db_path, current_backup)
                self.stdout.write(
                    self.style.SUCCESS(f"Current database backed up as: {os.path.basename(current_backup)}")
                )
            
            # Copy the selected backup to the original database path
            subprocess.run(['cp', selected_backup_path, original_db_path], check=True)
            
            # Set proper permissions
            os.chmod(original_db_path, 0o664)
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Successfully restored database from '{os.path.basename(selected_backup_path)}'"
                )
            )
            
            self.stdout.write(
                self.style.WARNING(
                    "\n⚠️  Remember to restart the Django and Celery services:\n"
                    "   sudo systemctl restart django-sampledb\n"
                    "   sudo systemctl restart celery-sampledb"
                )
            )
            
        except subprocess.CalledProcessError as e:
            self.stdout.write(self.style.ERROR(f"Error during restoration: {e}"))
            raise
        except Exception as ex:
            self.stdout.write(self.style.ERROR(f"An unexpected error occurred: {ex}"))
            raise