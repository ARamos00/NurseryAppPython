"""
Developer settings (extends base).

Defaults
--------
- DEBUG defaults True (overridable via env).
- Console email backend (no outbound mail).
- SQLite by default unless `DATABASE_URL` is provided (see comment for Postgres).

Security
--------
- Do not use these settings in production; cookies and HTTPS flags are not forced
  here. Use `prod.py` for hardened defaults.
"""

from .base import *  # noqa

DEBUG = env.bool("DEBUG", True)

# Console email backend for dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------
# Dev CSRF: trust local SPA and Django dev server origins.
# NOTE: Environment variable CSRF_TRUSTED_ORIGINS will override this.
# Keep both localhost and 127.0.0.1 variants, and both ports (8000, 5173).
# ---------------------------------------------------------------------
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
)

# ---------------------------------------------------------------------
# Optional: verbose CSRF diagnostics in dev ONLY.
# This logs the exact CSRF rejection reason (origin mismatch, missing cookie,
# bad token, etc.) to the console to speed up debugging.
# ---------------------------------------------------------------------
LOGGING["loggers"]["django.security.csrf"] = {  # type: ignore[name-defined]
    "handlers": ["console"],
    "level": "DEBUG",
    "propagate": False,
}

# SQLite by default; override with DATABASE_URL if you want Postgres locally
# Example for Postgres:
# DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/nursery_db
