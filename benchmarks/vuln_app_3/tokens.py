"""Token issuing and verification."""
import jwt
from settings import JWT_SECRET


def issue_token(user_id):
    return jwt.encode({"user_id": user_id}, JWT_SECRET, algorithm="HS256")


def verify_token(token):
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
