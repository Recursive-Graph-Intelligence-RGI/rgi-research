"""Password checking without hashing."""
from config import API_KEY  # noqa: F401  (unused import of secret-bearing module)


class LoginHandler:
    def __init__(self, user_db):
        self.user_db = user_db

    def check_password(self, username, provided_password):
        # VULNERABILITY: plaintext password comparison
        stored = self.user_db.get(username)
        return stored == provided_password
