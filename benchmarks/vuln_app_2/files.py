"""File serving with intentional path traversal."""
import os


def read_report(filename):
    # VULNERABILITY: unvalidated user-controlled path
    path = os.path.join("/var/data/reports", filename)
    with open(path) as f:
        return f.read()
