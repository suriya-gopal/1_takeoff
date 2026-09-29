"""
Views for the TakeOff trips app: pages, forms, search, chart and JSON API.
"""

from django.http import HttpResponse
from django.shortcuts import redirect, render

from .forms import JoinRequestForm, TripForm
from .models import Destination, JoinRequest, Trip


def home(request):
    """Landing page: community-posted trips plus the most popular destinations."""
    trips = (
        Trip.objects.filter(visibility=Trip.PUBLIC)
        .select_related("owner")
        .prefetch_related("stops__destination")[:6]
    )
    # Destinations ranked by how many trips visit them.
    popular = destination_popularity()[:4]
    return render(request, "trips/home.html", {"trips": trips, "popular": popular})


# ---------------------------------------------------------------------------
# Trip pages
# ---------------------------------------------------------------------------
from django.template import loader
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import ListView


def trip_manual_view(request):
    """Quick feed of public trips. Loads the template by hand and wraps it in an HttpResponse."""
    trips = Trip.objects.filter(visibility=Trip.PUBLIC)
    template = loader.get_template('trips/trip_list_manual.html')
    context = {'trips': trips}
    return HttpResponse(template.render(context, request))


def trip_list_view(request):
    """List of all trips, using the render() shortcut."""
    trips = (
        Trip.objects
        .select_related('owner')
        .prefetch_related('stops__destination')
    )
    return render(request, 'trips/trip_list.html', {'trips': trips})


