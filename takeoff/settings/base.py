"""Settings shared by every environment. development.py and production.py extend this module."""

from pathlib import Path

from takeoff.secrets_environment import env

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = env('SECRET_KEY')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'trips',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'takeoff.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'takeoff.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/Chicago'
USE_I18N = True
USE_TZ = True

# Static files
# Site-wide CSS and JavaScript live in one project-level folder. Images and scripts owned by the
# trips app stay in trips/static/trips/. `collectstatic` gathers everything into STATIC_ROOT, which
# is git-ignored and rebuilt on the server at deploy time.
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'takeoff' / 'ui-ux' / 'static']
STATIC_ROOT = BASE_DIR / 'takeoff' / 'ui-ux' / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cross-origin access
# The JSON feeds under /api/ are public and read-only. Allowing the Vega editor's origin lets anyone
# chart them at https://vega.github.io/editor/ without a proxy.
CORS_ALLOWED_ORIGINS = ['https://vega.github.io']
CORS_URLS_REGEX = r'^/api/.*$'
CORS_ALLOW_METHODS = ['GET', 'HEAD', 'OPTIONS']
