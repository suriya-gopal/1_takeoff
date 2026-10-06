"""Chart feeds, chart definitions, cross-origin access and the Insights page."""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from .factories import make_destination, make_traveler, make_trip
from .models import Trip


class ChartFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = make_traveler()
        rome = make_destination("Rome", "Italy", "125.00")
        lisbon = make_destination("Lisbon", "Portugal", "95.00")
        make_trip(owner, rome, "Italy loop", date(2026, 3, 10), visibility=Trip.PUBLIC, seats_open=2)
        make_trip(owner, rome, "Rome again", date(2026, 5, 2), visibility=Trip.PUBLIC, seats_open=1)
        make_trip(owner, lisbon, "Secret Lisbon", date(2026, 4, 2), visibility=Trip.PRIVATE)

    def test_destination_feed_is_a_plain_array_of_public_trip_counts(self):
        response = self.client.get(reverse("trips:api-insights-destinations"))
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), [
            {"destination": "Rome", "country": "Italy", "public_trips": 2, "avg_daily_cost_usd": 125.0},
        ])

    def test_departure_feed_fills_quiet_months_with_zero(self):
        rows = self.client.get(reverse("trips:api-insights-departures")).json()
        self.assertEqual([r["month"] for r in rows], ["2026-03-01", "2026-04-01", "2026-05-01"])
        self.assertEqual([r["public_trips"] for r in rows], [1, 0, 1])
        self.assertEqual([r["seats_open"] for r in rows], [2, 0, 1])

    def test_feeds_are_empty_arrays_without_public_trips(self):
        Trip.objects.all().delete()
        self.assertEqual(self.client.get(reverse("trips:api-insights-destinations")).json(), [])
        self.assertEqual(self.client.get(reverse("trips:api-insights-departures")).json(), [])


class ChartDefinitionTests(TestCase):
    def test_bar_chart_reads_its_feed_by_url(self):
        spec = self.client.get(reverse("trips:chart-spec-destinations")).json()
        self.assertEqual(spec["data"], {"url": reverse("trips:api-insights-destinations")})
        self.assertNotIn("values", spec["data"])
        self.assertEqual(spec["mark"]["type"], "bar")

    def test_line_chart_reads_its_feed_by_url(self):
        spec = self.client.get(reverse("trips:chart-spec-departures")).json()
        self.assertEqual(spec["data"], {"url": reverse("trips:api-insights-departures")})
        self.assertEqual(spec["mark"]["type"], "line")


class CrossOriginTests(TestCase):
    def test_vega_editor_may_read_the_feeds(self):
        response = self.client.get(
            reverse("trips:api-insights-destinations"), HTTP_ORIGIN="https://vega.github.io")
        self.assertEqual(response["Access-Control-Allow-Origin"], "https://vega.github.io")

    def test_other_origins_and_pages_get_no_cors_header(self):
        feed = self.client.get(reverse("trips:api-insights-destinations"), HTTP_ORIGIN="https://example.com")
        page = self.client.get(reverse("trips:home"), HTTP_ORIGIN="https://vega.github.io")
        self.assertNotIn("Access-Control-Allow-Origin", feed)
        self.assertNotIn("Access-Control-Allow-Origin", page)


class InsightsPageTests(TestCase):
    def test_page_embeds_both_charts_with_a_text_fallback(self):
        response = self.client.get(reverse("trips:insights"))
        self.assertContains(response, reverse("trips:chart-spec-destinations"))
        self.assertContains(response, reverse("trips:chart-spec-departures"))
        self.assertContains(response, "vega-embed")
        self.assertContains(response, "<figcaption>")
        self.assertContains(response, "alt=")
