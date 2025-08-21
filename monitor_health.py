#!/usr/bin/env python3
"""
Health monitoring script for Django Sample Database server.
Checks if the server is responding and restarts services if needed.
"""

import requests
import time
import subprocess
import logging
from datetime import datetime
import os
import sys

# Configuration
HEALTH_URL = "http://localhost:8000/health/"
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds
REQUEST_TIMEOUT = 5  # seconds
LOG_FILE = "/home/jls/Desktop/SampleDatabase/health_monitor.log"

# Setup logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def check_health():
    """Check if the Django server is healthy."""
    try:
        response = requests.get(HEALTH_URL, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'healthy':
                return True, "Server is healthy"
            else:
                return False, f"Server unhealthy: {data}"
        else:
            return False, f"Server returned status code: {response.status_code}"
    except requests.exceptions.Timeout:
        return False, "Request timed out"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused - server may be down"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def restart_django_service():
    """Restart the Django service using systemd."""
    try:
        logging.info("Attempting to restart Django service...")
        
        # First, try to restart the Django service
        result = subprocess.run(
            ['sudo', 'systemctl', 'restart', 'django-sampledb'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            logging.info("Django service restarted successfully")
            return True
        else:
            logging.error(f"Failed to restart Django service: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logging.error("Service restart timed out")
        return False
    except Exception as e:
        logging.error(f"Error restarting service: {str(e)}")
        return False

def restart_celery_service():
    """Restart the Celery service if it exists."""
    try:
        # Check if Celery service exists
        check_result = subprocess.run(
            ['sudo', 'systemctl', 'status', 'celery-sampledb'],
            capture_output=True,
            text=True
        )
        
        if check_result.returncode in [0, 3]:  # 0=active, 3=inactive
            logging.info("Attempting to restart Celery service...")
            result = subprocess.run(
                ['sudo', 'systemctl', 'restart', 'celery-sampledb'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logging.info("Celery service restarted successfully")
                return True
            else:
                logging.error(f"Failed to restart Celery service: {result.stderr}")
                return False
        else:
            logging.info("Celery service not found, skipping...")
            return True
            
    except Exception as e:
        logging.error(f"Error restarting Celery: {str(e)}")
        return False

def system_reboot():
    """Reboot the system as a last resort."""
    try:
        logging.critical("Initiating system reboot as last resort...")
        subprocess.run(['sudo', 'reboot'], check=True)
        return True
    except Exception as e:
        logging.critical(f"Failed to reboot system: {str(e)}")
        return False

def main():
    """Main monitoring loop."""
    logging.info("=" * 50)
    logging.info("Starting health check monitor")
    
    # Perform health check with retries
    is_healthy = False
    last_error = ""
    
    for attempt in range(MAX_RETRIES):
        healthy, message = check_health()
        
        if healthy:
            logging.info(f"Health check passed: {message}")
            is_healthy = True
            break
        else:
            last_error = message
            logging.warning(f"Health check failed (attempt {attempt + 1}/{MAX_RETRIES}): {message}")
            
            if attempt < MAX_RETRIES - 1:
                logging.info(f"Waiting {RETRY_DELAY} seconds before retry...")
                time.sleep(RETRY_DELAY)
    
    # If health checks failed, attempt recovery
    if not is_healthy:
        logging.error(f"All health checks failed. Last error: {last_error}")
        
        # Step 1: Try restarting Django
        if restart_django_service():
            time.sleep(15)  # Give service time to start
            
            # Check if restart fixed the issue
            healthy, message = check_health()
            if healthy:
                logging.info("Django restart resolved the issue")
                return
        
        # Step 2: Try restarting Celery (which might be blocking Django)
        if restart_celery_service():
            time.sleep(10)
            
            # Check again
            healthy, message = check_health()
            if healthy:
                logging.info("Celery restart resolved the issue")
                return
        
        # Step 3: Last resort - reboot system
        # Only do this if we have a flag file to prevent reboot loops
        reboot_flag_file = "/tmp/sampledb_reboot_flag"
        
        if os.path.exists(reboot_flag_file):
            # Check if flag is recent (within last hour)
            flag_age = time.time() - os.path.getmtime(reboot_flag_file)
            if flag_age < 3600:  # 1 hour
                logging.critical("Recent reboot detected, avoiding reboot loop")
                return
        
        # Create/update reboot flag
        with open(reboot_flag_file, 'w') as f:
            f.write(str(datetime.now()))
        
        logging.critical("All recovery attempts failed, considering system reboot")
        # Uncomment the line below to enable system reboot
        # system_reboot()
    
    else:
        logging.info("Health check completed successfully")

if __name__ == "__main__":
    main()