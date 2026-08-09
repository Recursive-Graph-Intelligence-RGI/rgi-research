"""App entrypoint."""
from api import route


def create_app():
    app = {"debug": True, "secret_key": "debug-secret"}
    return app


def main():
    app = create_app()
    print(f"serving with {app}")
    # serve(app, host="0.0.0.0", port=8080, debug=True)


if __name__ == "__main__":
    main()
