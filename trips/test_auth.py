"""Login, signup and logout, and which pages and APIs need a signed-in user."""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .factories import make_destination, make_traveler, make_trip
from .models import Traveler, Trip

PROTECTED_PAGES = [
    "trip-list", "trip-search", "trip-create", "insights", "reports",
    "export-trips-csv", "export-trips-json", "chart-trips-by-destination",
]
PUBLIC_API = "api-insights-destinations"   # the one API anyone may call
PROTECTED_APIS = [
    "api-trips", "api-destinations", "api-destinations-popular", "api-insights-departures",
    "api-ping-json", "api-ping-http-manual-json", "api-ping-http-default", "api-ping-http-text",
    "chart-spec-destinations", "chart-spec-departures",
]


class SignUpTests(TestCase):
    def test_signup_creates_account_and_profile_and_signs_in(self):
        resp = self.client.post(reverse("trips:signup"), {
            "username": "carol", "email": "Carol@Illinois.edu",
            "password1": "a-Strong-pass-123", "password2": "a-Strong-pass-123",
        })
        self.assertRedirects(resp, reverse("trips:home"))
        user = User.objects.get(username="carol")
        self.assertEqual(user.email, "carol@illinois.edu")
        self.assertTrue(Traveler.objects.get(user=user).is_domain_verified)   # .edu address
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_signup_returns_to_the_page_that_asked_for_login(self):
        resp = self.client.post(reverse("trips:signup"), {
            "username": "dan", "email": "dan@example.com",
            "password1": "a-Strong-pass-123", "password2": "a-Strong-pass-123",
            "next": reverse("trips:trip-create"),
        })
        self.assertRedirects(resp, reverse("trips:trip-create"))

    def test_signup_ignores_a_next_link_to_another_site(self):
        resp = self.client.post(reverse("trips:signup"), {
            "username": "eve", "email": "eve@example.com",
            "password1": "a-Strong-pass-123", "password2": "a-Strong-pass-123",
            "next": "https://evil.example.com/",
        })
        self.assertRedirects(resp, reverse("trips:home"))

    def test_signup_rejects_mismatched_passwords_and_duplicate_email(self):
        User.objects.create_user("frank", "frank@example.com", "pw")
        resp = self.client.post(reverse("trips:signup"), {
            "username": "frank2", "email": "FRANK@example.com",
            "password1": "a-Strong-pass-123", "password2": "different-pass-123",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("email", resp.context["form"].errors)
        self.assertIn("password2", resp.context["form"].errors)
        self.assertFalse(User.objects.filter(username="frank2").exists())


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", "alice@illinois.edu", "secret-pass-123")

    def test_login_page_is_the_custom_template(self):
        resp = self.client.get(reverse("trips:login"))
        self.assertTemplateUsed(resp, "accounts/login.html")
        self.assertContains(resp, reverse("trips:signup"))

    def test_login_with_the_right_password_redirects_home(self):
        resp = self.client.post(reverse("trips:login"), {"username": "alice", "password": "secret-pass-123"})
        self.assertRedirects(resp, reverse("trips:home"))

    def test_login_with_the_wrong_password_shows_an_error(self):
        resp = self.client.post(reverse("trips:login"), {"username": "alice", "password": "nope"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["form"].non_field_errors())

    def test_login_follows_next(self):
        resp = self.client.post(reverse("trips:login"), {
            "username": "alice", "password": "secret-pass-123", "next": reverse("trips:reports"),
        })
        self.assertRedirects(resp, reverse("trips:reports"))

    def test_logout_needs_post_and_signs_out(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("trips:logout")).status_code, 405)
        resp = self.client.post(reverse("trips:logout"))
        self.assertRedirects(resp, reverse("trips:home"))
        self.assertNotIn("_auth_user_id", self.client.session)


class ProtectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = make_traveler("alice")
        cls.bob = make_traveler("bob")
        rome = make_destination()
        cls.public = make_trip(cls.alice, rome, "Italy loop", date(2026, 5, 1),
                               visibility=Trip.PUBLIC, status=Trip.PLANNED, seats_open=2)
        cls.private = make_trip(cls.alice, rome, "Secret Rome", date(2026, 6, 1), visibility=Trip.PRIVATE)

    def test_public_pages_open_without_login(self):
        for name in ("home", "trip-list-generic", "trip-manual", "login", "signup"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"trips:{name}")).status_code, 200)

    def test_protected_pages_redirect_to_login_with_next(self):
        for name in PROTECTED_PAGES:
            with self.subTest(page=name):
                url = reverse(f"trips:{name}")
                self.assertRedirects(self.client.get(url), f"{reverse('trips:login')}?next={url}",
                                     fetch_redirect_response=False)
        for name in ("trip-detail", "trip-budget"):
            with self.subTest(page=name):
                url = reverse(f"trips:{name}", args=[self.public.pk])
                self.assertRedirects(self.client.get(url), f"{reverse('trips:login')}?next={url}",
                                     fetch_redirect_response=False)

    def test_protected_apis_answer_401_json(self):
        urls = [reverse(f"trips:{name}") for name in PROTECTED_APIS]
        urls.append(reverse("trips:api-trip-budget", args=[self.public.pk]) + "?currency=EUR")
        for url in urls:
            with self.subTest(api=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 401)
                self.assertEqual(resp["Content-Type"], "application/json")
                self.assertEqual(resp.json()["login_url"], reverse("trips:login"))

    def test_protected_apis_work_after_login(self):
        self.client.force_login(self.bob.user)
        for name in PROTECTED_APIS:
            with self.subTest(api=name):
                self.assertEqual(self.client.get(reverse(f"trips:{name}")).status_code, 200)

    def test_nav_hides_protected_links_until_login(self):
        hidden = [reverse(f"trips:{n}") for n in ("trip-list", "trip-search", "insights", "reports", "trip-create")]
        resp = self.client.get(reverse("trips:home"))
        for url in hidden:
            self.assertNotContains(resp, f'href="{url}"')
        self.assertContains(resp, f'href="{reverse("trips:login")}"')
        self.assertContains(resp, f'href="{reverse("trips:signup")}"')

        self.client.force_login(self.bob.user)
        resp = self.client.get(reverse("trips:home"))
        for url in hidden:
            self.assertContains(resp, f'href="{url}"')
        self.assertContains(resp, f'action="{reverse("trips:logout")}"')
        self.assertNotContains(resp, f'href="{reverse("trips:login")}"')

    def test_private_trip_is_only_visible_to_its_owner(self):
        self.client.force_login(self.bob.user)
        self.assertNotContains(self.client.get(reverse("trips:trip-list")), "Secret Rome")
        self.assertEqual(self.client.get(self.private.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(reverse("trips:trip-budget", args=[self.private.pk])).status_code, 404)

        self.client.force_login(self.alice.user)
        self.assertContains(self.client.get(reverse("trips:trip-list")), "Secret Rome")
        self.assertEqual(self.client.get(self.private.get_absolute_url()).status_code, 200)

    def test_a_new_trip_belongs_to_the_signed_in_user(self):
        user = User.objects.create_user("newbie", "newbie@example.com", "pw")   # no profile yet
        self.client.force_login(user)
        rome = self.public.stops.first().destination
        resp = self.client.post(reverse("trips:trip-create"), {
            "title": "First trip", "start_date": "2026-11-01", "end_date": "2026-11-04",
            "budget_min_usd": "100", "budget_max_usd": "200", "group_size": "1", "seats_open": "0",
            "stop_1": rome.pk,
        })
        trip = Trip.objects.get(title="First trip")
        self.assertRedirects(resp, trip.get_absolute_url())
        self.assertEqual(trip.owner.user, user)


class PublicApiTests(TestCase):
    """/api/insights/destinations/ is the single public API; it serves clean JSON from the database."""

    @classmethod
    def setUpTestData(cls):
        owner = make_traveler("alice")
        rome, lisbon = make_destination("Rome", "Italy", "125.00"), make_destination("Lisbon", "Portugal", "95.00")
        make_trip(owner, rome, "Italy loop", date(2026, 5, 1), visibility=Trip.PUBLIC)
        make_trip(owner, rome, "Rome again", date(2026, 6, 1), visibility=Trip.PUBLIC)
        make_trip(owner, lisbon, "Secret Lisbon", date(2026, 7, 1), visibility=Trip.PRIVATE)

    def test_public_api_needs_no_login_and_returns_clean_json(self):
        resp = self.client.get(reverse(f"trips:{PUBLIC_API}"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/json")
        self.assertEqual(resp.json(), [
            {"destination": "Rome", "country": "Italy", "public_trips": 2, "avg_daily_cost_usd": 125.0},
        ])   # Lisbon's only trip is private, so it is not published

    def test_public_api_reflects_the_database(self):
        Trip.objects.filter(title="Rome again").delete()
        self.assertEqual(self.client.get(reverse(f"trips:{PUBLIC_API}")).json()[0]["public_trips"], 1)

    def test_public_api_exposes_no_personal_data(self):
        body = self.client.get(reverse(f"trips:{PUBLIC_API}")).content.decode()
        for secret in ("alice", "@illinois.edu", "Secret Lisbon", "budget"):
            self.assertNotIn(secret, body)

    def test_vega_editor_may_read_the_public_api(self):
        resp = self.client.get(reverse(f"trips:{PUBLIC_API}"), HTTP_ORIGIN="https://vega.github.io")
        self.assertEqual(resp["Access-Control-Allow-Origin"], "https://vega.github.io")

    def test_every_other_api_stays_protected(self):
        for name in PROTECTED_APIS:
            with self.subTest(api=name):
                self.assertEqual(self.client.get(reverse(f"trips:{name}")).status_code, 401)
