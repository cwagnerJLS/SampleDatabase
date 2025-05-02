import os
from msal_extensions import FilePersistence, PersistedTokenCache

TOKEN_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "token_cache.json")

def get_token_cache():
    """
    Return a lock-protected, on-disk token cache.
    PersistedTokenCache auto-saves whenever MSAL changes the cache and
    uses an internal cross-platform file-lock, so no corruption occurs.
    """
    persistence = FilePersistence(os.path.abspath(TOKEN_CACHE_FILE))
    return PersistedTokenCache(persistence)
