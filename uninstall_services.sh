#!/bin/bash

# Sample Database Management System - Service Uninstall Script
# This script removes systemd services and cron jobs for the Sample Database

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration variables
PROJECT_DIR="/home/jls/Desktop/SampleDatabase"
USER="jls"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_header() {
    echo ""
    echo "========================================="
    echo "$1"
    echo "========================================="
    echo ""
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Stop services
stop_services() {
    print_header "Stopping Services"
    
    if systemctl is-active --quiet django-sampledb; then
        systemctl stop django-sampledb
        print_status "Django service stopped"
    else
        print_warning "Django service not running"
    fi
    
    if systemctl is-active --quiet celery-sampledb; then
        systemctl stop celery-sampledb
        print_status "Celery service stopped"
    else
        print_warning "Celery service not running"
    fi
}

# Disable services
disable_services() {
    print_header "Disabling Services"
    
    if systemctl list-unit-files | grep -q django-sampledb; then
        systemctl disable django-sampledb
        print_status "Django service disabled"
    fi
    
    if systemctl list-unit-files | grep -q celery-sampledb; then
        systemctl disable celery-sampledb
        print_status "Celery service disabled"
    fi
}

# Remove service files
remove_service_files() {
    print_header "Removing Service Files"
    
    if [ -f /etc/systemd/system/django-sampledb.service ]; then
        rm /etc/systemd/system/django-sampledb.service
        print_status "Django service file removed"
    else
        print_warning "Django service file not found"
    fi
    
    if [ -f /etc/systemd/system/celery-sampledb.service ]; then
        rm /etc/systemd/system/celery-sampledb.service
        print_status "Celery service file removed"
    else
        print_warning "Celery service file not found"
    fi
    
    # Reload systemd daemon
    systemctl daemon-reload
    print_status "Systemd daemon reloaded"
}

# Remove cron jobs
remove_cron_jobs() {
    print_header "Removing Cron Jobs"
    
    # Create a temporary file for cron jobs
    CRON_FILE="/tmp/sampledb_cron_remove"
    
    # Get existing crontab for user
    su - $USER -c "crontab -l 2>/dev/null" > $CRON_FILE || {
        print_warning "No crontab found for user $USER"
        return
    }
    
    # Remove Sample Database related cron jobs
    ORIGINAL_LINES=$(wc -l < $CRON_FILE)
    
    # Remove each cron job pattern
    sed -i '/backup_database.py/d' $CRON_FILE
    sed -i '/populate_sharepoint_info/d' $CRON_FILE
    sed -i '/monitor_health.py/d' $CRON_FILE
    sed -i '/send_weekly_audit_report/d' $CRON_FILE
    
    REMAINING_LINES=$(wc -l < $CRON_FILE)
    REMOVED_LINES=$((ORIGINAL_LINES - REMAINING_LINES))
    
    if [ $REMOVED_LINES -gt 0 ]; then
        # Install the updated crontab
        su - $USER -c "crontab $CRON_FILE"
        print_status "Removed $REMOVED_LINES Sample Database cron job(s)"
    else
        print_warning "No Sample Database cron jobs found"
    fi
    
    rm $CRON_FILE
}

# Remove helper scripts
remove_helper_scripts() {
    print_header "Removing Helper Scripts"
    
    if [ -f "$PROJECT_DIR/manage_services.sh" ]; then
        rm "$PROJECT_DIR/manage_services.sh"
        print_status "Removed manage_services.sh"
    else
        print_warning "manage_services.sh not found"
    fi
    
    if [ -f "$PROJECT_DIR/run_development.sh" ]; then
        rm "$PROJECT_DIR/run_development.sh"
        print_status "Removed run_development.sh"
    else
        print_warning "run_development.sh not found"
    fi
}

# Clean up PID files
cleanup_pid_files() {
    print_header "Cleaning Up PID Files"
    
    # Remove Gunicorn PID file
    if [ -f /tmp/gunicorn-sampledb.pid ]; then
        rm /tmp/gunicorn-sampledb.pid
        print_status "Removed Gunicorn PID file"
    fi
    
    # Remove Celery PID files
    for pid_file in /tmp/celery-sampledb_*.pid; do
        if [ -f "$pid_file" ]; then
            rm "$pid_file"
            print_status "Removed Celery PID file: $(basename $pid_file)"
        fi
    done
}

# Main uninstall function
main() {
    print_header "Sample Database Service Uninstallation"
    
    echo "This script will remove:"
    echo "  - Django systemd service"
    echo "  - Celery systemd service"
    echo "  - Cron jobs for automation"
    echo "  - Helper scripts"
    echo "  - PID files"
    echo ""
    echo "NOTE: This will NOT remove:"
    echo "  - Application code"
    echo "  - Database files"
    echo "  - Log files"
    echo "  - Virtual environment"
    echo "  - Redis service"
    echo ""
    read -p "Do you want to continue? (y/n): " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "Uninstallation cancelled"
        exit 0
    fi
    
    check_root
    stop_services
    disable_services
    remove_service_files
    remove_cron_jobs
    remove_helper_scripts
    cleanup_pid_files
    
    print_header "Uninstallation Complete!"
    
    echo "Services and automation have been removed."
    echo ""
    echo "To completely remove the application, you can:"
    echo "  1. Remove the project directory:"
    echo "     rm -rf $PROJECT_DIR"
    echo ""
    echo "  2. Remove Redis (if not needed for other applications):"
    echo "     apt-get remove redis-server"
    echo ""
    print_status "Uninstallation complete!"
}

# Run main function
main