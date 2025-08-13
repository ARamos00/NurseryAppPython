from .base import *

DEBUG = env.bool("DEBUG", True)

# Console email backend for dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# SQLite by default; override with DATABASE_URL if you want Postgres locally
# Example for Postgres:
# DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/nursery_db
