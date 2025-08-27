from pathlib import Path
import environ

# ---------------------------------------------------------------------
# Paths & Env
# ---------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env(DEBUG=(bool, False))
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

# ---------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://127.0.0.1:8000", "http://localhost:8000"],
)

# ---------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------
INSTALLED_APPS = [
    # Django apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "django_filters",
    "drf_spectacular",

    # Local apps
    "accounts",
    "core",
    "nursery",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Observability: request-id + structured request log (one line per request)
    "core.middleware.RequestIDLogMiddleware",
]

ROOT_URLCONF = "nursery_tracker.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "nursery_tracker.wsgi.application"

# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

# ---------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------
# Static/Media
# ---------------------------------------------------------------------
STATIC_URL = "static/"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------
# DRF & API Schema
# ---------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": env("DRF_THROTTLE_RATE_USER", default="200/min"),
        "anon": env("DRF_THROTTLE_RATE_ANON", default="50/min"),
        "wizard-seed": env("DRF_THROTTLE_RATE_WIZARD_SEED", default="30/min"),
        "events-export": env("DRF_THROTTLE_RATE_EVENTS_EXPORT", default="10/min"),
        "label-public": env("DRF_THROTTLE_RATE_LABEL_PUBLIC", default="120/min"),
        "audit-read": env("DRF_THROTTLE_RATE_AUDIT_READ", default="60/min"),
        "imports": env("DRF_THROTTLE_RATE_IMPORTS", default="6/min"),
        "reports-read": env("DRF_THROTTLE_RATE_REPORTS_READ", default="60/min"),
        "labels-read": env("DRF_THROTTLE_RATE_LABELS_READ", default="60/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Nursery Tracker API",
    "DESCRIPTION": "Backend API for nursery tracking (backend-first build).",
    "VERSION": "0.1.0",
    # Advertise both the current surface (root) and the /api/v1/ mirror.
    "SERVERS": [
        {"url": "http://127.0.0.1:8000", "description": "Local Dev"},
        {"url": "/", "description": "Current"},
        {"url": "/api/v1/", "description": "v1 mirror"},
    ],
    # Auto-resolve any residual operationId duplicates by suffixing (prevents warnings).
    "OPERATION_ID_DUPLICATE_MODE": "suffix",
    "CONTACT": {"name": "Nursery Tracker", "email": "dev@example.com"},
    "LICENSE": {"name": "MIT"},
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
    "ENUM_NAME_OVERRIDES": {
        "PlantStatusEnum": "nursery.models.PlantStatus",
        "BatchStatusEnum": "nursery.models.BatchStatus",
        "MaterialTypeEnum": "nursery.models.MaterialType",
        "PropagationMethodEnum": "nursery.models.PropagationMethod",
        "EventTypeEnum": "nursery.models.EventType",
    },
}

# Concurrency strictness toggle
ENFORCE_IF_MATCH = env.bool("ENFORCE_IF_MATCH", False)

# NEW: Import size cap (bytes)
MAX_IMPORT_BYTES = env.int("MAX_IMPORT_BYTES", default=5_000_000)

# ---------------------------------------------------------------------
# Security defaults (safe baseline; prod hardening in prod.py)
# ---------------------------------------------------------------------
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

# ---------------------------------------------------------------------
# Auth model
# ---------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------
# Concurrency (optimistic locking) switch
# ---------------------------------------------------------------------
# When True, PATCH/PUT/DELETE require `If-Match` and return 428 if missing.
ENFORCE_IF_MATCH = env.bool("ENFORCE_IF_MATCH", False)

# --- Webhooks ------------------------------------------------------------------
# Require HTTPS for webhook endpoints unless explicitly disabled for local dev.
WEBHOOKS_REQUIRE_HTTPS = env.bool("WEBHOOKS_REQUIRE_HTTPS", default=not DEBUG)
WEBHOOKS_SIGNATURE_HEADER = env("WEBHOOKS_SIGNATURE_HEADER", default="X-Webhook-Signature")
WEBHOOKS_USER_AGENT = env("WEBHOOKS_USER_AGENT", default="NurseryTracker/0.1")
# Turn on automatic emits later (e.g., from signals) without altering code.
WEBHOOKS_ENABLE_AUTO_EMIT = env.bool("WEBHOOKS_ENABLE_AUTO_EMIT", default=False)

# ---------------------------------------------------------------------
# Logging (observability)
# ---------------------------------------------------------------------
# Minimal, structured console logging for request lines. The RequestIDFilter
# injects `request_id` even for logs outside HTTP contexts.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "core.logging.RequestIDFilter"},
    },
    "formatters": {
        # Simple structured formatter; extend as needed in prod.py
        "structured": {
            "format": "level=%(levelname)s logger=%(name)s request_id=%(request_id)s "
                      "method=%(method)s path=%(path)s status=%(status)s user_id=%(user_id)s duration_ms=%(duration_ms)s "
                      "message=%(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "structured",
        },
    },
    "loggers": {
        # The middleware logs one line per request to this logger.
        "nursery.request": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
