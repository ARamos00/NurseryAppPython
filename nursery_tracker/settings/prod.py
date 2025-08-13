from .base import *

# ----------------------------------------------------------------------
# Core
# ----------------------------------------------------------------------
DEBUG = False

# Require an explicit secret in prod
SECRET_KEY = env("SECRET_KEY")

# Hosts & CSRF must be provided by env in prod
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# ----------------------------------------------------------------------
# Database (must NOT default to SQLite in prod)
# e.g. postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
# ----------------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL")
}

# ----------------------------------------------------------------------
# Static files
# ----------------------------------------------------------------------
# Static files should be collected here (served by your web server or CDN)
STATIC_ROOT = BASE_DIR / "staticfiles"

# ----------------------------------------------------------------------
# Security hardening (Django deploy checklist)
# ----------------------------------------------------------------------
# Force HTTPS
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", True)

# Secure cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True  # CSRF cookie not readable by JS

# SameSite policy
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# HSTS (enable preload only after verifying HTTPS everywhere)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", 60 * 60 * 24 * 7)  # 1 week
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Content-type sniffing and referrer policy
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# If behind a proxy/load balancer that terminates TLS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ----------------------------------------------------------------------
# Logging (concise console logging + request/security channels)
# ----------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
