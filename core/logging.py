"""
Logging helpers for request-scoped correlation.

Overview
--------
- Exposes a `contextvars.ContextVar` (`request_id_var`) that stores the current
  request id for the lifetime of the request (set by middleware).
- Provides `RequestIDFilter`, a `logging.Filter` that injects `request_id` onto
  every `LogRecord` so formatters using `%(request_id)s` never break—even when
  the log line originates outside an HTTP request (e.g., management commands).

Usage
-----
- Middleware (`core.middleware.RequestIDLogMiddleware`) sets the value on each
  request and also adds `X-Request-ID` to responses.
- Configure the filter on handlers in Django LOGGING settings so all logs have a
  stable correlation id. A safe dash `"-"` is used when no request id is present.
"""

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
        # If middleware didn't attach a request_id, use the context var (or "-").
        if not hasattr(record, "request_id"):
            try:
                record.request_id = request_id_var.get()
            except Exception:  # very defensive
                record.request_id = "-"
        return True
