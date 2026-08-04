"""Database execution layer."""
import sqlite3
from settings import DB_PATH


def run_query(query):
    conn = sqlite3.connect(DB_PATH)
    return conn.execute(query).fetchall()
