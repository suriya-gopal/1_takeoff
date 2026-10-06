"""Page views, search, the plan-a-trip form, the chart image and the JSON API for the trips app."""

import json
from decimal import Decimal, InvalidOperation
from io import BytesIO

import matplotlib
matplotlib.use("Agg")  # draw to memory only; a server has no display
import matplotlib.pyplot as plt
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import CreateView, ListView
from matplotlib.ticker import MaxNLocator

from .forms import JoinRequestForm, TripForm
from .models import Destination, JoinRequest, Trip


def destination_popularity():
    """
    Destinations ranked by how many trips visit them.

    Shared by the home page, the search summaries, the insights charts and the API so
    their numbers always agree.
    """
    return (
        Destination.objects
        # Destination <- TripStop <- Trip: 'stops__trip' spans two relationships. distinct=True
        # because the join can repeat a trip and each trip should be counted once.
        .annotate(
            n_trips=Count("stops__trip", distinct=True),
            n_public=Count("stops__trip", filter=Q(stops__trip__visibility=Trip.PUBLIC), distinct=True),
        )
        .filter(n_trips__gt=0)  # hide cities nobody has planned to visit
        .order_by("-n_trips", "name")
    )


# ---------------------------------------------------------------------------
# Home and trip pages
# ---------------------------------------------------------------------------
def home(request):
    """Landing page: community-posted trips plus the most popular destinations."""
    trips = (
        Trip.objects.filter(visibility=Trip.PUBLIC)
        .select_related("owner")
        .prefetch_related("stops__destination")[:6]
    )
    return render(request, "trips/home.html", {"trips": trips, "popular": destination_popularity()[:4]})


def trip_manual_view(request):
    """Quick feed of public trips, rendered through the template loader."""
    template = loader.get_template("trips/trip_list_manual.html")
    trips = Trip.objects.filter(visibility=Trip.PUBLIC)
    return HttpResponse(template.render({"trips": trips}, request))


def trip_list_view(request):
    """Every trip, soonest departure first."""
    trips = Trip.objects.select_related("owner").prefetch_related("stops__destination")
    return render(request, "trips/trip_list.html", {"trips": trips})


class TripListView(ListView):
    """Community trips (public only). Shares its template with trip_list_view."""

    model = Trip
    template_name = "trips/trip_list.html"
    context_object_name = "trips"
    queryset = Trip.objects.filter(visibility=Trip.PUBLIC)


class TripDetailView(View):
    """
    One trip: its route, its join requests and the "Request to join" form.

    GET shows the page with an empty form. POST validates the form, saves a join request
    and redirects back to the trip.
    """

    def _render(self, request, trip, form, status=200):
        return render(
            request,
            "trips/trip_detail.html",
            {
                "trip": trip,
                "stops": trip.stops.all(),
                "join_requests": trip.join_requests.all(),
                "form": form,
            },
            status=status,
        )

    def get(self, request, pk):
        trip = get_object_or_404(Trip, pk=pk)
        return self._render(request, trip, JoinRequestForm(trip=trip))

    def post(self, request, pk):
        trip = get_object_or_404(Trip, pk=pk)
        form = JoinRequestForm(request.POST, trip=trip)
        if form.is_valid():
            form.save()
            return redirect(trip.get_absolute_url())  # redirect so a refresh cannot re-submit the form
        return self._render(request, trip, form, status=400)


class TripCreateView(CreateView):
    """
    "Plan your trip" form. A valid submission saves the trip with its stops and redirects to the
    new trip's page (CreateView falls back to Trip.get_absolute_url).
    """

    model = Trip
    form_class = TripForm
    template_name = "trips/trip_form.html"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
