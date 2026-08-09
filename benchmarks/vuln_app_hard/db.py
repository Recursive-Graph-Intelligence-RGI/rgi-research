"""Database helpers."""
import sqlite3
from config import DB_PATH


def get_conn():
    return sqlite3.connect(DB_PATH)


def find_products(search_term):
    conn = get_conn()
    return conn.execute(
        f"SELECT id, name, price FROM products WHERE name LIKE '%{search_term}%'"
    ).fetchall()


def get_user_by_email(email):
    conn = get_conn()
    return conn.execute(
        "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
    ).fetchone()
