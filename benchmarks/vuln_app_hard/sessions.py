"""Session storage backed by the cache layer."""
import time
from cache import load_session_blob, store_session_blob


def create_session(user_id: str) -> str:
    session_id = f"sess-{user_id}-{int(time.time())}"
    store_session_blob(session_id, {"user_id": user_id, "created": time.time()})
    return session_id


def get_session(session_id: str):
    # sessions are returned as-is: no timeout, no idle check
    return load_session_blob(session_id)
