from __future__ import annotations

import logging
from contextvars import ContextVar

# Public contextvar so middleware & arbitrary modules can read/write the current id.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")  # default safe dash


class RequestIDFilter(logging.Filter):
    """
    Ensures `%(request_id)s` is always present in log records, even when a logger
    emits outside of an HTTP request context (e.g., management commands).
    """

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover (behavior exercised via middleware)
        if not hasattr(record, "request_id"):
            try:
                record.request_id = request_id_var.get()
            except Exception:  # very defensive
                record.request_id = "-"
        return True
