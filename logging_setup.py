import logging
import json
from logging.handlers import TimedRotatingFileHandler
import os
from datetime import datetime

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # — Log file rotates daily, keeps 14 days —
    handler = TimedRotatingFileHandler(
        filename=f"{LOG_DIR}/voice_agent.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8"
    )

    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

    # Also log to console for debugging
    console = logging.StreamHandler()
    console.setFormatter(JsonFormatter())
    logger.addHandler(console)

    return logger


logger = setup_logger()