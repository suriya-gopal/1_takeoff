"""A Google login fills in a missing first and last name, without overwriting names already set."""

from unittest import mock

from allauth.socialaccount.models import SocialAccount, SocialLogin
from allauth.socialaccount.signals import social_account_added, social_account_updated
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from .factories import make_traveler

GOOGLE_PROFILE = {
    "email": "ramesh21@illinois.edu", "email_verified": True,
    "given_name": "Nandhini", "family_name": "Ramesh", "name": "Nandhini Ramesh",
}


def google_login_for(user, extra_data=GOOGLE_PROFILE, uid="1234"):
    account = SocialAccount(provider="google", uid=uid, extra_data=extra_data)
    return SocialLogin(user=user, account=account)


class GoogleNamesTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")

    def test_existing_account_matched_by_email_gets_its_names(self):
        # Like the seeded "nramesh": created without names, then linked through Google by email.
        user = User.objects.create_user("nramesh", "ramesh21@illinois.edu", "pw")
        sociallogin = google_login_for(user)
        with mock.patch("allauth.socialaccount.adapter.DefaultSocialAccountAdapter.send_notification_mail"):
            sociallogin.connect(self.request, user)   # what allauth does on an email match
        user.refresh_from_db()
        self.assertEqual((user.first_name, user.last_name), ("Nandhini", "Ramesh"))

    def test_later_logins_fill_names_that_are_still_missing(self):
        user = User.objects.create_user("priya", "priya@illinois.edu", "pw")
        social_account_updated.send(sender=SocialLogin, request=self.request,
                                    sociallogin=google_login_for(user))
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Nandhini")

    def test_names_someone_already_has_are_kept(self):
        user = User.objects.create_user("kim", "kim@illinois.edu", "pw", first_name="Kimmy")
        social_account_added.send(sender=SocialLogin, request=self.request,
                                  sociallogin=google_login_for(user))
        user.refresh_from_db()
        self.assertEqual((user.first_name, user.last_name), ("Kimmy", "Ramesh"))

    def test_profile_without_names_changes_nothing(self):
        user = make_traveler("sam").user
        social_account_updated.send(sender=SocialLogin, request=self.request,
                                    sociallogin=google_login_for(user, extra_data={"email": "sam@illinois.edu"}))
        user.refresh_from_db()
        self.assertEqual((user.first_name, user.last_name), ("", ""))
