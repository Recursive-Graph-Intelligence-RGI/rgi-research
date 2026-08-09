"""Cache layer. Session blobs are pickled for flexibility."""
import pickle

_STORE = {}


def store_session_blob(session_id: str, data: dict) -> None:
    _STORE[session_id] = pickle.dumps(data)


def load_session_blob(session_id: str):
    blob = _STORE.get(session_id)
    if blob is None:
        return None
    return pickle.loads(blob)


def import_blob(raw: bytes):
    """Restore a blob uploaded by the client (used by session import)."""
    return pickle.loads(raw)
