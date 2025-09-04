#!/bin/bash

# Sample Database Management System - Service Setup Script
# This script sets up systemd services and cron jobs for the Sample Database

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration variables
PROJECT_DIR="/home/jls/Desktop/SampleDatabase"
VENV_DIR="$PROJECT_DIR/venv"
USER="jls"
PYTHON_BIN="$VENV_DIR/bin/python"
CELERY_BIN="$VENV_DIR/bin/celery"
GUNICORN_BIN="$VENV_DIR/bin/gunicorn"

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

# Check if running as root (needed for systemd service installation)
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check if project directory exists
    if [ ! -d "$PROJECT_DIR" ]; then
        print_error "Project directory not found: $PROJECT_DIR"
        exit 1
    fi
    print_status "Project directory found"
    
    # Check if virtual environment exists
    if [ ! -d "$VENV_DIR" ]; then
        print_error "Virtual environment not found: $VENV_DIR"
        print_warning "Please create virtual environment first: python -m venv venv"
        exit 1
    fi
    print_status "Virtual environment found"
    
    # Check if Redis is installed
    if ! command -v redis-cli &> /dev/null; then
        print_warning "Redis not found. Installing Redis..."
        apt-get update && apt-get install -y redis-server
    fi
    print_status "Redis is available"
    
    # Check if user exists
    if ! id "$USER" &>/dev/null; then
        print_error "User $USER does not exist"
        print_warning "Please update the USER variable in this script"
        exit 1
    fi
    print_status "User $USER exists"
}

# Create log directory
create_log_directory() {
    print_header "Creating Log Directory"
    
    LOG_DIR="$PROJECT_DIR/logs"
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR"
        chown -R "$USER:$USER" "$LOG_DIR"
        print_status "Created log directory: $LOG_DIR"
    else
        print_status "Log directory already exists"
    fi
}

# Install Django systemd service
install_django_service() {
    print_header "Installing Django Service"
    
    cat > /etc/systemd/system/django-sampledb.service << EOF
[Unit]
Description=Django Sample Database
After=network.target

[Service]
Type=forking
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$GUNICORN_BIN \\
    --workers 3 \\
    --bind 0.0.0.0:8000 \\
    --daemon \\
    --pid /tmp/gunicorn-sampledb.pid \\
    --access-logfile $PROJECT_DIR/logs/gunicorn-access.log \\
    --error-logfile $PROJECT_DIR/logs/gunicorn-error.log \\
    inventory_system.wsgi:application
ExecReload=/bin/kill -s HUP \$MAINPID
ExecStop=/bin/kill -s TERM \$MAINPID
PIDFile=/tmp/gunicorn-sampledb.pid
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    print_status "Django service file created"
}

# Install Celery systemd service
install_celery_service() {
    print_header "Installing Celery Service"
    
    cat > /etc/systemd/system/celery-sampledb.service << EOF
[Unit]
Description=Celery Sample Database Worker
After=network.target redis.service

[Service]
Type=forking
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$CELERY_BIN \\
    multi start worker1 worker2 worker3 \\
    -A inventory_system \\
    --pidfile=/tmp/celery-sampledb_%n.pid \\
    --logfile=$PROJECT_DIR/logs/celery_%n.log \\
    --loglevel=info
ExecStop=$CELERY_BIN \\
    multi stopwait worker1 worker2 worker3 \\
    --pidfile=/tmp/celery-sampledb_%n.pid
ExecReload=$CELERY_BIN \\
    multi restart worker1 worker2 worker3 \\
    -A inventory_system \\
    --pidfile=/tmp/celery-sampledb_%n.pid \\
    --logfile=$PROJECT_DIR/logs/celery_%n.log \\
    --loglevel=info
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    print_status "Celery service file created"
}

# Setup cron jobs
setup_cron_jobs() {
    print_header "Setting Up Cron Jobs"
    
    # Create a temporary file for cron jobs
    CRON_FILE="/tmp/sampledb_cron"
    
    # Get existing crontab for user (if any)
    su - $USER -c "crontab -l 2>/dev/null" > $CRON_FILE || true
    
    # Add new cron jobs if they don't exist
    
    # Database backup - Daily at 2 AM
    if ! grep -q "backup_database.py" $CRON_FILE; then
        echo "0 2 * * * cd $PROJECT_DIR && $PYTHON_BIN backup_database.py >> $PROJECT_DIR/logs/backup.log 2>&1" >> $CRON_FILE
        print_status "Added database backup cron job (daily at 2 AM)"
    else
        print_warning "Database backup cron job already exists"
    fi
    
    # SharePoint info population - Every hour
    if ! grep -q "populate_sharepoint_info" $CRON_FILE; then
        echo "0 * * * * cd $PROJECT_DIR && $PYTHON_BIN manage.py populate_sharepoint_info >> $PROJECT_DIR/logs/sharepoint_populate.log 2>&1" >> $CRON_FILE
        print_status "Added SharePoint info population cron job (hourly)"
    else
        print_warning "SharePoint info population cron job already exists"
    fi
    
    # Health monitoring - Every 5 minutes
    if ! grep -q "monitor_health.py" $CRON_FILE; then
        echo "*/5 * * * * cd $PROJECT_DIR && $PYTHON_BIN monitor_health.py >> $PROJECT_DIR/logs/health_monitor.log 2>&1" >> $CRON_FILE
        print_status "Added health monitoring cron job (every 5 minutes)"
    else
        print_warning "Health monitoring cron job already exists"
    fi
    
    # Weekly audit report - Mondays at 8 AM
    if ! grep -q "send_weekly_audit_report" $CRON_FILE; then
        echo "0 8 * * 1 cd $PROJECT_DIR && $PYTHON_BIN manage.py send_weekly_audit_report >> $PROJECT_DIR/logs/weekly_audit.log 2>&1" >> $CRON_FILE
        print_status "Added weekly audit report cron job (Mondays at 8 AM)"
    else
        print_warning "Weekly audit report cron job already exists"
    fi
    
    # Install the new crontab for the user
    su - $USER -c "crontab $CRON_FILE"
    rm $CRON_FILE
    
    print_status "Cron jobs installed for user $USER"
}

