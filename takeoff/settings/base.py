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
    # django-allauth: "Continue with Google" (OAuth 2.0)
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
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
    'allauth.account.middleware.AccountMiddleware',
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

# Authentication
# Pages and APIs marked with @login_required (or LoginRequiredMixin) send visitors who are not
# signed in to LOGIN_URL. After signing in they land on LOGIN_REDIRECT_URL (or the page they were
# trying to open, via ?next=), and after signing out on LOGOUT_REDIRECT_URL.
LOGIN_URL = 'trips:login'
LOGIN_REDIRECT_URL = 'trips:home'
LOGOUT_REDIRECT_URL = 'trips:home'

# Two ways to sign in: Django's username/password check, and allauth for Google accounts.
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Google OAuth (django-allauth)
# The client ID and secret come from Google Cloud Console -> APIs & Services -> Credentials and
# live in .env, never in git. Authorised redirect URIs to register there:
#   http://127.0.0.1:8000/accounts/google/login/callback/
#   http://localhost:8000/accounts/google/login/callback/
#   https://<username>.pythonanywhere.com/accounts/google/login/callback/
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': env('GOOGLE_CLIENT_ID', default=''),
            'secret': env('GOOGLE_CLIENT_SECRET', default=''),
            'key': '',
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online', 'prompt': 'select_account'},
    }
}
SOCIALACCOUNT_AUTO_SIGNUP = True            # first Google login creates the account, no extra form
SOCIALACCOUNT_LOGIN_ON_GET = False          # the Google button POSTs (with a CSRF token)
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True   # a Google login whose verified email matches an
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True  # existing account signs into that account
ACCOUNT_EMAIL_VERIFICATION = 'none'         # Google has already verified the address
ACCOUNT_LOGOUT_REDIRECT_URL = LOGOUT_REDIRECT_URL

# Cross-origin access
# The JSON feeds under /api/ are public and read-only. Allowing the Vega editor's origin lets anyone
# chart them at https://vega.github.io/editor/ without a proxy.
CORS_ALLOWED_ORIGINS = ['https://vega.github.io']
CORS_URLS_REGEX = r'^/api/.*$'
CORS_ALLOW_METHODS = ['GET', 'HEAD', 'OPTIONS']
