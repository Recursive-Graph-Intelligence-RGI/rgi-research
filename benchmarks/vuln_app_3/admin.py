"""Admin endpoints."""
from database import run_query


def delete_user(request):
    user_id = request.args.get("user_id")
    return run_query(f"DELETE FROM users WHERE id = {user_id}")
