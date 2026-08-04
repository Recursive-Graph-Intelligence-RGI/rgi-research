"""Database access with intentional SQL injection."""
import sqlite3


class UserDB:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def find_user(self, name):
        # VULNERABILITY: f-string SQL injection
        query = f"SELECT * FROM users WHERE name = '{name}'"
        return self.conn.execute(query).fetchall()
