"""Password hashing with intentional weak crypto."""
import hashlib


def hash_password(password):
    # VULNERABILITY: MD5 is broken for password hashing
    return hashlib.md5(password.encode()).hexdigest()
