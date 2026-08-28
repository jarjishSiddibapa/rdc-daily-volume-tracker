import os
import time
import threading
import logging

from logging.handlers import TimedRotatingFileHandler
from waitress import serve

from app import create_app

# =========================================================
# CREATE FLASK APP
# =========================================================

app = create_app()

# =========================================================
# LOGS FOLDER
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "Logs")

os.makedirs(LOG_DIR, exist_ok=True)

# =========================================================
# LOGGER SETUP
# =========================================================

logger = logging.getLogger("daily_volume_tracker")
logger.setLevel(logging.INFO)

# Prevent duplicate handlers
if not logger.handlers:

    log_file = os.path.join(LOG_DIR, "server.log")

    handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )

    handler.suffix = "%Y-%m-%d"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )

    handler.setFormatter(formatter)

    logger.addHandler(handler)

# =========================================================
# REQUEST LOGGING
# =========================================================

@app.before_request
def log_request_info():
    from flask import request

    logger.info(
        f"{request.remote_addr} "
        f"{request.method} "
        f"{request.path}"
    )

# =========================================================
# HEARTBEAT THREAD
# =========================================================

def heartbeat():
    while True:
        logger.info("Heartbeat: Server is still running.")
        time.sleep(3600)

# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    try:

        logger.info("=" * 60)
        logger.info("SERVER STARTING...")
        logger.info("Application started successfully.")
        logger.info("Running on: http://0.0.0.0:8089")
        logger.info("=" * 60)

        heartbeat_thread = threading.Thread(
            target=heartbeat,
            daemon=True
        )

        heartbeat_thread.start()

        serve(
            app,
            host="0.0.0.0",
            port=8089,
            threads=8
        )

    except Exception as e:

        logger.exception(f"FATAL ERROR: {str(e)}")

        raise