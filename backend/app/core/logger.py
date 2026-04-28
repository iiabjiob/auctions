import logging
import os
from logging import LoggerAdapter
from app.core.config import get_settings

settings = get_settings()
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


base_logger = logging.getLogger("app")


LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL
}
log_level = LOG_LEVELS.get(settings.debug_level.lower(), logging.INFO)
base_logger.setLevel(log_level)


class AlignedFormatter(logging.Formatter):
    LEVEL_FORMATS = {
        logging.DEBUG:    "DEBUG",
        logging.INFO:     "INFO ",
        logging.WARNING:  "WARN ",
        logging.ERROR:    "ERROR",
        logging.CRITICAL: "CRIT "
    }

    def format(self, record):
        record.levelname = self.LEVEL_FORMATS.get(record.levelno, record.levelname)
        return super().format(record)

class SourceAwareFormatter(AlignedFormatter):
    def format(self, record):
        source = getattr(record, "source", "")
        if source:
            src = str(source).upper()
            
            src = src[:4].ljust(4)
            source_tag = f"[{src}]"
            if not str(record.msg).startswith(source_tag):
                record.msg = f"{source_tag} {record.msg}"
        return super().format(record)

formatter = SourceAwareFormatter("%(asctime)s - %(levelname)s - %(message)s")


console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO if settings.app_env == "production" else log_level)
console_handler.setFormatter(formatter)

base_logger.addHandler(console_handler)


base_logger.propagate = False


def get_logger(source: str = "") -> LoggerAdapter:
    return LoggerAdapter(base_logger, {"source": source})


logger = get_logger()


logger.info(f"Logger initialized with level: {settings.debug_level} (env: {settings.app_env})")