"""Production settings: debug off, hosts and database taken from the environment."""

from .base import *  # noqa: F401,F403

DEBUG = False

# Comma-separated list in .env, e.g. ALLOWED_HOSTS=yourname.pythonanywhere.com
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['.pythonanywhere.com', 'localhost', '127.0.0.1'])
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# SQLite by default; set DATABASE_URL (for example a Postgres URL) to switch databases.
DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}

# Set HTTPS_ONLY=True once the site is served over HTTPS so cookies are never sent in clear text.
HTTPS_ONLY = env.bool('HTTPS_ONLY', default=False)
SESSION_COOKIE_SECURE = HTTPS_ONLY
CSRF_COOKIE_SECURE = HTTPS_ONLY

# Hashed file names (style.css -> style.<hash>.css) let browsers cache assets safely: a changed file
# gets a new URL. Requires `collectstatic` to have run.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'},
}
