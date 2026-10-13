"""Small helpers for building test data."""

from datetime import date

from django.contrib.auth.models import User

from .models import Destination, Traveler, Trip, TripStop


def make_traveler(username="alice", verified=True):
    user = User.objects.create_user(username, f"{username}@illinois.edu", "pw")
    return Traveler.objects.create(user=user, display_name=username.title(), is_domain_verified=verified)


def make_destination(name="Rome", country="Italy", daily_cost="100.00"):
    return Destination.objects.create(name=name, country=country, avg_daily_cost_usd=daily_cost)


def make_trip(owner, destination, title="Italy loop", start=date(2026, 5, 1), nights=5, **fields):
    """A trip with one stop covering all its nights."""
    trip = Trip.objects.create(
        owner=owner, title=title, start_date=start,
        end_date=date.fromordinal(start.toordinal() + nights), **fields,
    )
    TripStop.objects.create(trip=trip, destination=destination, position=1, nights=nights)
    return trip


class SignedInMixin:
    """
    Test-case mixin: every test starts with the test client signed in.

    Most pages and APIs require login, so tests that are about what a page shows (rather than about
    who may see it) sign in first. Set `signed_in_as` to a username to choose the account.
    """

    signed_in_as = "viewer"

    def setUp(self):
        super().setUp()
        user = User.objects.filter(username=self.signed_in_as).first()
        if user is None:
            user = User.objects.create_user(self.signed_in_as, f"{self.signed_in_as}@illinois.edu", "pw")
        self.client.force_login(user)
