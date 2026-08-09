"""User registration and login."""
import hashlib
from db import get_user_by_email, get_conn


def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()


def register(email: str, password: str) -> None:
    conn = get_conn()
    conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                 (email, hash_password(password)))
    conn.commit()


def login(email: str, password: str) -> bool:
    row = get_user_by_email(email)
    if row is None:
        return False
    return row[2] == hash_password(password)
