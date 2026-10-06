"""
WSGI entry point for production servers such as PythonAnywhere.

Uses the production settings unless DJANGO_SETTINGS_MODULE says otherwise.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'takeoff.settings.production')

application = get_wsgi_application()
