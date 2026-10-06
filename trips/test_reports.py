"""The community report page."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from .factories import make_destination, make_traveler, make_trip
from .models import JoinRequest, Trip


class ReportsPageTests(TestCase):
    def test_empty_report_shows_empty_rows_and_zero_totals(self):
        response = self.client.get(reverse("trips:reports"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No community trips yet.", count=2)
        self.assertContains(response, "No join requests yet.")
        self.assertEqual(response.context["total_trips"], 0)

    def test_report_groups_public_trips_and_totals_them(self):
        owner, guest = make_traveler("alice"), make_traveler("bob", verified=False)
        rome = make_destination("Rome", "Italy")
        planned = make_trip(owner, rome, "Italy loop", date(2026, 5, 1), visibility=Trip.PUBLIC,
                            status=Trip.PLANNED, seats_open=3)
        make_trip(owner, rome, "Old Rome", date(2025, 5, 1), visibility=Trip.PUBLIC, status=Trip.COMPLETED)
        make_trip(owner, rome, "Secret", date(2026, 8, 1), visibility=Trip.PRIVATE, seats_open=9)
        JoinRequest.objects.create(trip=planned, requester=guest)

        ctx = self.client.get(reverse("trips:reports")).context
        self.assertEqual(ctx["total_trips"], 2)
        self.assertEqual(ctx["total_seats_open"], 3)
        self.assertEqual(ctx["total_requests"], 1)
        rome_row = ctx["trips_per_destination"][0]
        self.assertEqual((rome_row.n_trips, rome_row.n_planned, rome_row.n_completed), (2, 1, 1))
        self.assertEqual({r["label"] for r in ctx["trips_per_status"]}, {"Planned", "Completed"})

    def test_page_has_both_download_buttons(self):
        response = self.client.get(reverse("trips:reports"))
        self.assertContains(response, reverse("trips:export-trips-csv"))
        self.assertContains(response, reverse("trips:export-trips-json"))
        self.assertContains(response, "Download CSV")
        self.assertContains(response, "Download JSON")
