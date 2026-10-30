"""Cloud settings. Local development continues using config.settings."""
import re
from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403

DEBUG = False
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 50 random characters.")

ALLOWED_HOSTS = [host.strip().lower() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if host.strip()]
render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
if render_host:
    ALLOWED_HOSTS.append(render_host)
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))
if not ALLOWED_HOSTS or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Set exact hostnames in DJANGO_ALLOWED_HOSTS or RENDER_EXTERNAL_HOSTNAME; no URLs or wildcards.")

CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

DATABASES = deepcopy(DATABASES)
DATABASES["default"].update(CONN_MAX_AGE=60, CONN_HEALTH_CHECKS=True)
DATABASES["default"]["OPTIONS"] = {"connect_timeout": 5}

ROOT_URLCONF = "config.urls_production"
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
MIDDLEWARE.append("config.deployment_views.NoIndexMiddleware")
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
STATICFILES_DIRS = [("app", FRONTEND_DIST)]
# Vite already hashes its assets. Keep their original names referenced by index.html.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_MAX_AGE = 3600

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
}
