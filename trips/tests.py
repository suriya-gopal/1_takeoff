"""
Automated proof that the constraints and on_delete rules actually hold.

These mirror the checks in seed_data.py but run in an isolated test database,
so they can be re-run at any time with:  python manage.py test trips
"""

from datetime import date

from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.db.utils import IntegrityError
from django.test import TestCase

from .models import Destination, ItineraryItem, JoinRequest, Traveler, Trip, TripStop


class TripModelConstraintTests(TestCase):
    """Exercises the uniqueness constraints and deletion behaviour."""

    def setUp(self):
        self.rome = Destination.objects.create(name="Rome", country="Italy")
        self.owner = Traveler.objects.create(
            user=User.objects.create_user("alice", "alice@illinois.edu", "pw"),
            display_name="Alice",
            is_domain_verified=True,
        )
        self.trip = Trip.objects.create(
            owner=self.owner,
            title="Italy loop",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 8),
            visibility=Trip.PUBLIC,
        )
        self.stop = TripStop.objects.create(
            trip=self.trip, destination=self.rome, position=1, nights=3
        )

    def test_same_city_cannot_appear_twice_in_one_trip(self):
        with self.assertRaises(IntegrityError):
            TripStop.objects.create(
                trip=self.trip, destination=self.rome, position=2, nights=1
            )

    def test_two_cities_cannot_share_a_route_position(self):
        milan = Destination.objects.create(name="Milan", country="Italy")
        with self.assertRaises(IntegrityError):
            TripStop.objects.create(
                trip=self.trip, destination=milan, position=1, nights=2
            )

    def test_destination_in_use_is_protected_from_deletion(self):
        with self.assertRaises(ProtectedError):
            self.rome.delete()

    def test_deleting_a_trip_cascades_to_stops_and_items(self):
        ItineraryItem.objects.create(
            stop=self.stop, category=ItineraryItem.ACTIVITY,
            title="Colosseum", day_number=1,
        )
        self.trip.delete()
        self.assertEqual(TripStop.objects.count(), 0)
        self.assertEqual(ItineraryItem.objects.count(), 0)
        # The shared Destination survives; only the trip's own rows went away.
        self.assertEqual(Destination.objects.filter(pk=self.rome.pk).count(), 1)

    def test_one_join_request_per_person_per_trip(self):
        bob = Traveler.objects.create(
            user=User.objects.create_user("bob", "bob@illinois.edu", "pw"),
            display_name="Bob",
        )
        JoinRequest.objects.create(trip=self.trip, requester=bob)
        with self.assertRaises(IntegrityError):
            JoinRequest.objects.create(trip=self.trip, requester=bob)


# ===========================================================================
# Tests for navigation, search, chart, forms and the JSON API.
# Run with:  python manage.py test trips
# ===========================================================================
from django.test import Client
from django.urls import reverse


class A3BaseTestCase(TestCase):
    """Small shared data set: one public planned trip, one private draft, one completed."""

    @classmethod
    def setUpTestData(cls):
        cls.rome = Destination.objects.create(name="Rome", country="Italy")
        cls.lisbon = Destination.objects.create(name="Lisbon", country="Portugal")
        cls.kyoto = Destination.objects.create(name="Kyoto", country="Japan")
        cls.alice = Traveler.objects.create(
            user=User.objects.create_user("alice", "alice@illinois.edu", "pw"),
            display_name="Alice", is_domain_verified=True)
        cls.bob = Traveler.objects.create(
            user=User.objects.create_user("bob", "bob@example.com", "pw"), display_name="Bob")

        def make(title, dest, **kw):
            trip = Trip.objects.create(
                owner=cls.alice, title=title, start_date=date(2026, 5, 1), end_date=date(2026, 5, 8), **kw)
            TripStop.objects.create(trip=trip, destination=dest, position=1, nights=7)
            return trip

        cls.public = make("Italy loop", cls.rome, visibility=Trip.PUBLIC, status=Trip.PLANNED,
                          seats_open=2, budget_min_usd=1000, budget_max_usd=1500)
        cls.private = make("Secret Lisbon", cls.lisbon, visibility=Trip.PRIVATE, status=Trip.DRAFT)
        cls.done = make("Kyoto memories", cls.kyoto, visibility=Trip.PUBLIC, status=Trip.COMPLETED)


class UrlAndNavigationTests(A3BaseTestCase):
    def test_home_page_and_nav_use_named_urls(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        for name in ("trips:trip-search",):
            self.assertContains(resp, reverse(name))

    def test_get_absolute_url_matches_detail_route(self):
        self.assertEqual(self.public.get_absolute_url(), f"/trips/{self.public.pk}/")
        self.assertEqual(self.client.get(self.public.get_absolute_url()).status_code, 200)

    def test_list_links_to_detail_via_get_absolute_url(self):
        self.assertContains(self.client.get(reverse("trips:trip-list")), self.public.get_absolute_url())


class SearchTests(A3BaseTestCase):
    def test_full_list_never_contains_private_trips(self):
        resp = self.client.get(reverse("trips:trip-search"))
        self.assertContains(resp, "Italy loop")
        self.assertNotContains(resp, "Secret Lisbon")

    def test_get_search_spans_relationships(self):
        resp = self.client.get(reverse("trips:trip-search"), {"q": "Italy"})   # matches destination *country*
        self.assertEqual([t.title for t in resp.context["search_results"]], ["Italy loop"])

    def test_get_tab_filters_by_status(self):
        resp = self.client.get(reverse("trips:trip-search"), {"tab": "completed"})
        self.assertEqual([t.title for t in resp.context["search_results"]], ["Kyoto memories"])

    def test_post_budget_search(self):
        resp = self.client.post(reverse("trips:trip-search"), {"max_budget": "1200", "group_size": "2"})
        self.assertEqual([t.title for t in resp.context["budget_results"]], ["Italy loop"])
        resp = self.client.post(reverse("trips:trip-search"), {"max_budget": "500", "group_size": "1"})
        self.assertEqual(list(resp.context["budget_results"]), [])

    def test_post_budget_search_rejects_junk(self):
        resp = self.client.post(reverse("trips:trip-search"), {"max_budget": "abc"})
        self.assertIsNotNone(resp.context["budget_error"])

    def test_post_requires_csrf_token(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(reverse("trips:trip-search"), {"max_budget": "1200"}).status_code, 403)

    def test_aggregations_present(self):
        ctx = self.client.get(reverse("trips:trip-search")).context
        self.assertEqual(ctx["total_trips"], 3)
        self.assertEqual(ctx["public_trips"], 2)
        rome = [d for d in ctx["trips_per_destination"] if d.name == "Rome"][0]
        self.assertEqual(rome.n_trips, 1)
