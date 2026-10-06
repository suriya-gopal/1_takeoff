"""Budget conversion: exchange-rate lookups (mocked), analysis and the page and API built on them."""

from datetime import date
from decimal import Decimal
from unittest import mock

import requests
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import budget
from .factories import make_destination, make_traveler, make_trip
from .models import Trip


def rates_response(rate="0.9", date_="2026-10-05", status=200):
    response = mock.Mock(status_code=status)
    response.json.return_value = {"amount": 1.0, "base": "USD", "date": date_, "rates": {"EUR": float(rate)}}
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    return response


class FetchRateTests(SimpleTestCase):
    @mock.patch("trips.budget.requests.get")
    def test_asks_for_one_dollar_in_the_chosen_currency_with_a_timeout(self, get):
        get.return_value = rates_response("0.9")
        rate, as_of = budget.fetch_usd_rate("EUR")
        self.assertEqual((rate, as_of), (Decimal("0.9"), "2026-10-05"))
        _, kwargs = get.call_args
        self.assertEqual(kwargs["params"], {"base": "USD", "symbols": "EUR"})
        self.assertEqual(kwargs["timeout"], 5)

    @mock.patch("trips.budget.requests.get")
    def test_dollars_need_no_lookup(self, get):
        self.assertEqual(budget.fetch_usd_rate("USD"), (Decimal("1"), None))
        get.assert_not_called()

    @mock.patch("trips.budget.requests.get", side_effect=requests.Timeout)
    def test_timeout_becomes_504(self, _):
        with self.assertRaises(budget.RateServiceError) as ctx:
            budget.fetch_usd_rate("EUR")
        self.assertEqual(ctx.exception.status, 504)

    @mock.patch("trips.budget.requests.get", side_effect=requests.ConnectionError)
    def test_unreachable_service_becomes_502(self, _):
        with self.assertRaises(budget.RateServiceError) as ctx:
            budget.fetch_usd_rate("EUR")
        self.assertEqual(ctx.exception.status, 502)

    @mock.patch("trips.budget.requests.get")
    def test_unknown_currency_becomes_400(self, get):
        get.return_value = rates_response(status=404)
        with self.assertRaises(budget.UnsupportedCurrency):
            budget.fetch_usd_rate("ABC")

    @mock.patch("trips.budget.requests.get")
    def test_server_error_becomes_502(self, get):
        get.return_value = rates_response(status=500)
        with self.assertRaises(budget.RateServiceError) as ctx:
            budget.fetch_usd_rate("EUR")
        self.assertEqual(ctx.exception.status, 502)

    @mock.patch("trips.budget.requests.get")
    def test_unexpected_body_becomes_502(self, get):
        response = mock.Mock()
        response.json.return_value = {"unexpected": True}
        get.return_value = response
        with self.assertRaises(budget.RateServiceError):
            budget.fetch_usd_rate("EUR")


class AssessmentTests(SimpleTestCase):
    def test_compares_typical_cost_with_the_budget_range(self):
        low, high = Decimal("1000"), Decimal("2000")
        self.assertEqual(budget.assess(Decimal("2500"), low, high)["status"], "over")
        self.assertEqual(budget.assess(Decimal("1500"), low, high)["status"], "within")
        self.assertEqual(budget.assess(Decimal("800"), low, high)["status"], "under")
        self.assertEqual(budget.assess(None, low, high)["status"], "unknown")
        self.assertEqual(budget.assess(Decimal("800"), Decimal("0"), Decimal("0"))["status"], "unset")


class BudgetViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = make_traveler()
        rome = make_destination("Rome", "Italy", "100.00")
        cls.public = make_trip(
            owner, rome, "Italy loop", date(2026, 5, 1), nights=5, visibility=Trip.PUBLIC,
            status=Trip.PLANNED, budget_min_usd=400, budget_max_usd=800)
        cls.private = make_trip(owner, rome, "Secret", date(2026, 6, 1), visibility=Trip.PRIVATE)

    @mock.patch("trips.budget.requests.get")
    def test_api_returns_converted_budget_and_assessment(self, get):
        get.return_value = rates_response("0.9")
        data = self.client.get(reverse("trips:api-trip-budget", args=[self.public.pk]), {"currency": "eur"}).json()
        self.assertEqual(data["currency"], "EUR")
        self.assertEqual(data["budget_per_person"]["max_local"], 720.0)
        self.assertEqual(data["estimate_per_person"]["usd"], 500.0)
        self.assertEqual(data["estimate_per_person"]["local"], 450.0)
        self.assertEqual(data["assessment"]["status"], "within")

    def test_api_requires_a_currency(self):
        response = self.client.get(reverse("trips:api-trip-budget", args=[self.public.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_api_rejects_malformed_currency_without_calling_out(self):
        with mock.patch("trips.budget.requests.get") as get:
            response = self.client.get(reverse("trips:api-trip-budget", args=[self.public.pk]), {"currency": "EURO1"})
        self.assertEqual(response.status_code, 400)
        get.assert_not_called()

    def test_api_hides_private_and_unknown_trips(self):
        for pk in (self.private.pk, 99999):
            response = self.client.get(reverse("trips:api-trip-budget", args=[pk]), {"currency": "EUR"})
            self.assertEqual(response.status_code, 404)

    @mock.patch("trips.budget.requests.get", side_effect=requests.Timeout)
    def test_api_reports_upstream_failure_as_json(self, _):
        response = self.client.get(reverse("trips:api-trip-budget", args=[self.public.pk]), {"currency": "EUR"})
        self.assertEqual(response.status_code, 504)
        self.assertIn("error", response.json())

    def test_page_preselects_the_currency_of_the_first_stop(self):
        response = self.client.get(reverse("trips:trip-budget", args=[self.public.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected"], "EUR")
        self.assertIsNone(response.context["report"])

    @mock.patch("trips.budget.requests.get")
    def test_page_shows_the_conversion(self, get):
        get.return_value = rates_response("0.9")
        response = self.client.get(reverse("trips:trip-budget", args=[self.public.pk]), {"currency": "EUR"})
        self.assertContains(response, "Typical costs along the route")
        self.assertContains(response, "Frankfurter")

    @mock.patch("trips.budget.requests.get", side_effect=requests.ConnectionError)
    def test_page_explains_when_rates_are_unavailable(self, _):
        response = self.client.get(reverse("trips:trip-budget", args=[self.public.pk]), {"currency": "EUR"})
        self.assertEqual(response.status_code, 502)
        self.assertContains(response, "could not be reached", status_code=502)

    def test_trip_page_links_to_the_conversion(self):
        response = self.client.get(self.public.get_absolute_url())
        self.assertContains(response, reverse("trips:trip-budget", args=[self.public.pk]))
