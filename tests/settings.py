"""
Django settings for testing django-easypay.

Minimal configuration required to run pytest-django tests.
"""

SECRET_KEY = "django-insecure-test-key-for-easypay-tests-only"

DEBUG = True

ALLOWED_HOSTS = ["*", "testserver", "localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "easypay",
    "easypay.sandbox",  # Sandbox testing module
    "tests",  # Contains concrete Payment model for testing
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "db.sqlite3",
    }
}

# EasyPay Test Configuration
EASYPAY_MALL_ID = "T0021792"
EASYPAY_API_URL = "https://testpgapi.easypay.co.kr"

# Timezone
USE_TZ = True
TIME_ZONE = "Asia/Seoul"

# Default auto field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Middleware (minimal for admin tests)
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

# Templates (for admin)
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

ROOT_URLCONF = "tests.urls"
