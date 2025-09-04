# Sample Database Management System

A comprehensive Django-based laboratory sample management system with SharePoint integration, automated workflows, and real-time audit tracking for test engineering environments.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [System Architecture](#system-architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Database Schema](#database-schema)
- [SharePoint Integration](#sharepoint-integration)
- [Automation & Scheduled Tasks](#automation--scheduled-tasks)
- [Deployment](#deployment)
- [Monitoring & Health Checks](#monitoring--health-checks)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

## Overview

The Sample Database Management System is a production-ready web application designed for test laboratories to manage physical samples, track their storage locations, schedule audits, and maintain comprehensive documentation through SharePoint integration. The system automates document generation, email notifications, and provides real-time visibility into sample status across the organization.

### Key Capabilities
- **Unique Sample Tracking**: 4-digit unique IDs with QR code labels
- **Storage Management**: 8 predefined storage locations with automatic audit scheduling
- **SharePoint Integration**: Automated folder creation and Excel documentation
- **Audit System**: Color-coded visual indicators for overdue/upcoming audits
- **Image Management**: Dual storage system (thumbnails + full-size) with SharePoint sync
- **Activity Logging**: Comprehensive audit trail of all user actions
- **Email Notifications**: Automated notifications via Microsoft Graph API

## Features

### Sample Management
- **Batch Creation**: Create multiple samples with auto-generated unique IDs (1000-9999 range)
- **Opportunity Grouping**: Organize samples by project/customer opportunities
- **Storage Tracking**: 8 storage locations with different audit cycles:
  - 3-week cycle: Cooler #2, Walk-in Fridge
  - 8-week cycle: Freezer #5, Freezer #9, Walk-in Freezer, Dry Food Storage, Empty Case Storage
- **Visual Status Indicators**:
  - 🔴 Red: Overdue for audit
  - 🟡 Yellow: Due within 7 days
  - 🟢 Green: Audit status OK

### Document Management
- **SharePoint Folders**: Automatic creation with proper metadata
- **Excel Documentation**: Real-time updates to tracking spreadsheets
- **Template System**: Automated copying of documentation templates
- **Archive/Restore**: Automatic archival when samples removed, restoration when new samples added
- **Export Function**: Bulk export of sample documentation to Sales Engineering

### Label Generation
- **QR Code Labels**: 101.6mm x 50.8mm PDF labels with embedded QR codes
- **Direct Printing**: Integration with system printer via `lpr` command
- **Batch Printing**: Print multiple labels in single operation
- **Mobile Scanning**: QR codes link directly to sample management page

### Image Management
- **Dual Storage System**:
  - Thumbnails (200x200px) for quick preview
  - Full-size images for detailed view
- **SharePoint Sync**: Automatic upload to SharePoint document libraries
- **Opportunity Organization**: Images grouped by opportunity number
- **Bulk Operations**: Upload/delete multiple images at once

### Audit & Compliance
- **Automatic Scheduling**: Audit dates calculated based on storage type
- **Visual Warnings**: Color-coded rows in sample listings
- **Weekly Reports**: Automated email reports every Monday at 8 AM
- **Activity Tracking**: 20+ tracked actions with user attribution
- **Compliance Dashboard**: Real-time view of audit status

## System Architecture

### Technology Stack
- **Backend**: Django 5.1.1 with Python 3.11+
- **Task Queue**: Celery 5.4.0 with Redis 5.2.0
- **Database**: SQLite (production) with backup automation
- **Frontend**: Django templates with jQuery, Select2
- **File Storage**: Local filesystem with SharePoint synchronization
- **Authentication**: Microsoft Authentication Library (MSAL)
- **Email**: Microsoft Graph API integration
- **Web Server**: Gunicorn with 3 workers

### Component Architecture
```
┌─────────────────────────────────────────────────┐
│                 Web Interface                    │
│         (Django Templates + jQuery)              │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│              Django Application                  │
│                  (samples)                       │
├──────────────────────────────────────────────────┤
│  Models  │  Views  │  Tasks  │  Services        │
└─────┬────────┬──────────┬──────────┬────────────┘
      │        │          │          │
┌─────▼────────▼──────────▼──────────▼────────────┐
│              Celery Task Queue                   │
│                (Redis Backend)                   │
└──────────────────────────────────────────────────┘
      │
┌─────▼────────────────────────────────────────────┐
│           External Integrations                  │
├──────────────────────────────────────────────────┤
│ SharePoint │ Graph API │ Email │ rclone         │
└──────────────────────────────────────────────────┘
```

## Installation

### Prerequisites
- Python 3.11 or higher
- Redis server
- rclone configured for SharePoint
- Microsoft Azure AD application credentials
- Network access to SharePoint sites

### Setup Steps

1. **Clone the repository**
```bash
cd /home/jls/Desktop
git clone https://github.com/cwagnerJLS/SampleDatabase.git
cd SampleDatabase
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
Create a `.env` file with required configurations:
```env
# Azure AD Configuration
AZURE_CLIENT_ID=your_client_id
AZURE_TENANT_ID=your_tenant_id
AZURE_USERNAME=your_username

# SharePoint Library IDs
TEST_ENGINEERING_LIBRARY_ID=your_test_engineering_library_id
SALES_ENGINEERING_LIBRARY_ID=your_sales_engineering_library_id

# Email Configuration
TEST_MODE_EMAIL=test@example.com
SHAREPOINT_EMAIL=sharepoint@example.com

# User Access Control
VALID_USERS=user1,user2,user3
ADMIN_USERS=admin1,admin2
```

5. **Run database migrations**
```bash
python manage.py migrate
```

6. **Create superuser (optional)**
```bash
python manage.py createsuperuser
```

7. **Configure rclone for SharePoint**
```bash
rclone config
# Create remote named "TestLabSamples"
```

8. **Start Redis server**
```bash
redis-server
```

9. **Start Celery worker**
```bash
celery -A inventory_system worker --loglevel=info
```

10. **Run development server**
```bash
python manage.py runserver 0.0.0.0:8000
```

## Configuration

### Key Configuration Files

#### `inventory_system/settings.py`
- Django settings with production configurations
- Database, static files, and media settings
- Middleware and authentication configuration

#### `samples/sharepoint_config.py`
- Centralized SharePoint and Azure AD settings
- Environment variable management
- API endpoint configurations

#### `samples/logging_config.py`
- Comprehensive logging setup
- Multiple log files for different components:
  - `django.log`: Main application logs
  - `celery_worker.log`: Task queue logs
  - `sharepoint.log`: SharePoint operations
  - `email.log`: Email notifications
  - `health_monitor.log`: System health checks

### Storage Configuration
- **Thumbnails**: `media/Thumbnails/`
- **Full-size Images**: `media/Full Size Images/`
- **Labels**: `Labels/`
- **Database Backups**: Synced to SharePoint `_Backups` folder

## Usage

### Web Interface Access
Navigate to `http://192.168.6.91:8000` (or configured address)

### User Identification
1. First-time users select their name from the dropdown
2. System stores user identity in session
3. All actions are logged with user attribution

### Core Workflows

#### Creating Samples
1. Navigate to Create Sample page
2. Select Customer, RSM, and Opportunity
3. Enter quantity and date received
4. System generates unique IDs automatically
5. SharePoint folder created if new opportunity
6. Email notification sent to stakeholders

#### Managing Storage & Audits
1. Assign storage location to trigger audit scheduling
2. System calculates due date based on location type
3. Visual indicators show audit status:
   - Red: Overdue
   - Yellow: Due within 7 days
   - Normal: No immediate action needed
4. Mark samples as audited to reset cycle

#### Uploading Images
1. Click Upload/View on sample row
2. Select multiple images
3. Thumbnails generated automatically
4. Full-size images synced to SharePoint
5. Images organized by opportunity

#### Printing Labels
1. Select samples to print
2. Click Print Labels
3. PDF generated with QR codes
4. Sent to default printer automatically

## API Documentation

### Main Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Home page - redirects to view samples |
| `/create_sample/` | GET/POST | Create new samples interface |
| `/view_samples/` | GET | List all samples |
| `/manage_sample/<id>/` | GET/POST | Individual sample management |
| `/health/` | GET | Health check endpoint |
| `/log/` | GET | Activity log viewer |

### AJAX Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/update_sample_location/` | POST | Update storage location |
| `/upload_files/` | POST | Upload sample images |
| `/get_sample_images/` | GET | Retrieve image list |
| `/delete_sample_image/` | POST | Delete specific image |
| `/batch_audit/` | POST | Mark multiple samples as audited |
| `/export_documentation/` | POST | Export to Sales Engineering |
| `/validate_delete_samples/` | POST | Check if samples can be deleted |
| `/delete_samples/` | POST | Delete samples |
| `/remove_from_inventory/` | POST | Archive samples |
| `/handle_print_request/` | POST | Generate and print labels |

### Response Format
All API endpoints return JSON responses:
```json
{
  "status": "success|error",
  "message": "Operation result message",
  "data": {}  // Optional data payload
}
```

## Database Schema

### Core Models

#### Sample
- `unique_id`: 4-digit unique identifier (CharField)
- `opportunity_number`: Links to opportunity (CharField)
- `customer`: Customer name (CharField)
- `rsm`: Regional Sales Manager (CharField)
- `date_received`: Sample receipt date (DateField)
- `description`: Sample description (TextField)
- `storage_location`: Current storage location (CharField)
- `audit`: Audit completed flag (BooleanField)
- `audit_due_date`: Calculated audit date (DateField)
- `last_audit_date`: Last audit timestamp (DateTimeField)
- `location_assigned_date`: Storage assignment timestamp (DateTimeField)
- `created_by`: User who created (CharField)
- `modified_by`: Last modifier (CharField)

#### Opportunity
- `opportunity_number`: Unique identifier (CharField)
- `customer`: Customer name (CharField)
- `rsm`: Regional Sales Manager (CharField)
- `description`: Project description (TextField)
- `sample_info_url`: SharePoint URL (URLField)
- `sample_info_id`: SharePoint folder ID (CharField)
- `new`: New opportunity flag (BooleanField)
- `update`: Needs update flag (BooleanField)
- `export_count`: Number of exports (IntegerField)
- `last_export_date`: Last export timestamp (DateTimeField)

#### SampleImage
- `sample`: Foreign key to Sample
- `image`: Image file (ImageField)
- `thumbnail`: Thumbnail file (ImageField)
- `full_size_uploaded`: SharePoint sync flag (BooleanField)
- `uploaded_at`: Upload timestamp (DateTimeField)

#### ActivityLog
- `user`: User identifier (CharField)
- `action`: Action type (CharField)
- `details`: Action details (JSONField)
- `timestamp`: Action timestamp (DateTimeField)
- `ip_address`: User IP (GenericIPAddressField)
- `user_agent`: Browser info (TextField)

### Action Types
20+ tracked actions including:
- `sample_created`, `sample_deleted`
- `location_updated`, `audit_performed`
- `image_uploaded`, `image_deleted`
- `label_printed`, `export_initiated`
- `folder_created`, `email_sent`

## SharePoint Integration

### Architecture
- **Authentication**: MSAL device flow with token caching
- **Graph API**: Direct API calls for document operations
- **rclone**: File synchronization for images and backups
- **Folder Structure**:
  ```
  Test Engineering Library/
  ├── [Opportunity Number]/
  │   ├── Samples/
  │   │   ├── [Sample Images]
  │   │   └── ...
  │   └── [Documentation Template].xlsx
  └── _Archive/
      └── [Archived Opportunities]
  ```

### Key Operations

#### Folder Creation
- Triggered on new opportunity
- Creates folder structure
- Copies documentation template
- Sets metadata properties

#### Excel Updates
- Reads existing sample IDs
- Updates with new samples
- Maintains formatting
- Preserves existing data

#### Image Sync
- Full-size images uploaded via Celery task
- rclone handles synchronization
- Maintains folder structure

#### Archive/Restore
- Automatic archival when samples removed
- Restoration when new samples added
- Preserves all documentation

## Automation & Scheduled Tasks

### Celery Tasks
35+ asynchronous tasks including:
- `create_sharepoint_folder_task`
- `copy_documentation_template_task`
- `update_excel_file_task`
- `send_email_task`
- `upload_images_to_sharepoint_task`
- `export_documentation_task`

### Task Chains
Complex workflows use Celery chains:
```python
chain(
    create_folder_task.s(),
    copy_template_task.s(),
    update_excel_task.s(),
    send_email_task.s()
).apply_async()
```

### Scheduled Jobs (via cron)
- **Database Backup**: Daily at 2 AM
- **SharePoint Info Population**: Hourly
- **Health Monitoring**: Every 5 minutes
- **Weekly Audit Report**: Mondays at 8 AM

## Deployment

### Production Environment
- **Server**: `192.168.6.91:8000`
- **OS**: Linux (Raspberry Pi)
- **Process Manager**: systemd services
- **Web Server**: Gunicorn with 3 workers
- **Database**: SQLite with automated backups

### Systemd Services

#### Django Service (`django-sampledb.service`)
```ini
[Unit]
Description=Django Sample Database
After=network.target

[Service]
Type=forking
User=jls
WorkingDirectory=/home/jls/Desktop/SampleDatabase
ExecStart=/home/jls/Desktop/SampleDatabase/venv/bin/gunicorn \
          --workers 3 --bind 0.0.0.0:8000 \
          --daemon --pid /tmp/gunicorn.pid \
          inventory_system.wsgi:application

[Install]
WantedBy=multi-user.target
```

#### Celery Service (`celery-sampledb.service`)
```ini
[Unit]
Description=Celery Sample Database Worker
After=network.target redis.service

[Service]
Type=forking
User=jls
WorkingDirectory=/home/jls/Desktop/SampleDatabase
ExecStart=/home/jls/Desktop/SampleDatabase/venv/bin/celery \
          multi start worker1 worker2 worker3 \
          -A inventory_system --pidfile=/tmp/celery_%n.pid

[Install]
WantedBy=multi-user.target
```

### Service Management
```bash
# Check status
sudo systemctl status django-sampledb
sudo systemctl status celery-sampledb

# Restart services
sudo systemctl restart django-sampledb
sudo systemctl restart celery-sampledb

# View logs
sudo journalctl -u django-sampledb -f
sudo journalctl -u celery-sampledb -f
```

## Monitoring & Health Checks

### Health Check System
- **Endpoint**: `/health/`
- **Frequency**: Every 5 minutes via cron
- **Components Checked**:
  - Django application availability
  - Database connectivity
  - Redis connection
  - SharePoint token validity

### Auto-Recovery
`monitor_health.py` implements progressive recovery:
1. **Level 1**: Retry 3 times with 10-second delays
2. **Level 2**: Restart Django service
3. **Level 3**: Restart Celery service
4. **Level 4**: System reboot (disabled by default)

### Monitoring Logs
- Location: `/home/jls/Desktop/SampleDatabase/logs/`
- Files:
  - `health_monitor.log`: Health check results
  - `django.log`: Application logs
  - `celery_worker.log`: Task execution
  - `sharepoint.log`: SharePoint operations
  - `email.log`: Email notifications

### Weekly Audit Reports
Automated reports include:
- Overdue audits
- Upcoming audits (7-day window)
- Samples without location
- Samples without images
- Incomplete documentation
- Unexported opportunities

## Development

### Development Setup
```bash
# Activate virtual environment
source venv/bin/activate

# Stop production services
sudo systemctl stop django-sampledb
sudo systemctl stop celery-sampledb

# Run development server
python manage.py runserver 0.0.0.0:8000

# Run Celery in development
celery -A inventory_system worker --loglevel=debug
```

### Code Structure
```
samples/
├── models.py           # Data models
├── views.py            # View controllers
├── tasks.py            # Celery tasks
├── middleware.py       # Custom middleware
├── activity_logger.py  # Activity tracking
├── email_utils.py      # Email functionality
├── label_utils.py      # Label generation
├── sharepoint_config.py # Configuration
├── services/           # Business logic
├── utils/              # Utility functions
├── management/         # Management commands
└── templates/          # HTML templates
```

### Testing
Currently no formal test suite. Recommended testing approach:
1. Use health check endpoint for basic validation
2. Test SharePoint integration with `ManualAuth.py`
3. Verify email delivery in test mode
4. Check audit calculations with sample data

### Database Management
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Backup database
python manage.py backup_database

# Restore from backup
python manage.py restore_backup backup_name.sql.gz
```

## Troubleshooting

### Common Issues

#### SharePoint Token Expiration
```bash
# Manually refresh tokens
python ManualAuth.py
```

#### Service Not Starting
```bash
# Check service status
sudo systemctl status django-sampledb
sudo journalctl -u django-sampledb -n 50

# Check port availability
sudo lsof -i :8000
```

#### Celery Tasks Not Executing
```bash
# Check Redis connection
redis-cli ping

# Monitor Celery workers
celery -A inventory_system events

# Purge task queue
celery -A inventory_system purge
```

#### Database Lock Issues
```bash
# Check for locks
fuser db.sqlite3

# Backup and restore
cp db.sqlite3 db.sqlite3.backup
python manage.py migrate --run-syncdb
```

### Log Analysis
```bash
# View recent errors
grep ERROR logs/django.log | tail -20

# Monitor SharePoint operations
tail -f logs/sharepoint.log

# Check email failures
grep "Failed to send" logs/email.log
```

### Performance Optimization
1. **Database**: Regular VACUUM operations on SQLite
2. **Images**: Ensure thumbnail generation is working
3. **Celery**: Monitor task queue length
4. **SharePoint**: Batch operations when possible

## Security Considerations

### Authentication & Authorization
- User identification via session storage
- Role-based access (VALID_USERS, ADMIN_USERS)
- Activity logging for audit trail

### Data Protection
- Environment variables for sensitive configuration
- Token caching with proper permissions
- Database backups encrypted during transfer

### Network Security
- Internal network deployment (192.168.6.91)
- HTTPS recommended for production
- SharePoint access via OAuth 2.0

## License

Proprietary - JLS Automation

## Support

For issues, questions, or feature requests, contact the Test Engineering team.

## Changelog

See git commit history for detailed changes.

## Acknowledgments

Built with Django, Celery, and Microsoft Graph API.