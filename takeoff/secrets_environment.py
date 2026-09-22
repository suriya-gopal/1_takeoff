"""
takeoff/secrets_environment.py

Loads secret configuration values (SECRET_KEY, any API keys) from a .env
file at the project root into OS environment variables, using
django-environ. Keeps secrets out of GitHub.
"""

import environ
from pathlib import Path

env = environ.Env()

BASE_DIR = Path(__file__).resolve().parent.parent
environ.Env.read_env(BASE_DIR / ".env")
