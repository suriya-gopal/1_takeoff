"""
Trip budgets in local currencies.

A trip's budget is stored in US dollars. This module converts it with live exchange rates from the
free Frankfurter service (https://frankfurter.dev, no API key) and sets it against what the route is
expected to cost, using the average daily cost kept on each destination. Rates are fetched when a
page or endpoint is requested and are never saved.

    /trips/<id>/budget/?currency=EUR        page with the conversion
    /api/trips/<id>/budget/?currency=EUR    the same result as JSON (public trips only)
"""

import re
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import Trip

RATES_URL = "https://api.frankfurter.dev/v1/latest"
REQUEST_TIMEOUT_SECONDS = 5
CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")

# Currencies offered in the picker (ISO 4217 code -> name). Any other three-letter code is still
# accepted; the rates service decides whether it can convert it.
CURRENCY_NAMES = {
    "AUD": "Australian dollar", "BGN": "Bulgarian lev", "BRL": "Brazilian real", "CAD": "Canadian dollar",
    "CHF": "Swiss franc", "CNY": "Chinese yuan", "CZK": "Czech koruna", "DKK": "Danish krone",
    "EUR": "Euro", "GBP": "British pound", "HKD": "Hong Kong dollar", "HUF": "Hungarian forint",
    "IDR": "Indonesian rupiah", "ILS": "Israeli shekel", "INR": "Indian rupee", "ISK": "Icelandic krona",
    "JPY": "Japanese yen", "KRW": "South Korean won", "MXN": "Mexican peso", "MYR": "Malaysian ringgit",
    "NOK": "Norwegian krone", "NZD": "New Zealand dollar", "PHP": "Philippine peso", "PLN": "Polish zloty",
    "RON": "Romanian leu", "SEK": "Swedish krona", "SGD": "Singapore dollar", "THB": "Thai baht",
    "TRY": "Turkish lira", "USD": "US dollar", "ZAR": "South African rand",
}
CURRENCY_CHOICES = sorted(CURRENCY_NAMES.items(), key=lambda item: item[1])

# Used to pre-select the picker with the currency of the trip's first stop.
COUNTRY_CURRENCY = {
    "Australia": "AUD", "Canada": "CAD", "France": "EUR", "Germany": "EUR", "Greece": "EUR",
    "Iceland": "ISK", "India": "INR", "Ireland": "EUR", "Italy": "EUR", "Japan": "JPY",
    "Mexico": "MXN", "Netherlands": "EUR", "Portugal": "EUR", "Singapore": "SGD", "South Korea": "KRW",
    "Spain": "EUR", "Switzerland": "CHF", "Thailand": "THB", "United Kingdom": "GBP",
    "United States": "USD",
}

TWO_PLACES = Decimal("0.01")


class RateServiceError(Exception):
    """The exchange-rate service could not provide a rate. `status` is the HTTP status to answer with."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class UnsupportedCurrency(RateServiceError):
    """The requested currency is not one the rates service converts."""

    def __init__(self, code):
        super().__init__(f"{code} is not a currency we can convert to.", status=400)


# ---------------------------------------------------------------------------
# Exchange rates
# ---------------------------------------------------------------------------
def fetch_usd_rate(currency):
    """
    Return (rate, as_of): how many units of `currency` one US dollar buys, and the date of the rate.

    Raises RateServiceError when the service is slow, unreachable or answers with something unusable.
    """
    if currency == "USD":
        return Decimal("1"), None

    try:
        response = requests.get(
            RATES_URL,
            params={"base": "USD", "symbols": currency},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        rate = Decimal(str(payload["rates"][currency]))
        as_of = payload["date"]
    except requests.Timeout:
        raise RateServiceError("The exchange-rate service took too long to respond.", status=504)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (404, 422):
            raise UnsupportedCurrency(currency)
        raise RateServiceError("The exchange-rate service returned an error.")
    except requests.RequestException:
        raise RateServiceError("The exchange-rate service could not be reached.")
    except (ValueError, KeyError, TypeError, ArithmeticError):
        raise RateServiceError("The exchange-rate service sent an unexpected response.")

    if rate <= 0:
        raise RateServiceError("The exchange-rate service sent an unexpected response.")
    return rate, as_of


# ---------------------------------------------------------------------------
# Budget analysis
# ---------------------------------------------------------------------------
def to_local(amount_usd, rate):
    """Convert a US dollar amount, rounded to two decimal places."""
    return (Decimal(amount_usd) * rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def assess(estimate_usd, budget_min, budget_max):
    """Compare the expected cost of the route with the traveler's budget range (per person)."""
    if budget_max <= 0:
        return {"status": "unset", "message": "Set a budget range on this trip to compare it with typical costs."}
    if estimate_usd is None:
        return {"status": "unknown", "message": "Add stops to this trip to compare its budget with typical costs."}
    if estimate_usd > budget_max:
        over = (estimate_usd - budget_max).quantize(TWO_PLACES)
        return {"status": "over", "message": f"Typical costs for this route run ${over:,.0f} above the top of the budget."}
    if estimate_usd < budget_min:
        under = (budget_min - estimate_usd).quantize(TWO_PLACES)
        return {"status": "under", "message": f"Typical costs for this route sit ${under:,.0f} below the bottom of the budget."}
    return {"status": "within", "message": "Typical costs for this route fall inside the budget range."}


