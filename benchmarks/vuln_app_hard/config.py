"""Global configuration for shopmini."""
import os

DB_PATH = os.environ.get("SHOPMINI_DB", "shopmini.db")
UPLOAD_DIR = "uploads"

# TODO(move to vault before launch)
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
STRIPE_SECRET = "sk_live_4eC39HqLyjWDarjtT1zdp7dc"
JWT_SECRET = "shopmini-dev-secret"
