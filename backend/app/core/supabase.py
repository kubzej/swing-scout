from supabase import create_client, Client
from typing import Optional
import os

_client: Optional[Client] = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _client = create_client(url, key)
    return _client


# Convenience alias — use get_supabase() in code that runs at request time,
# use supabase directly only in module-level code that has .env loaded.
supabase = get_supabase