class TripSearchView(ListView):
    """
    Search page with two forms:

      GET  /trips/search/?q=lisbon&tab=planned  filter public trips by destination, country, date, status
      POST /trips/search/                       find open trips within a budget and group size

    The filter uses GET so a result link can be bookmarked or shared. The budget search uses POST
    so a personal budget stays out of the URL, browser history and server logs.
    """

    model = Trip
    template_name = "trips/trip_search.html"
    context_object_name = "trips"

    def get_queryset(self):
        # Only public trips: a page reachable by a plain link must never expose private ones.
        return (
            Trip.objects.filter(visibility=Trip.PUBLIC)
            .select_related("owner")
            .prefetch_related("stops__destination")
        )

    def post(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()

        budget_error = None
        budget_results = None
        raw_budget = request.POST.get("max_budget", "").strip()
        raw_group = request.POST.get("group_size", "").strip()

        try:
            max_budget = Decimal(raw_budget)
            group_size = int(raw_group or 1)
            if max_budget < 0 or group_size < 1:
                raise ValueError
        except (InvalidOperation, ValueError):
            budget_error = "Enter a budget of 0 or more and a group size of at least 1."
        else:
            budget_results = self.get_queryset().filter(
                status=Trip.PLANNED,
                budget_min_usd__lte=max_budget,  # the cheapest plausible cost fits the budget
                seats_open__gte=group_size,  # enough free seats for the group
            )

        context = self.get_context_data(
            budget_results=budget_results,
            budget_error=budget_error,
            budget_searched=True,
            posted_budget=raw_budget,
            posted_group=raw_group,
        )
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET

        q = params.get("q", "").strip()
        country = params.get("country", "").strip()
        tab = params.get("tab", "").strip()  # "planned" or "completed"
        try:
            starts_after = parse_date(params.get("starts_after", "").strip())
        except ValueError:
            starts_after = None

        searching = bool(q or country or tab or starts_after)
        search_results = None
        if searching:
            search_results = self.get_queryset()
            if q:
                search_results = search_results.filter(
                    Q(title__icontains=q)
                    | Q(stops__destination__name__icontains=q)
                    | Q(stops__destination__country__icontains=q)
                )
            if country:
                search_results = search_results.filter(stops__destination__country=country)
            if tab in (Trip.PLANNED, Trip.COMPLETED):
                search_results = search_results.filter(status=tab)
            if starts_after:
                search_results = search_results.filter(start_date__gte=starts_after)
            search_results = search_results.distinct()  # joins can repeat a trip

        ctx.update(
            q=q,
            country=country,
            tab=tab,
            starts_after=params.get("starts_after", ""),
            search_results=search_results,
            searching=searching,
            countries=Destination.objects.order_by("country").values_list("country", flat=True).distinct(),
        )

        # Totals and grouped summaries shown under the results.
        ctx["total_trips"] = Trip.objects.count()
        ctx["public_trips"] = Trip.objects.filter(visibility=Trip.PUBLIC).count()
        ctx["total_requests"] = JoinRequest.objects.count()
        ctx["trips_per_destination"] = destination_popularity()
        ctx["requests_per_status"] = (
            JoinRequest.objects.values("status").annotate(n=Count("request_id")).order_by("status")
        )
        return ctx


# ---------------------------------------------------------------------------
# Chart image
# ---------------------------------------------------------------------------
def trips_by_destination_chart(request):
    """
    GET /charts/trips-by-destination.png — public and private trips per destination as a PNG.

    The image is drawn into an in-memory buffer, so nothing is written to disk, and the figure is
    closed afterwards to release its memory.
    """
    rows = list(destination_popularity())
    labels = [d.name for d in rows]
    public = [d.n_public for d in rows]
    private = [d.n_trips - d.n_public for d in rows]

    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=130)
    if rows:
        ax.bar(labels, public, color="#18a0f0", label="Public (community)")
        ax.bar(labels, private, bottom=public, color="#ffb62d", label="Private")
        ax.legend(frameon=False, fontsize=8)
    else:
        ax.text(0.5, 0.5, "No trips yet", ha="center", va="center", transform=ax.transAxes)

    ax.set_title("Trips per destination", fontsize=11, color="#0b2f6b", loc="left")
    ax.set_xlabel("Destination", fontsize=9)
    ax.set_ylabel("Number of trips", fontsize=9)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.tick_params(axis="x", rotation=40, labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return HttpResponse(buf.getvalue(), content_type="image/png")


# ---------------------------------------------------------------------------
# JSON API (public, read-only, public trips only)
# ---------------------------------------------------------------------------
def api_ping_jsonresponse(request):
    """Health check answered with JsonResponse (Content-Type: application/json)."""
    return JsonResponse({"ok": True})


def api_ping_httpresponse_manual_json(request):
    """Health check built by hand: json.dumps plus an explicit application/json header."""
    return HttpResponse(json.dumps({"ok": True}), content_type="application/json")


def api_ping_httpresponse_default(request):
    """Health check with Django's default HttpResponse type (text/html; charset=utf-8)."""
    return HttpResponse('{"ok": true}')


def api_ping_httpresponse_text(request):
    """Health check as plain text (text/plain)."""
    return HttpResponse("ok", content_type="text/plain")


def _trip_to_dict(trip):
    """The one place that decides which trip fields are safe to publish."""
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
        "seats_open": trip.seats_open,
        "owner": trip.owner.display_name,
        "owner_verified": trip.owner.is_domain_verified,
        "url": trip.get_absolute_url(),
    }


def api_trips(request):
    """
    GET /api/trips/ — public trips as JSON.

      ?q=lisbon         title, destination or country contains
      ?country=Italy    trip visits a city in this country
      ?status=planned   planned | completed
      ?max_budget=1500  trips whose minimum budget is at most this
      ?min_seats=2      trips with at least this many open seats
    """
    params = request.GET
    qs = (
        Trip.objects.filter(visibility=Trip.PUBLIC)  # never publish private trips
        .select_related("owner")
        .prefetch_related("stops__destination")
    )

    q = params.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(stops__destination__name__icontains=q)
            | Q(stops__destination__country__icontains=q)
        )
    country = params.get("country", "").strip()
    if country:
        qs = qs.filter(stops__destination__country__iexact=country)
    status = params.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)
    try:
        if params.get("max_budget"):
            qs = qs.filter(budget_min_usd__lte=Decimal(params["max_budget"]))
        if params.get("min_seats"):
            qs = qs.filter(seats_open__gte=int(params["min_seats"]))
    except (InvalidOperation, ValueError):
        return JsonResponse({"error": "max_budget must be a number and min_seats a whole number."}, status=400)

    data = [_trip_to_dict(t) for t in qs.distinct()]
    return JsonResponse({"count": len(data), "results": data})


class DestinationsAPI(View):
    """GET /api/destinations/?country=Italy&q=rom — destinations with their public trip counts."""

    def get(self, request):
        qs = Destination.objects.annotate(
            public_trips=Count("stops__trip", filter=Q(stops__trip__visibility=Trip.PUBLIC), distinct=True)
        )
        country = request.GET.get("country", "").strip()
        if country:
            qs = qs.filter(country__iexact=country)
        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)

        data = [
            {
                "name": d.name,
                "country": d.country,
                "iata_code": d.iata_code,
                "avg_daily_cost_usd": float(d.avg_daily_cost_usd),
                "public_trips": d.public_trips,
            }
            for d in qs.order_by("-public_trips", "name")
        ]
        return JsonResponse({"count": len(data), "results": data})


def api_popular_destinations(request):
    """GET /api/destinations/popular/ — parallel label and count arrays."""
    rows = destination_popularity()
    return JsonResponse({
        "labels": [d.name for d in rows],
        "public_trips": [d.n_public for d in rows],
    })
