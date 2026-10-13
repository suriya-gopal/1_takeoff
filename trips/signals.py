"""
Signal handlers.

Every successful login, whichever way it happened (username/password or "Continue with Google"),
makes sure the account has its Traveler profile. A first-time Google user therefore lands on the
site with a profile named after their Google account and can plan trips straight away.
"""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import Traveler


@receiver(user_logged_in)
def ensure_traveler_profile(sender, request, user, **kwargs):
    Traveler.for_user(user)
