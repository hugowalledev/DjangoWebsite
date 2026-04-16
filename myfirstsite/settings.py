"""
Django settings for esport project.

Docs :
- https://docs.djangoproject.com/en/5.2/topics/settings/
- https://docs.djangoproject.com/en/5.2/ref/settings/
"""

from pathlib import Path
import os

import dj_database_url
from decouple import config


# Paths

BASE_DIR = Path(__file__).resolve().parent.parent


# Core env

DEBUG = config("DEBUG", default=False, cast=bool)
SECRET_KEY = config("SECRET_KEY")


# Hosts / CSRF

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="127.0.0.1,localhost,pronostiqueurs-all-star.onrender.com"
).split(",")

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="https://pronostiqueurs-all-star.onrender.com"
).split(",")


# Application definition

INSTALLED_APPS = [
    # Admin-interface
    'jazzmin',
    'django.contrib.admin',
    # Apps
    'esport.apps.EsportConfig',
    'users.apps.UsersConfig',

    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    # Tailwind
    'tailwind',
    'theme',
]

if DEBUG:
    INSTALLED_APPS += [
        'django_browser_reload',
        'django_extensions',
        'debug_toolbar',
    ]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]
if DEBUG:
    MIDDLEWARE += ['django_browser_reload.middleware.BrowserReloadMiddleware',]

ROOT_URLCONF = 'myfirstsite.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.request',
                'users.context_processors.auth_forms',
            ],
        },
    },
]

WSGI_APPLICATION = 'myfirstsite.wsgi.application'


# Database

DATABASE_URL = config('DATABASE_URL', default='sqlite:///db.sqlite3')

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=not DEBUG  
    )
}


# Auth

AUTH_USER_MODEL = 'users.UserProfile'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

LOGIN_REDIRECT_URL = '/esport/'
LOGOUT_REDIRECT_URL ='/esport/'


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    ("champions", BASE_DIR / "champions"),
    ("tournaments", BASE_DIR / "tournaments"),
    ("teams", BASE_DIR / "teams"),
    ("roles", BASE_DIR / "roles"),
]


STATICFILES_STORAGE="whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR/"media"


# Security

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# Allauth / Sites

SITE_ID = 1

ACCOUNT_SIGNUP_FIELDS = ['username*', 'email*', 'password1', 'password2']
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https" if not DEBUG else "http"
ACCOUNT_LOGIN_METHODS = {"username",'email'}
ACCOUNT_LOGOUT_ON_GET = True

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


# Social auth

GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = config("GOOGLE_CLIENT_SECRET")

SOCIALACCOUNT_PROVIDERS = {
   'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'APP': {
            'client_id': GOOGLE_CLIENT_ID,
            'secret': GOOGLE_CLIENT_SECRET,
            'key': ''
        }
   }
}

SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_EMAIL_VERIFICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_LOGIN_ON_GET=True
SOCIALACCOUNT_AUTO_SIGNUP = True


# Dev tools

INTERNAL_IPS = ["127.0.0.1"]

DATA_UPLOAD_MAX_NUMBER_FIELDS = 100000


# Tailwind settings
if DEBUG:
    NPM_BIN_PATH = 'C:/NodeJs/npm.cmd'
    
TAILWIND_APP_NAME = 'theme'

JAZZMIN_SETTINGS = {"theme": "darkly"}


# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
