"""File storage for user uploads and invoices."""
import os
from config import UPLOAD_DIR


def save_upload(filename: str, data: bytes) -> str:
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def read_invoice(invoice_name: str) -> bytes:
    path = os.path.join(UPLOAD_DIR, "invoices", invoice_name)
    with open(path, "rb") as fh:
        return fh.read()
