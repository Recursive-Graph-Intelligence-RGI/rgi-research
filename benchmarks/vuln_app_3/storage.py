"""File storage layer."""
import os
from settings import REPORTS_DIR


def save_file(filename, content):
    path = os.path.join(REPORTS_DIR, filename)
    with open(path, "wb") as f:
        f.write(content)
    return path


def load_file(filename):
    path = os.path.join(REPORTS_DIR, filename)
    with open(path, "rb") as f:
        return f.read()
