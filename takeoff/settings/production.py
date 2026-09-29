from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}

# Cache busting for production.
# `collectstatic` renames style.css -> style.<content-hash>.css, so a changed file
# gets a new URL and browsers must re-download it. Kept OUT of base.py on purpose:
# with this storage, a missing `collectstatic` breaks {% static %} (and the test
# runner, which runs with DEBUG=False).
# Django 5.1+ removed the old STATICFILES_STORAGE setting; the STORAGES dict below replaces it.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}
