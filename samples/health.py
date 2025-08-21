import json
from django.http import JsonResponse
from django.db import connection
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
@require_GET
def health_check(request):
    """
    Simple health check endpoint that verifies:
    1. Django is responding
    2. Database is accessible
    3. Returns current timestamp
    """
    health_status = {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'checks': {
            'django': True,
            'database': False
        }
    }
    
    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        health_status['checks']['database'] = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status['status'] = 'unhealthy'
        health_status['checks']['database'] = False
        health_status['error'] = str(e)
    
    # Return appropriate status code
    status_code = 200 if health_status['status'] == 'healthy' else 503
    
    return JsonResponse(health_status, status=status_code)