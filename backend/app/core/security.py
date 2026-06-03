from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _get_key(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header:
        return str(hash(auth_header))
    return get_remote_address(request)


limiter = Limiter(key_func=_get_key, default_limits=["200/minute"])
