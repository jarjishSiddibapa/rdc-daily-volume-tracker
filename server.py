import os
import time
import threading
import logging

from logging.handlers import TimedRotatingFileHandler
from waitress import serve
from flask import g, request

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

LOG_ALL_REQUESTS = os.getenv("LOG_ALL_REQUESTS", "false").lower() == "true"
SLOW_REQUEST_MS = int(os.getenv("SLOW_REQUEST_MS", "750"))


@app.before_request
def start_request_timer():
    if request.endpoint != "static":
        g._request_started_at = time.perf_counter()


@app.after_request
def log_relevant_requests(response):
    started_at = g.get("_request_started_at")
    if started_at is None:
        return response

    elapsed_ms = round((time.perf_counter() - started_at) * 1000)
    if LOG_ALL_REQUESTS or response.status_code >= 400 or elapsed_ms >= SLOW_REQUEST_MS:
        logger.info(
            "%s %s %s %s %sms",
            request.remote_addr,
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
    return response

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

        host = os.getenv("APP_HOST", "0.0.0.0")
        port = int(os.getenv("APP_PORT", "8089"))
        threads = int(os.getenv("WAITRESS_THREADS", "4"))

        logger.info("=" * 60)
        logger.info("SERVER STARTING...")
        logger.info("Application started successfully.")
        logger.info("Running on: http://%s:%s", host, port)
        logger.info("=" * 60)

        if os.getenv("HEARTBEAT_ENABLED", "false").lower() == "true":
            heartbeat_thread = threading.Thread(
                target=heartbeat,
                daemon=True
            )
            heartbeat_thread.start()

        serve(
            app,
            host=host,
            port=port,
            threads=threads,
        )

    except Exception as e:

        logger.exception(f"FATAL ERROR: {str(e)}")

        raise
