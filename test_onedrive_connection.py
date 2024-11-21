#!/usr/bin/env python3

import subprocess
import sys
import os
import tempfile

def send_notification(title, message):
    subprocess.run(['notify-send', title, message])

def test_onedrive_connection(remote, remote_folder):
    # Create a temporary test file
    with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt') as temp_file:
        temp_file.write("This is a test file for verifying OneDrive connection.")
        temp_file_path = temp_file.name

    test_file_name = os.path.basename(temp_file_path)
    remote_path = f"{remote}:{remote_folder}/{test_file_name}"

    try:
        # Attempt to upload the test file
        print("Uploading test file to OneDrive...")
        subprocess.run(['rclone', 'copy', temp_file_path, f"{remote}:{remote_folder}"], check=True)

        # Verify that the file exists on OneDrive
        print("Verifying upload...")
        result = subprocess.run(
            ['rclone', 'lsf', f"{remote}:{remote_folder}"],
            capture_output=True, text=True, check=True
        )
        files = result.stdout.strip().split('\n')
        if test_file_name in files:
            print("Test file successfully uploaded.")

            # Delete the test file from OneDrive
            print("Deleting test file from OneDrive...")
            subprocess.run(['rclone', 'deletefile', remote_path], check=True)
            print("Test file deleted from OneDrive.")

            # Clean up local test file
            os.remove(temp_file_path)
            print("Local test file removed.")

            # Send success notification
            send_notification("OneDrive Test Passed", "OneDrive connection test completed successfully.")
        else:
            print("Test file was not found on OneDrive. Upload may have failed.")
            error_message = "Test file not found on OneDrive after upload."
            send_notification("OneDrive Test Failed", error_message)
            sys.exit(1)

    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
        error_message = f"An error occurred: {e}"
        send_notification("OneDrive Test Failed", error_message)
        sys.exit(1)
    except FileNotFoundError:
        print("rclone is not installed or not found in PATH.")
        error_message = "rclone is not installed or not found in PATH."
        send_notification("OneDrive Test Failed", error_message)
        sys.exit(1)

def main():
    # Define your remote name and folder here
    remote = 'TestLabSamples'  # Replace with your rclone remote name
    remote_folder = 'Sample Documentation'  # Replace with your OneDrive folder

    test_onedrive_connection(remote, remote_folder)

if __name__ == "__main__":
    main()