class TripDetailView(View):
    """
    One trip's page, built on the base View class.

    get()  shows the trip, its route, its join requests and an empty "Request to join" form.
    post() validates that form, saves a JoinRequest row, then redirects back to the trip.
    """

    def _render(self, request, trip, form, status=200):
        return render(
            request,
            'trips/trip_detail.html',
            {
                'trip': trip,
                'stops': trip.stops.all(),
                'join_requests': trip.join_requests.all(),
                'form': form,
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
            # Post/Redirect/Get: redirecting means a browser refresh cannot re-submit the form.
            return redirect(trip.get_absolute_url())
        return self._render(request, trip, form, status=400)


class TripListView(ListView):
    """Community trips (public only), using a generic ListView. Shares trip_list.html with trip_list_view."""
    model = Trip
    template_name = 'trips/trip_list.html'
    context_object_name = 'trips'
    queryset = Trip.objects.filter(visibility=Trip.PUBLIC)



# ===========================================================================
# Search, forms, chart and API
# ===========================================================================

import json
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils.dateparse import parse_date
from django.views.generic import CreateView

import matplotlib
matplotlib.use("Agg")            # draw to memory only — no GUI window on a server
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


# ---------------------------------------------------------------------------
# Shared query used by the home page, the search page's summary table, the chart
# and the API, so the "popular destinations" numbers can never disagree.
# ---------------------------------------------------------------------------
def destination_popularity():
    """Destinations ranked by how many trips visit them (grouped COUNT)."""
    return (
        Destination.objects
        # Destination <- TripStop <- Trip: 'stops__trip' spans two relationships.
        # distinct=True because a join can repeat a trip; we count each trip once.
        .annotate(
            n_trips=Count("stops__trip", distinct=True),
            n_public=Count("stops__trip", filter=Q(stops__trip__visibility=Trip.PUBLIC), distinct=True),
        )
        .filter(n_trips__gt=0)          # HAVING COUNT(...) > 0 : hide never-visited cities
        .order_by("-n_trips", "name")
    )


# ---------------------------------------------------------------------------
# Search page: filter search, budget search and summaries
# ---------------------------------------------------------------------------
class TripSearchView(ListView):
    """
    Search page: a ListView that answers two kinds of request.

      GET  /trips/search/?q=lisbon&tab=planned   -> filter by destination, country, date, status
      POST /trips/search/                         -> find trips within a budget and group size

    The filter uses GET because the same link always gives the same results, so it can be
    bookmarked or shared. The budget search uses POST because a personal budget should
    not appear in the URL, browser history or server logs (the trade-off: the result
    page has no shareable link).
    """
    model = Trip
    template_name = "trips/trip_search.html"
    context_object_name = "trips"

    def get_queryset(self):
        # FULL LIST. Only public trips: a page reachable by a plain link must
        # never expose private trips.
        return (
            Trip.objects.filter(visibility=Trip.PUBLIC)
            .select_related("owner")
            .prefetch_related("stops__destination")
        )

    # ---- Budget search (form submission) ----
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
            budget_results = (
                self.get_queryset()
                .filter(status=Trip.PLANNED,
                        budget_min_usd__lte=max_budget,     # cheapest plausible cost fits the budget
                        seats_open__gte=group_size)         # enough free seats for the group
            )

        context = self.get_context_data(
            budget_results=budget_results,
            budget_error=budget_error,
            budget_searched=True,
            posted_budget=raw_budget,
            posted_group=raw_group,
        )
        return self.render_to_response(context)

    # ---- Filter search (URL query) and summaries ----
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET

        q = params.get("q", "").strip()
        country = params.get("country", "").strip()
        tab = params.get("tab", "").strip()               # 'planned' | 'completed'
        starts_after = None
        try:
            starts_after = parse_date(params.get("starts_after", "").strip())
        except ValueError:
            starts_after = None

        searching = bool(q or country or tab or starts_after)
        search_results = None
        if searching:
            search_results = self.get_queryset()
            if q:
                # Relationship spanning with '__': Trip -> TripStop -> Destination -> name/country
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
            search_results = search_results.distinct()   # joins can repeat a trip

        ctx.update(
            q=q, country=country, tab=tab,
            starts_after=params.get("starts_after", ""),
            search_results=search_results,
            searching=searching,
            countries=Destination.objects.order_by("country").values_list("country", flat=True).distinct(),
        )

        # =========================
        # AGGREGATIONS
        # =========================
        # A) Totals: one number each (COUNT)
        ctx["total_trips"] = Trip.objects.count()
        ctx["public_trips"] = Trip.objects.filter(visibility=Trip.PUBLIC).count()
        ctx["total_requests"] = JoinRequest.objects.count()

        # B) Grouped summary: trips per destination (annotate + Count)
        ctx["trips_per_destination"] = destination_popularity()

        # C) Grouped summary: join requests per status (values -> annotate -> Count)
        ctx["requests_per_status"] = (
            JoinRequest.objects.values("status").annotate(n=Count("request_id")).order_by("status")
        )
        return ctx


# ---------------------------------------------------------------------------
# Plan a trip form
# ---------------------------------------------------------------------------
class TripCreateView(CreateView):
    """
    "Plan your trip" page. On a valid submission the trip and its stops are saved and
    the user is redirected to the new trip. success_url is left out on purpose:
    CreateView then uses the trip's get_absolute_url().
    """
    model = Trip
    form_class = TripForm
    template_name = "trips/trip_form.html"


# ---------------------------------------------------------------------------
# Chart image
# ---------------------------------------------------------------------------
def trips_by_destination_chart(request):
    """
    PNG image endpoint: /charts/trips-by-destination.png

    Data comes from the ORM (destination_popularity), not hard-coded numbers.

    Memory awareness: the picture is built and saved into a BytesIO — a file
    that lives in RAM — so nothing is written to disk. Costs to know about:
      * the Figure holds the pixels in memory while drawing (a few MB at this
        size), so plt.close(fig) is called or every request would leak a figure;
      * the finished PNG is only tens of KB, but it is held in RAM once in
        `buf` and once more by getvalue(), then released after the response;
      * pyplot keeps global state, which is fine for the dev server but is why
        production apps often use matplotlib.figure.Figure directly.
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
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))     # no "1.5 trips"
    ax.tick_params(axis="x", rotation=40, labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)                       # free the figure's memory
    buf.seek(0)
    return HttpResponse(buf.getvalue(), content_type="image/png")


def insights(request):
    """Page that shows the chart with a heading, caption, alt text and the numbers behind it."""
    return render(request, "trips/insights.html", {"rows": destination_popularity()})


# ---------------------------------------------------------------------------
# JSON API (public, read-only, public trips only)
# ---------------------------------------------------------------------------
# --- HttpResponse vs JsonResponse: same data, different Content-Type labels ---
# The MIME type is the Content-Type header that tells the client how to read the body.
def api_ping_jsonresponse(request):
    """JsonResponse: serialises the dict AND sets Content-Type: application/json."""
    return JsonResponse({"ok": True})


def api_ping_httpresponse_manual_json(request):
    """HttpResponse doing JsonResponse's job by hand: json.dumps + set the header ourselves."""
    return HttpResponse(json.dumps({"ok": True}), content_type="application/json")


def api_ping_httpresponse_default(request):
    """HttpResponse with no content_type: Django labels it text/html; charset=utf-8."""
    return HttpResponse('{"ok": true}')


def api_ping_httpresponse_text(request):
    """HttpResponse labelled text/plain — a client will NOT treat this as JSON."""
    return HttpResponse("ok", content_type="text/plain")


def _trip_to_dict(trip):
    """One place that decides which Trip fields are safe to publish."""
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
    FBV API:  GET /api/trips/
      ?q=lisbon         title / destination / country contains
      ?country=Italy    trip visits a city in this country
      ?status=planned   planned | completed
      ?max_budget=1500  trips whose minimum budget is <= this
      ?min_seats=2      trips with at least this many open seats
    """
    params = request.GET
    qs = (
        Trip.objects.filter(visibility=Trip.PUBLIC)       # never publish private trips
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
    """
    CBV API:  GET /api/destinations/?country=Italy&q=rom
    Destinations with how many PUBLIC trips visit each one.
    """

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
    """GET /api/destinations/popular/ — labels and counts arrays, handy for charts."""
    rows = destination_popularity()
    return JsonResponse({
        "labels": [d.name for d in rows],
        "public_trips": [d.n_public for d in rows],
    })

