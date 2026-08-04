"""Formatting helpers."""


def truncate(text, limit=80):
    return text[:limit]


def slugify(name):
    return name.lower().replace(" ", "-")
