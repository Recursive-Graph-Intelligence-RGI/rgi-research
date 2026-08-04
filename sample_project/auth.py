"""JWT handling with intentional vulnerabilities."""
import jwt

SECRET_KEY = "supersecret123"  # hardcoded weak secret


class JWTManager:
    def __init__(self):
        self.secret = SECRET_KEY

    def create_token(self, user_id):
        # VULNERABILITY: no 'exp' claim — tokens never expire
        return jwt.encode({"user_id": user_id}, self.secret, algorithm="HS256")

    def decode_token(self, token):
        # VULNERABILITY: no expiration verification, HS256 only
        return jwt.decode(token, self.secret, algorithms=["HS256"])
