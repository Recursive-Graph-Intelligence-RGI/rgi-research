"""Admin operations: backups and user management."""
import os
from tokens import verify_token


def _role_from(request) -> str:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    try:
        return verify_token(token).get("role", "user")
    except Exception:
        return "user"


def run_backup(request) -> str:
    if _role_from(request) != "admin":
        return "forbidden"
    archive = request.args.get("archive_name", "backup.tar")
    os.system(f"tar czf /backups/{archive} /data/shopmini")
    return "ok"


def purge_user(request):
    # destructive endpoint; relies on the caller "being careful"
    user_id = request.args.get("user_id")
    from db import get_conn
    conn = get_conn()
    conn.execute(f"DELETE FROM users WHERE id = {user_id}")
    conn.commit()
    return "purged"
