"""Auth middleware."""
from functools import wraps
from tokens import verify_token


def require_auth(handler):
    @wraps(handler)
    def wrapper(request, *args, **kwargs):
        claims = verify_token(request.headers.get("Authorization", ""))
        request.user = claims["user_id"]
        return handler(request, *args, **kwargs)
    return wrapper
