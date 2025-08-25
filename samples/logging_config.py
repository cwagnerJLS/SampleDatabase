import os
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / 'logs'

LOGS_DIR.mkdir(exist_ok=True)

LOG_FILES = {
    'django': LOGS_DIR / 'django.log',
    'django_error': LOGS_DIR / 'django_error.log',
    'celery': LOGS_DIR / 'celery.log',
    'celery_worker': LOGS_DIR / 'celery_worker.log',
    'backup': LOGS_DIR / 'backup.log',
    'health_monitor': LOGS_DIR / 'health_monitor.log',
    'rclone_sync': LOGS_DIR / 'rclone_sync.log',
    'sharepoint': LOGS_DIR / 'sharepoint.log',
    'email': LOGS_DIR / 'email.log',
    'debug': LOGS_DIR / 'debug.log',
}

def get_logger(name, log_file_key='debug', level=logging.INFO):
    """
    Get a configured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        log_file_key: Key from LOG_FILES dict for the log file to use
        level: Logging level
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(level)
        
        log_file = LOG_FILES.get(log_file_key, LOG_FILES['debug'])
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
    
    return logger

DJANGO_LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{asctime} - {name} - {levelname} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': str(LOG_FILES['debug']),
            'formatter': 'simple',
        },
        'celery_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': str(LOG_FILES['celery']),
            'formatter': 'simple',
        },
        'sharepoint_file': {
            'level': 'INFO', 
            'class': 'logging.FileHandler',
            'filename': str(LOG_FILES['sharepoint']),
            'formatter': 'simple',
        },
        'email_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': str(LOG_FILES['email']),
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
        'celery': {
            'handlers': ['celery_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'samples.sharepoint': {
            'handlers': ['sharepoint_file'],
            'level': 'INFO', 
            'propagate': False,
        },
        'samples.email': {
            'handlers': ['email_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['file'],
        'level': 'INFO',
    },
}