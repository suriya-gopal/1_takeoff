"""Every page and endpoint answers, and unknown addresses get the branded 404 page."""

from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from .factories import make_destination, make_traveler, make_trip
from .models import Trip


class SiteRouteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        trip = make_trip(make_traveler(), make_destination(), "Italy loop", date(2026, 5, 1),
                         visibility=Trip.PUBLIC, status=Trip.PLANNED, seats_open=2)
        cls.pk = trip.pk

    def test_named_routes_respond_successfully(self):
        names = [
            "home", "trip-manual", "trip-list", "trip-list-generic", "trip-search", "trip-create",
            "insights", "chart-spec-destinations", "chart-spec-departures", "chart-trips-by-destination",
            "reports", "export-trips-csv", "export-trips-json", "api-trips", "api-destinations",
            "api-destinations-popular", "api-insights-destinations", "api-insights-departures",
            "api-ping-json", "api-ping-http-manual-json", "api-ping-http-default", "api-ping-http-text",
        ]
        for name in names:
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(f"trips:{name}")).status_code, 200)
        for name in ("trip-detail", "trip-budget"):
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(f"trips:{name}", args=[self.pk])).status_code, 200)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
    def test_unknown_address_shows_the_site_404_page(self):
        response = self.client.get("/no/such/page/")
        self.assertContains(response, "We couldn&rsquo;t find that page", status_code=404)

    def test_navigation_links_to_insights_and_reports(self):
        response = self.client.get(reverse("trips:home"))
        self.assertContains(response, reverse("trips:insights"))
        self.assertContains(response, reverse("trips:reports"))
