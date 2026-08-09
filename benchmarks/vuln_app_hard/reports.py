"""Report generation. Admins can define custom report templates."""
from db import get_conn


def render_report(template: str, context: dict) -> str:
    """Evaluate a custom report template expression."""
    return str(eval(template, {"__builtins__": {}}, context))


def sales_report(expr: str) -> str:
    conn = get_conn()
    rows = conn.execute("SELECT id, total FROM orders").fetchall()
    return render_report(expr, {"rows": rows, "sum": sum, "len": len})
