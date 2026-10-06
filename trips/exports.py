"""Downloadable CSV and JSON exports of the community's public trips."""

import csv

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_safe

from .models import Trip

CSV_COLUMNS = [
    "trip_id", "title", "status", "start_date", "end_date", "nights", "route",
    "budget_min_usd", "budget_max_usd", "group_size", "seats_open", "owner", "owner_verified",
]


def _public_trips():
    """Public trips in departure order. Private trips are never exported."""
    return (
        Trip.objects.filter(visibility=Trip.PUBLIC)
        .select_related("owner")
        .prefetch_related("stops__destination")
        .order_by("start_date", "title")
    )


def _record(trip):
    return {
        "trip_id": trip.pk,
        "title": trip.title,
        "status": trip.status,
        "start_date": trip.start_date.isoformat(),
        "end_date": trip.end_date.isoformat(),
        "nights": trip.duration_nights,
        "route": [stop.destination.name for stop in trip.stops.all()],
        "budget_min_usd": float(trip.budget_min_usd),
        "budget_max_usd": float(trip.budget_max_usd),
        "group_size": trip.group_size,
        "seats_open": trip.seats_open,
        "owner": trip.owner.display_name,
        "owner_verified": trip.owner.is_domain_verified,
    }


def _spreadsheet_safe(value):
    """Stop spreadsheet apps from running a cell as a formula when user-written text starts with =, +, - or @."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _stamp():
    return timezone.localtime().strftime("%Y-%m-%d_%H-%M")


@require_safe
def export_trips_csv(request):
    """GET /export/trips.csv — public trips as a spreadsheet, named trips_YYYY-MM-DD_HH-MM.csv."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="trips_{_stamp()}.csv"'

    writer = csv.writer(response)
    writer.writerow(CSV_COLUMNS)
    for trip in _public_trips():
        record = _record(trip)
        record["route"] = " > ".join(record["route"])
        record["budget_min_usd"] = f'{record["budget_min_usd"]:.2f}'
        record["budget_max_usd"] = f'{record["budget_max_usd"]:.2f}'
        writer.writerow([_spreadsheet_safe(record[column]) for column in CSV_COLUMNS])
    return response


@require_safe
def export_trips_json(request):
    """GET /export/trips.json — the same trips as formatted JSON with generation metadata."""
    trips = [_record(trip) for trip in _public_trips()]
    payload = {
        "generated_at": timezone.localtime().isoformat(timespec="seconds"),
        "record_count": len(trips),
        "trips": trips,
    }
    response = JsonResponse(payload, json_dumps_params={"indent": 2})
    response["Content-Disposition"] = f'attachment; filename="trips_{_stamp()}.json"'
    return response
