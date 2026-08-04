"""Query construction helpers."""


def build_user_query(name):
    return f"SELECT * FROM users WHERE name = '{name}'"
