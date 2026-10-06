"""
Community insights: chart-ready JSON feeds, the Vega-Lite chart definitions and the Insights page.

Feeds (public trips only, plain JSON arrays so any charting tool can read them):
    /api/insights/destinations/   public trips per destination
    /api/insights/departures/     public trips departing per month

Chart definitions are served as JSON from /insights/specs/ so the page, and anyone
experimenting in the Vega editor, always chart the live feeds.
"""

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from .models import Destination, Trip
from .views import destination_popularity

VEGA_LITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"

# Navy, sky and sun come from the TakeOff logo; the rest keep neighbouring bars distinguishable.
CHART_COLORS = ["#0b2f6b", "#18a0f0", "#ffb62d", "#2f8f6b", "#8a5cf5", "#e4572e", "#5b6b85"]


# ---------------------------------------------------------------------------
# Feed data
# ---------------------------------------------------------------------------
def destination_summary():
    """Destinations that public trips visit, most visited first."""
    rows = [d for d in destination_popularity() if d.n_public]
    rows.sort(key=lambda d: (-d.n_public, d.name))
    return [
        {
            "destination": d.name,
            "country": d.country,
            "public_trips": d.n_public,
            "avg_daily_cost_usd": float(d.avg_daily_cost_usd),
        }
        for d in rows
    ]


def monthly_departures():
    """
    Public trips and open seats by departure month, with a row for every month between the
    first and last departure so a line chart shows quiet months as zero instead of skipping them.
    """
    by_month = {
        row["month"]: row
        for row in (
            Trip.objects.filter(visibility=Trip.PUBLIC)
            .annotate(month=TruncMonth("start_date"))
            .values("month")
            .annotate(public_trips=Count("trip_id"), seats_open=Sum("seats_open"))
        )
    }
    if not by_month:
        return []

    first, last = min(by_month), max(by_month)
    series = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        key = first.replace(year=year, month=month)
        row = by_month.get(key)
        series.append({
            "month": key.isoformat(),
            "public_trips": row["public_trips"] if row else 0,
            "seats_open": row["seats_open"] if row else 0,
        })
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return series


def api_destination_summary(request):
    """GET /api/insights/destinations/ — one record per destination."""
    return JsonResponse(destination_summary(), safe=False)


def api_monthly_departures(request):
    """GET /api/insights/departures/ — one record per month."""
    return JsonResponse(monthly_departures(), safe=False)


# ---------------------------------------------------------------------------
# Vega-Lite chart definitions
# ---------------------------------------------------------------------------
def whole_numbers(max_value):
    """Axis tick values 0..max_value so counts of trips are never labelled with fractions."""
    return list(range(0, max(int(max_value), 1) + 1))


def destination_chart_spec(data_url, max_value=1):
    """Bar chart: public trips per destination, coloured by country."""
    return {
        "$schema": VEGA_LITE_SCHEMA,
        "description": "Public trips per destination",
        "data": {"url": data_url},
        "width": "container",
        "height": 320,
        "mark": {"type": "bar", "cornerRadiusEnd": 4},
        "encoding": {
            "x": {
                "field": "destination", "type": "nominal", "sort": "-y", "title": None,
                "axis": {"labelAngle": -35, "labelLimit": 120},
            },
            "y": {
                "field": "public_trips", "type": "quantitative", "title": "Community trips",
                "axis": {"tickMinStep": 1, "format": "d", "values": whole_numbers(max_value)},
            },
            "color": {
                "field": "country", "type": "nominal", "title": "Country",
                "scale": {"range": CHART_COLORS},
            },
            "tooltip": [
                {"field": "destination", "title": "Destination"},
                {"field": "country", "title": "Country"},
                {"field": "public_trips", "title": "Community trips"},
                {"field": "avg_daily_cost_usd", "title": "Avg. daily cost (USD)", "format": "$,.0f"},
            ],
        },
    }


def departure_chart_spec(data_url, max_value=1):
    """Line chart: public trips departing each month."""
    return {
        "$schema": VEGA_LITE_SCHEMA,
        "description": "Public trips departing per month",
        "data": {"url": data_url},
        "width": "container",
        "height": 280,
        "mark": {
            "type": "line", "color": CHART_COLORS[0], "strokeWidth": 3,
            "point": {"filled": True, "size": 80, "color": CHART_COLORS[1]},
        },
        "encoding": {
            "x": {
                "field": "month", "type": "temporal", "timeUnit": "utcyearmonth", "title": None,
                "axis": {"format": "%b %Y", "labelAngle": -30},
            },
            "y": {
                "field": "public_trips", "type": "quantitative", "title": "Trips departing",
                "axis": {"tickMinStep": 1, "format": "d", "values": whole_numbers(max_value)}, "scale": {"zero": True},
            },
            "tooltip": [
                {"field": "month", "type": "temporal", "timeUnit": "utcyearmonth", "title": "Month"},
                {"field": "public_trips", "title": "Trips departing"},
                {"field": "seats_open", "title": "Seats open"},
            ],
        },
    }


def destination_chart_json(request):
    """GET /insights/specs/destinations.json"""
    peak = max((row["public_trips"] for row in destination_summary()), default=1)
    spec = destination_chart_spec(reverse("trips:api-insights-destinations"), peak)
    return JsonResponse(spec, json_dumps_params={"indent": 2})


def departure_chart_json(request):
    """GET /insights/specs/departures.json"""
    peak = max((row["public_trips"] for row in monthly_departures()), default=1)
    spec = departure_chart_spec(reverse("trips:api-insights-departures"), peak)
    return JsonResponse(spec, json_dumps_params={"indent": 2})


# ---------------------------------------------------------------------------
# Insights page
# ---------------------------------------------------------------------------
def insights_page(request):
    """Popular destinations and departure timing, charted from the live feeds."""
    feeds = [
        {"label": "Trips per destination", "url": reverse("trips:api-insights-destinations")},
        {"label": "Departures per month", "url": reverse("trips:api-insights-departures")},
    ]
    return render(request, "trips/insights.html", {
        "rows": destination_popularity(),
        "feeds": feeds,
        "destinations_spec_url": reverse("trips:chart-spec-destinations"),
        "departures_spec_url": reverse("trips:chart-spec-departures"),
    })
