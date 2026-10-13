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


# ---------------------------------------------------------------------------
# Names from Google
# ---------------------------------------------------------------------------
# A brand-new Google user gets their first and last name from Google automatically. An account that
# already existed (for example one from the seed data, matched by email) does not, so these two
# handlers copy the names across whenever a Google account is linked or used, but only into empty
# fields: a name someone typed themselves is never overwritten.
from allauth.socialaccount.signals import social_account_added, social_account_updated  # noqa: E402


@receiver(social_account_added)
@receiver(social_account_updated)
def fill_names_from_google(sender, request, sociallogin, **kwargs):
    account = sociallogin.account
    user = sociallogin.user
    if account.provider != "google" or user is None or user.pk is None:
        return

    data = account.extra_data or {}
    changed = []
    if not user.first_name and data.get("given_name"):
        user.first_name = data["given_name"][:150]
        changed.append("first_name")
    if not user.last_name and data.get("family_name"):
        user.last_name = data["family_name"][:150]
        changed.append("last_name")
    if changed:
        user.save(update_fields=changed)
