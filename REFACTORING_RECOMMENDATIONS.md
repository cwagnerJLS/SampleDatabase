# Tasks.py Refactoring Recommendations

## Priority 1: Critical Improvements

### 1. Extract Common Email Logic
**Problem**: Duplicate code across 3 email tasks (lines 286-426)
**Solution**: Create a helper class or functions

```python
# samples/email_helpers.py
class EmailTaskHelper:
    @staticmethod
    def prepare_email_context(opportunity_number):
        """Get opportunity, RSM name, greeting, and CC list"""
        from .models import Opportunity, Sample
        from .email_utils import generate_email, NICKNAMES, TEST_LAB_GROUP
        
        opp = Opportunity.objects.get(opportunity_number=opportunity_number)
        if not opp.rsm:
            return None
            
        # Build CC list
        apps_eng_values = Sample.objects.filter(
            opportunity_number=opportunity_number
        ).values_list('apps_eng', flat=True).distinct()
        
        cc_list = TEST_LAB_GROUP.copy()
        for apps_eng_name in apps_eng_values:
            if apps_eng_name:
                apps_eng_email = generate_email(apps_eng_name)
                if apps_eng_email and apps_eng_email not in cc_list:
                    cc_list.append(apps_eng_email)
        
        # Get greeting name
        first_name = opp.rsm.split()[0]
        greeting_name = NICKNAMES.get(opp.rsm, first_name)
        
        return {
            'opportunity': opp,
            'greeting_name': greeting_name,
            'cc_list': cc_list,
            'rsm_email': get_rsm_email(opp.rsm)
        }
```

### 2. Consolidate SharePoint Utilities
**Problem**: Duplicate `find_folder_by_name` functions
**Solution**: Move to shared module

```python
# samples/utils/sharepoint_utils.py
class SharePointFolderManager:
    def __init__(self, access_token):
        self.access_token = access_token
    
    def find_folder_by_name(self, drive_id, parent_id, folder_name):
        """Centralized folder finding logic"""
        # Implementation here
    
    def list_children(self, drive_id, folder_id):
        """List items in folder"""
        # Implementation here
```

### 3. Simplify update_documentation_excels
**Problem**: 168-line function with complex nesting
**Solution**: Break into smaller functions

```python
@shared_task
def update_documentation_excels(opportunity_number=None):
    opportunities = get_opportunities_to_update(opportunity_number)
    
    for opp_num in opportunities:
        try:
            process_opportunity_documentation(opp_num)
        except Exception as e:
            logger.error(f"Failed to process {opp_num}: {e}")

def process_opportunity_documentation(opportunity_number):
    opp = Opportunity.objects.get(opportunity_number=opportunity_number)
    
    if not (opp.new or opp.update):
        return
    
    excel_handler = ExcelDocumentationHandler(opp)
    
    if opp.new:
        excel_handler.update_metadata()
        opp.new = False
    
    if opp.update:
        excel_handler.sync_sample_ids()
        opp.update = False
    
    opp.save()
```

## Priority 2: Performance Optimizations

### 1. Parallel Image Uploads
**Current**: Sequential uploads in loop
**Improved**: Use Celery group

```python
from celery import group

@shared_task
def upload_full_size_images_to_sharepoint(sample_image_ids):
    upload_tasks = group(
        upload_single_image.s(image_id) 
        for image_id in sample_image_ids
    )
    upload_tasks.apply_async()

@shared_task
def upload_single_image(sample_image_id):
    # Single image upload logic
```

### 2. Database Query Optimization
**Add select_related and prefetch_related**

```python
# Instead of:
apps_eng_values = Sample.objects.filter(
    opportunity_number=opportunity_number
).values_list('apps_eng', flat=True).distinct()

# Use:
samples = Sample.objects.filter(
    opportunity_number=opportunity_number
).select_related('opportunity').distinct('apps_eng')
```

### 3. Token Caching
**Current**: Multiple token requests
**Improved**: Cache tokens

```python
from django.core.cache import cache

def get_cached_access_token():
    token = cache.get('graph_api_token')
    if not token:
        token = get_access_token()
        # Cache for 50 minutes (tokens last 60)
        cache.set('graph_api_token', token, 3000)
    return token
```

## Priority 3: Code Quality Improvements

### 1. Add Retry Logic
```python
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def create_sharepoint_folder_task(self, opportunity_number, customer, rsm, description):
    try:
        create_sharepoint_folder(...)
    except Exception as exc:
        logger.error(f"Error attempt {self.request.retries}: {exc}")
        raise self.retry(exc=exc)
```

### 2. Use Constants
```python
# samples/constants.py
class ExcelConstants:
    WORKSHEET_NAME = 'Sheet1'
    DATA_START_ROW = 8
    METADATA_CELLS = {
        'CUSTOMER': 'B1',
        'RSM': 'B2', 
        'OPP_NUMBER': 'B3',
        'DESCRIPTION': 'B4'
    }
```

### 3. Transaction Management
```python
from django.db import transaction

@shared_task
def update_opportunity_flags(opportunity_number):
    with transaction.atomic():
        opp = Opportunity.objects.select_for_update().get(
            opportunity_number=opportunity_number
        )
        opp.new = False
        opp.update = False
        opp.save()
```

## Priority 4: Architectural Improvements

### 1. Task Chaining with Error Handling
```python
from celery import chain, chord

def process_new_opportunity(opp_number):
    workflow = chain(
        create_sharepoint_folder_task.s(opp_number),
        create_documentation_on_sharepoint_task.s(opp_number),
        update_documentation_excels.s(opp_number),
        send_documentation_completed_email.s(opp_number)
    ).on_error(handle_workflow_error.s(opp_number))
    
    workflow.apply_async()
```

### 2. Create Task Base Class
```python
from celery import Task

class SharePointTask(Task):
    autoretry_for = (ConnectionError, TimeoutError)
    retry_kwargs = {'max_retries': 3}
    retry_backoff = True
    
    def before_start(self, task_id, args, kwargs):
        self.token = get_cached_access_token()
```

### 3. Separate Concerns
- Move SharePoint operations to `sharepoint_tasks.py`
- Move email operations to `email_tasks.py`  
- Move archive operations to `archive_tasks.py`

## Implementation Plan

1. **Phase 1** (Week 1):
   - Extract email helper functions
   - Consolidate SharePoint utilities
   - Add retry logic to critical tasks

2. **Phase 2** (Week 2):
   - Break down large functions
   - Add constants module
   - Implement token caching

3. **Phase 3** (Week 3):
   - Optimize database queries
   - Implement parallel uploads
   - Add transaction management

4. **Phase 4** (Week 4):
   - Reorganize into separate task modules
   - Add comprehensive error handling
   - Write unit tests for refactored code

## Testing Strategy

1. Create test fixtures for each task type
2. Mock external API calls (SharePoint, email)
3. Test retry logic with simulated failures
4. Benchmark performance improvements
5. Ensure backwards compatibility

## Risk Mitigation

- Keep original tasks.py as backup
- Implement changes incrementally
- Test in staging environment first
- Monitor Celery task performance
- Have rollback plan ready