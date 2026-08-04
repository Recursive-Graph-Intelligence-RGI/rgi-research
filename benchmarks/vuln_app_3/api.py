"""Public search API."""
from middleware import require_auth
from query_builder import build_user_query
from database import run_query


@require_auth
def search_users(request):
    name = request.args.get("name", "")
    query = build_user_query(name)
    return run_query(query)
