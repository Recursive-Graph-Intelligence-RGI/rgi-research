"""Background queue consumer."""
import socket
from cache import deserialize


def listen(port=9393):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("0.0.0.0", port))
    sock.listen()
    while True:
        conn, _ = sock.accept()
        data = conn.recv(65536)
        deserialize(data)
