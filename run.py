"""Entry point for Daily Volume Tracker."""

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Bind to 0.0.0.0 so other machines on the network can access
    app.run(host="0.0.0.0", port=8089)
