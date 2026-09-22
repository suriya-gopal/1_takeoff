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
