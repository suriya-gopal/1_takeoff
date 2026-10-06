"""
ASGI entry point.

Uses the production settings unless DJANGO_SETTINGS_MODULE says otherwise.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'takeoff.settings.production')

application = get_asgi_application()
