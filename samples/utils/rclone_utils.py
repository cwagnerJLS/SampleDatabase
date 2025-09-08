"""
Rclone utility functions for SharePoint file operations.
Centralizes rclone command execution to eliminate duplicate code.
"""
import subprocess
import os
import logging
from typing import Optional, List, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class RcloneError(Exception):
    """Custom exception for rclone operation failures."""
    pass


class RcloneManager:
    """
    Manages rclone operations with consistent error handling and logging.
    """
    
    def __init__(self):
        """Initialize the RcloneManager with the configured executable path."""
        self.executable = getattr(settings, 'RCLONE_EXECUTABLE', '/usr/bin/rclone')
        logger.info(f"RcloneManager initialized with executable: {self.executable}")
    
    def _execute_command(self, args: List[str], check: bool = True) -> Tuple[int, str, str]:
        """
        Execute an rclone command with consistent error handling.
        
        Args:
            args: List of command arguments (excluding the executable)
            check: Whether to raise exception on non-zero return code
        
        Returns:
            Tuple of (return_code, stdout, stderr)
        
        Raises:
            RcloneError: If the command fails and check=True
        """
        command = [self.executable] + args
        logger.debug(f"Executing rclone command: {' '.join(command)}")
        
        try:
            result = subprocess.run(
                command,
                check=check,
                capture_output=True,
                text=True,
                env=os.environ
            )
            
            if result.stdout:
                logger.debug(f"rclone stdout: {result.stdout}")
            if result.stderr:
                if result.returncode != 0:
                    logger.error(f"rclone stderr: {result.stderr}")
                else:
                    logger.debug(f"rclone stderr: {result.stderr}")
            
            return result.returncode, result.stdout, result.stderr
            
        except subprocess.CalledProcessError as e:
            logger.error(f"rclone command failed: {e}")
            logger.error(f"stderr: {e.stderr}")
            raise RcloneError(f"rclone command failed: {e.stderr}")
        except Exception as e:
            logger.error(f"Unexpected error executing rclone: {e}")
            raise RcloneError(f"Unexpected error: {e}")
    
    def delete(self, remote_path: str) -> bool:
        """
        Delete a file from the remote storage.
        
        Args:
            remote_path: Path to the file on remote storage (e.g., "TestLabSamples:folder/file.txt")
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Deleting remote file: {remote_path}")
            self._execute_command(['delete', remote_path])
            logger.info(f"Successfully deleted: {remote_path}")
            return True
        except RcloneError as e:
            logger.error(f"Failed to delete {remote_path}: {e}")
            return False
    
    def copy(self, source_path: str, destination_path: str, 
             ignore_size: bool = False, ignore_checksum: bool = False) -> bool:
        """
        Copy a file to the remote storage.
        
        Args:
            source_path: Local path to the file
            destination_path: Remote path (e.g., "TestLabSamples:folder/file.txt")
            ignore_size: Whether to ignore file size in comparison
            ignore_checksum: Whether to ignore checksum in comparison
        
        Returns:
            True if successful, False otherwise
        """
        try:
            args = ['copyto', source_path, destination_path]
            if ignore_size:
                args.append('--ignore-size')
            if ignore_checksum:
                args.append('--ignore-checksum')
            
            logger.info(f"Copying {source_path} to {destination_path}")
            self._execute_command(args)
            logger.info(f"Successfully copied to: {destination_path}")
            return True
        except RcloneError as e:
            logger.error(f"Failed to copy {source_path} to {destination_path}: {e}")
            return False
    
    def purge(self, remote_path: str) -> bool:
        """
        Remove a directory and all its contents from remote storage.
        
        Args:
            remote_path: Path to the directory on remote storage
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Purging remote directory: {remote_path}")
            self._execute_command(['purge', remote_path])
            logger.info(f"Successfully purged: {remote_path}")
            return True
        except RcloneError as e:
            logger.error(f"Failed to purge {remote_path}: {e}")
            return False
    
    def sync(self, source_path: str, destination_path: str, 
             delete_during: bool = False, dry_run: bool = False) -> bool:
        """
        Sync files between source and destination.
        
        Args:
            source_path: Source path (can be local or remote)
            destination_path: Destination path (can be local or remote)
            delete_during: Whether to delete files in destination that don't exist in source
            dry_run: Whether to perform a dry run (no actual changes)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            args = ['sync', source_path, destination_path]
            if delete_during:
                args.append('--delete-during')
            if dry_run:
                args.append('--dry-run')
            
            logger.info(f"Syncing {source_path} to {destination_path}")
            self._execute_command(args)
            logger.info(f"Successfully synced to: {destination_path}")
            return True
        except RcloneError as e:
            logger.error(f"Failed to sync {source_path} to {destination_path}: {e}")
            return False
    
    def folder_exists(self, remote_path: str) -> bool:
        """
        Check if a folder exists on the remote storage.
        
        Args:
            remote_path: Remote path to check (e.g., "TestLabSamples:folder_name")
        
        Returns:
            True if folder exists, False otherwise
        """
        try:
            # Use lsf to list the folder - if it exists, command succeeds
            args = ['lsf', remote_path, '--max-depth', '0']
            returncode, stdout, stderr = self._execute_command(args, check=False)
            
            if returncode == 0:
                logger.debug(f"Folder exists: {remote_path}")
                return True
            else:
                logger.debug(f"Folder does not exist: {remote_path}")
                return False
        except Exception as e:
            logger.error(f"Error checking if folder exists {remote_path}: {e}")
            return False
    
    def list_files(self, remote_path: str) -> List[str]:
        """
        List files in a remote directory.
        
        Args:
            remote_path: Path to the directory on remote storage
        
        Returns:
            List of file names, or empty list on error
        """
        try:
            logger.info(f"Listing files in: {remote_path}")
            _, stdout, _ = self._execute_command(['ls', remote_path], check=False)
            files = [line.strip() for line in stdout.splitlines() if line.strip()]
            logger.debug(f"Found {len(files)} files in {remote_path}")
            return files
        except RcloneError as e:
            logger.error(f"Failed to list files in {remote_path}: {e}")
            return []
    
    def move(self, source_path: str, destination_path: str) -> bool:
        """
        Move a file from source to destination.
        
        Args:
            source_path: Source path (can be local or remote)
            destination_path: Destination path (can be local or remote)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Moving {source_path} to {destination_path}")
            self._execute_command(['moveto', source_path, destination_path])
            logger.info(f"Successfully moved to: {destination_path}")
            return True
        except RcloneError as e:
            logger.error(f"Failed to move {source_path} to {destination_path}: {e}")
            return False


# Global instance for convenience
_rclone_manager = None


def get_rclone_manager() -> RcloneManager:
    """
    Get or create the global RcloneManager instance.
    
    Returns:
        RcloneManager instance
    """
    global _rclone_manager
    if _rclone_manager is None:
        _rclone_manager = RcloneManager()
    return _rclone_manager


# Convenience functions for backward compatibility
def delete_from_sharepoint(remote_path: str) -> bool:
    """Delete a file from SharePoint."""
    return get_rclone_manager().delete(remote_path)


def copy_to_sharepoint(local_path: str, remote_path: str) -> bool:
    """Copy a file to SharePoint."""
    return get_rclone_manager().copy(local_path, remote_path)


def purge_sharepoint_folder(remote_path: str) -> bool:
    """Remove a folder and its contents from SharePoint."""
    return get_rclone_manager().purge(remote_path)


def sync_to_sharepoint(local_path: str, remote_path: str, delete: bool = False) -> bool:
    """Sync files to SharePoint."""
    return get_rclone_manager().sync(local_path, remote_path, delete_during=delete)