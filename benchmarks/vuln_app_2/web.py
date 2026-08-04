"""Diagnostics endpoint with intentional command injection."""
import os


def ping_host(host):
    # VULNERABILITY: shell command built from user input
    return os.system("ping -c 1 " + host)
