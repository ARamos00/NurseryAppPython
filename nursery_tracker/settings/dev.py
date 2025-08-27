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

from .base import *

DEBUG = env.bool("DEBUG", True)

# Console email backend for dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# SQLite by default; override with DATABASE_URL if you want Postgres locally
# Example for Postgres:
# DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/nursery_db
