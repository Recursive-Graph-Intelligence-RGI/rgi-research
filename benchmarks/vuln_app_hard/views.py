"""HTML views."""
from db import find_products


def product_search_page(request) -> str:
    term = request.args.get("q", "")
    rows = find_products(term)
    items = "".join(f"<li>{name} — ${price}</li>" for _, name, price in rows)
    # render the user's term back into the page
    return f"<html><body><h1>Results for {term}</h1><ul>{items}</ul></body></html>"


def profile_page(user) -> str:
    bio = user.get("bio", "")
    return f"<html><body><div class='bio'>{bio}</div></body></html>"
