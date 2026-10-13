"""Google sign-in through django-allauth (no real call to Google is made)."""

from urllib.parse import parse_qs, urlsplit

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .models import Traveler

GOOGLE = {
    "google": {
        "APP": {"client_id": "test-client-id.apps.googleusercontent.com", "secret": "test-secret", "key": ""},
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online", "prompt": "select_account"},
    }
}


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE)
class GoogleButtonTests(TestCase):
    def test_login_and_signup_pages_offer_google(self):
        start = reverse("google_login")
        for name, label in (("trips:login", "Continue with Google"), ("trips:signup", "Sign up with Google")):
            with self.subTest(page=name):
                resp = self.client.get(reverse(name))
                self.assertContains(resp, f'action="{start}"')
                self.assertContains(resp, label)

    def test_button_keeps_the_next_page(self):
        resp = self.client.get(reverse("trips:login"), {"next": "/reports/"})
        self.assertContains(resp, 'name="next" value="/reports/"', count=2)   # password form + Google form

    def test_google_start_redirects_to_google_with_the_callback_url(self):
        resp = self.client.post(reverse("google_login"))
        self.assertEqual(resp.status_code, 302)
        url = urlsplit(resp["Location"])
        self.assertEqual(url.netloc, "accounts.google.com")
        query = parse_qs(url.query)
        self.assertEqual(query["client_id"], ["test-client-id.apps.googleusercontent.com"])
        self.assertEqual(query["redirect_uri"], ["http://testserver/accounts/google/login/callback/"])
        self.assertIn("email", query["scope"][0])

    @override_settings(ACCOUNT_DEFAULT_HTTP_PROTOCOL="https")
    def test_production_sends_an_https_callback_url(self):
        resp = self.client.post(reverse("google_login"))
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertEqual(query["redirect_uri"], ["https://testserver/accounts/google/login/callback/"])

    def test_allauth_login_and_signup_pages_redirect_to_ours(self):
        self.assertRedirects(self.client.get("/accounts/login/?next=/reports/"),
                             f"{reverse('trips:login')}?next=/reports/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/accounts/signup/"), reverse("trips:signup"),
                             fetch_redirect_response=False)


class ProfileOnLoginTests(TestCase):
    def test_a_google_account_gets_a_profile_named_after_the_person(self):
        user = User.objects.create_user("priya", "priya@illinois.edu", first_name="Priya", last_name="K")
        SocialAccount.objects.create(user=user, provider="google", uid="1234")
        request = RequestFactory().get("/")
        user_logged_in.send(sender=User, request=request, user=user)
        traveler = Traveler.objects.get(user=user)
        self.assertEqual(traveler.display_name, "Priya K")
        self.assertTrue(traveler.is_domain_verified)