def build_budget_report(trip, currency, rate, as_of):
    """The trip's budget and route costs in `currency`, plus how the budget compares with typical costs."""
    route = []
    total_nights = 0
    total_usd = Decimal("0")
    for stop in trip.stops.select_related("destination"):
        stop_usd = stop.destination.avg_daily_cost_usd * stop.nights
        total_nights += stop.nights
        total_usd += stop_usd
        route.append({
            "destination": stop.destination.name,
            "country": stop.destination.country,
            "nights": stop.nights,
            "avg_daily_cost_usd": float(stop.destination.avg_daily_cost_usd),
            "estimated_usd": float(stop_usd),
            "estimated_local": float(to_local(stop_usd, rate)),
        })

    has_estimate = bool(route) and total_usd > 0
    estimate = None
    if has_estimate:
        estimate = {
            "nights": total_nights,
            "usd": float(total_usd),
            "local": float(to_local(total_usd, rate)),
            "per_night_usd": float((total_usd / total_nights).quantize(TWO_PLACES)),
        }

    return {
        "trip": {
            "trip_id": trip.pk,
            "title": trip.title,
            "nights": trip.duration_nights,
            "group_size": trip.group_size,
            "url": trip.get_absolute_url(),
        },
        "currency": currency,
        "currency_name": CURRENCY_NAMES.get(currency, currency),
        "rate": {"usd_to_local": float(rate), "as_of": as_of, "source": "Frankfurter"},
        "budget_per_person": {
            "min_usd": float(trip.budget_min_usd),
            "max_usd": float(trip.budget_max_usd),
            "min_local": float(to_local(trip.budget_min_usd, rate)),
            "max_local": float(to_local(trip.budget_max_usd, rate)),
        },
        "route": route,
        "estimate_per_person": estimate,
        "assessment": assess(total_usd if has_estimate else None, trip.budget_min_usd, trip.budget_max_usd),
    }


def suggested_currency(trip):
    """Currency of the first stop's country, or an empty string when we have no suggestion."""
    first_stop = trip.stops.select_related("destination").first()
    return COUNTRY_CURRENCY.get(first_stop.destination.country, "") if first_stop else ""


def clean_currency(raw):
    """Upper-case a requested code; return None unless it looks like an ISO 4217 code."""
    code = (raw or "").strip().upper()
    return code if CURRENCY_CODE.match(code) else None


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
def api_trip_budget(request, pk):
    """
    GET /api/trips/<id>/budget/?currency=EUR

    JSON budget conversion for a public trip. Responds 400 for a missing or unsupported currency,
    404 for an unknown or private trip, and 502/504 when the rates service fails.
    """
    trip = Trip.objects.filter(pk=pk, visibility=Trip.PUBLIC).first()
    if trip is None:
        return JsonResponse({"error": "Trip not found."}, status=404)

    currency = clean_currency(request.GET.get("currency"))
    if currency is None:
        return JsonResponse(
            {"error": "Add ?currency= with a three-letter currency code, for example ?currency=EUR."},
            status=400,
        )

    try:
        rate, as_of = fetch_usd_rate(currency)
    except RateServiceError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
    return JsonResponse(build_budget_report(trip, currency, rate, as_of))


def trip_budget_page(request, pk):
    """Page showing a trip's budget in the currency chosen in the picker."""
    trip = get_object_or_404(Trip, pk=pk)
    context = {
        "trip": trip,
        "currencies": CURRENCY_CHOICES,
        "selected": suggested_currency(trip),
        "report": None,
        "error": None,
    }
    status = 200

    if "currency" in request.GET:
        context["selected"] = request.GET["currency"].strip().upper()
        currency = clean_currency(request.GET["currency"])
        if currency is None:
            context["error"] = "Choose a currency to convert to."
            status = 400
        else:
            try:
                rate, as_of = fetch_usd_rate(currency)
                context["report"] = build_budget_report(trip, currency, rate, as_of)
            except RateServiceError as exc:
                context["error"] = str(exc)
                status = exc.status

    return render(request, "trips/trip_budget.html", context, status=status)
