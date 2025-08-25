# Duplicate Code Analysis - Round 2

## 1. JSON Response Patterns (HIGH PRIORITY)

### Duplicate Error Responses
Found **38 instances** of duplicate error response patterns in `views.py`:
```python
# Pattern repeated 38 times with minor variations:
JsonResponse({'status': 'error', 'error': str(e)}, status=500)
JsonResponse({'status': 'error', 'error': 'Some error message'}, status=400)
```

### Duplicate Success Responses
Found **9 instances** of success response patterns:
```python
JsonResponse({'status': 'success'})
JsonResponse({'status': 'success', 'message': 'Some message'})
```

**Recommendation:** Create a response utility module:
```python
# samples/utils/responses.py
def error_response(message, status=400):
    return JsonResponse({'status': 'error', 'error': message}, status=status)

def success_response(message=None, data=None):
    response = {'status': 'success'}
    if message:
        response['message'] = message
    if data:
        response.update(data)
    return JsonResponse(response)
```

## 2. Microsoft Authentication Pattern (HIGH PRIORITY)

### Duplicate Authentication Code
Found in 4 files with identical pattern:
- `samples/EditExcelSharepoint.py` (lines 152-176)
- `samples/email_utils.py` (lines 53-81)
- `samples/CreateOppFolderSharepoint.py` (lines 61-82)
- `samples/management/commands/manual_auth.py` (lines 19-36)

Each file repeats this pattern:
```python
cache = get_token_cache()
app = msal.PublicClientApplication(
    client_id=AZURE_CLIENT_ID,
    authority=authority,
    token_cache=cache
)
accounts = app.get_accounts(username=AZURE_USERNAME)
if accounts:
    result = app.acquire_token_silent(scopes, account=accounts[0])
    if result and "access_token" in result:
        return result["access_token"]
# Device flow code...
```

**Recommendation:** Create an authentication service:
```python
# samples/services/auth_service.py
class MicrosoftAuthService:
    @staticmethod
    def get_access_token(scopes):
        # Centralized authentication logic
```

## 3. Date Formatting (MEDIUM PRIORITY)

### Duplicate Date Format Conversion
Found **7 instances** of the same date formatting:
```python
date_received.strftime('%Y-%m-%d')
```

**Recommendation:** Create date utilities:
```python
# samples/utils/date_utils.py
def format_date_for_display(date):
    return date.strftime('%Y-%m-%d') if date else ''
```

## 4. Rclone Command Execution (MEDIUM PRIORITY)

### Duplicate Rclone Patterns
Found in `tasks.py` with repeated patterns:
- Lines 64-76 (delete operation)
- Lines 445-473 (copy operation)
- Lines 488-501 (purge operation)

Each follows this pattern:
```python
rclone_executable = settings.RCLONE_EXECUTABLE
logger.info(f"Using rclone executable at: {rclone_executable}")
result = subprocess.run(
    [rclone_executable, 'command', ...],
    check=True,
    capture_output=True,
    text=True
)
logger.debug(f"rclone stdout: {result.stdout}")
if result.stderr:
    logger.error(f"rclone stderr: {result.stderr}")
```

**Recommendation:** Create rclone utility:
```python
# samples/utils/rclone_utils.py
class RcloneManager:
    def execute_command(self, command, *args):
        # Centralized rclone execution
```

## 5. File Existence Checking (LOW PRIORITY)

### Duplicate File Check Pattern
Found **4 instances** of similar file checking:
```python
if not os.path.exists(file_path):
    logger.error(f"File not found at: {file_path}")
    # Handle error
```

**Recommendation:** Create file utilities:
```python
# samples/utils/file_utils.py
def ensure_file_exists(file_path, error_message=None):
    if not os.path.exists(file_path):
        msg = error_message or f"File not found at: {file_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)
    return True
```

## 6. SharePoint API Headers (LOW PRIORITY)

### Duplicate Header Construction
Multiple places construct the same headers:
```python
headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}
```

**Recommendation:** Centralize in sharepoint_config:
```python
def get_graph_api_headers(token):
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
```

## Summary Statistics

| Pattern | Instances | Files Affected | Priority |
|---------|-----------|----------------|----------|
| JSON Responses | 47 | 1 | HIGH |
| MS Auth | 4 | 4 | HIGH |
| Date Formatting | 7 | 2 | MEDIUM |
| Rclone Commands | 3 | 1 | MEDIUM |
| File Checks | 4 | 3 | LOW |
| API Headers | ~10 | 3 | LOW |

## Estimated Refactoring Impact

- **Lines of code that can be removed:** ~300-400
- **Functions that can be consolidated:** ~15-20
- **Improved testability:** High (centralized utilities are easier to mock)
- **Reduced maintenance burden:** ~50% for affected code

## Recommended Implementation Order

1. **Phase 1:** JSON Response utilities (1 hour)
2. **Phase 2:** Microsoft Authentication service (2-3 hours)
3. **Phase 3:** Rclone and Date utilities (1-2 hours)
4. **Phase 4:** File and API utilities (1 hour)

Total estimated time: 5-7 hours of refactoring