# Enable and start services
enable_services() {
    print_header "Enabling and Starting Services"
    
    # Reload systemd daemon
    systemctl daemon-reload
    print_status "Systemd daemon reloaded"
    
    # Enable services to start on boot
    systemctl enable django-sampledb.service
    print_status "Django service enabled"
    
    systemctl enable celery-sampledb.service
    print_status "Celery service enabled"
    
    # Start Redis if not running
    if ! systemctl is-active --quiet redis; then
        systemctl start redis
        systemctl enable redis
        print_status "Redis service started and enabled"
    else
        print_status "Redis already running"
    fi
    
    # Start services
    systemctl start celery-sampledb.service
    print_status "Celery service started"
    
    systemctl start django-sampledb.service
    print_status "Django service started"
}

# Check service status
check_service_status() {
    print_header "Service Status Check"
    
    echo "Django Service:"
    systemctl status django-sampledb.service --no-pager | head -n 10
    echo ""
    
    echo "Celery Service:"
    systemctl status celery-sampledb.service --no-pager | head -n 10
    echo ""
    
    echo "Redis Service:"
    systemctl status redis --no-pager | head -n 10
}

# Display cron jobs
display_cron_jobs() {
    print_header "Installed Cron Jobs"
    
    echo "Cron jobs for user $USER:"
    su - $USER -c "crontab -l" || print_warning "No cron jobs found"
}

# Create helper scripts
create_helper_scripts() {
    print_header "Creating Helper Scripts"
    
    # Create service management script
    cat > "$PROJECT_DIR/manage_services.sh" << 'EOF'
#!/bin/bash

# Service Management Helper Script

case "$1" in
    start)
        echo "Starting Sample Database services..."
        sudo systemctl start redis
        sudo systemctl start celery-sampledb
        sudo systemctl start django-sampledb
        echo "Services started"
        ;;
    stop)
        echo "Stopping Sample Database services..."
        sudo systemctl stop django-sampledb
        sudo systemctl stop celery-sampledb
        echo "Services stopped (Redis left running)"
        ;;
    restart)
        echo "Restarting Sample Database services..."
        sudo systemctl restart celery-sampledb
        sudo systemctl restart django-sampledb
        echo "Services restarted"
        ;;
    status)
        echo "Sample Database Service Status:"
        echo "=============================="
        echo "Django: $(systemctl is-active django-sampledb)"
        echo "Celery: $(systemctl is-active celery-sampledb)"
        echo "Redis:  $(systemctl is-active redis)"
        ;;
    logs)
        echo "Showing recent logs (use Ctrl+C to exit)..."
        sudo journalctl -u django-sampledb -u celery-sampledb -f
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
EOF
    
    chmod +x "$PROJECT_DIR/manage_services.sh"
    chown "$USER:$USER" "$PROJECT_DIR/manage_services.sh"
    print_status "Created manage_services.sh helper script"
    
    # Create development mode script
    cat > "$PROJECT_DIR/run_development.sh" << EOF
#!/bin/bash

# Development Mode Script
# Stops production services and runs development server

echo "Stopping production services..."
sudo systemctl stop django-sampledb
sudo systemctl stop celery-sampledb

echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

echo "Starting Redis if not running..."
sudo systemctl start redis

echo "Starting Celery in development mode..."
celery -A inventory_system worker --loglevel=info &
CELERY_PID=\$!

echo "Starting Django development server..."
python manage.py runserver 0.0.0.0:8000

echo "Stopping Celery worker..."
kill \$CELERY_PID

echo "Development session ended"
EOF
    
    chmod +x "$PROJECT_DIR/run_development.sh"
    chown "$USER:$USER" "$PROJECT_DIR/run_development.sh"
    print_status "Created run_development.sh helper script"
}

# Main installation function
main() {
    print_header "Sample Database Service Installation"
    
    echo "This script will install:"
    echo "  - Django systemd service"
    echo "  - Celery systemd service"
    echo "  - Cron jobs for automation"
    echo "  - Helper scripts"
    echo ""
    read -p "Do you want to continue? (y/n): " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "Installation cancelled"
        exit 0
    fi
    
    check_root
    check_prerequisites
    create_log_directory
    install_django_service
    install_celery_service
    setup_cron_jobs
    enable_services
    create_helper_scripts
    
    print_header "Installation Complete!"
    
    check_service_status
    display_cron_jobs
    
    print_header "Next Steps"
    echo "1. Verify the services are running:"
    echo "   sudo systemctl status django-sampledb"
    echo "   sudo systemctl status celery-sampledb"
    echo ""
    echo "2. Check the application:"
    echo "   curl http://localhost:8000/health/"
    echo ""
    echo "3. View logs:"
    echo "   sudo journalctl -u django-sampledb -f"
    echo "   sudo journalctl -u celery-sampledb -f"
    echo ""
    echo "4. Use helper scripts:"
    echo "   ./manage_services.sh {start|stop|restart|status|logs}"
    echo "   ./run_development.sh  (for development mode)"
    echo ""
    echo "5. Configure environment variables in .env file"
    echo ""
    print_status "Setup complete! Services are running."
}

# Run main function
main