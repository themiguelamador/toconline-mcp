import logging
import os
import re
import sys

_REDACT_KEYS = re.compile(
    r"(access_token|refresh_token|client_secret|authorization)"
    r"\s*[:=]\s*([\"']?)([^\s\"',}]+)",
    re.IGNORECASE,
)


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _REDACT_KEYS.sub(r"\1\2***REDACTED***", record.msg)
        return True


def get_logger(name: str = "toconline_mcp") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(_RedactFilter())
    logger.addHandler(handler)
    level = os.environ.get("TOCONLINE_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False
    return logger
