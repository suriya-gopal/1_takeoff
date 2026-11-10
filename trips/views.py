"""Page views, search, the plan-a-trip form, the chart image and the JSON API for the trips app."""

import json
from decimal import Decimal, InvalidOperation
from io import BytesIO

import matplotlib
matplotlib.use("Agg")  # draw to memory only; a server has no display
import matplotlib.pyplot as plt
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView
from matplotlib.ticker import MaxNLocator

from .access import api_login_required
from .forms import JoinRequestForm, TripForm
from .models import Destination, ItineraryItem, JoinRequest, Traveler, Trip


def visible_trips(user):
    """
    Trips a signed-in user may open: every public trip, their own private ones, and private trips
    they co-own because the owner accepted their request to join.

    Private trips belong to their owner, so another traveler gets a 404 for them, the same answer
    as for a trip that does not exist.
    """
    return Trip.objects.filter(
        Q(visibility=Trip.PUBLIC)
        | Q(owner__user=user)
        # Accepted companions are co-owners and can open the trip even if it is private.
        | Q(join_requests__requester__user=user, join_requests__status=JoinRequest.ACCEPTED)
    ).distinct()


def destination_popularity(user=None):
    """
    Destinations ranked by how many trips visit them.

    Shared by the home page, the search summaries, the insights charts and the API so
    their numbers always agree. Counts follow the same rule as the trip lists:
    n_public counts public trips; n_trips counts the trips `user` can open (public trips plus
    their own private ones), which is n_public again when no one is signed in. Other members'
    private trips are never counted, so no page reveals that they exist.
    """
    can_see = Q(stops__trip__visibility=Trip.PUBLIC)
    if user is not None and user.is_authenticated:
        can_see |= Q(stops__trip__owner__user=user)
        can_see |= Q(stops__trip__join_requests__requester__user=user,
                     stops__trip__join_requests__status=JoinRequest.ACCEPTED)
    return (
        Destination.objects
        # Destination <- TripStop <- Trip: 'stops__trip' spans two relationships. distinct=True
        # because the join can repeat a trip and each trip should be counted once.
        .annotate(
            n_trips=Count("stops__trip", filter=can_see, distinct=True),
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
    return render(request, "trips/home.html", {"trips": trips, "popular": destination_popularity(request.user)[:4]})


def trip_manual_view(request):
    """Quick feed of public trips, rendered through the template loader."""
    template = loader.get_template("trips/trip_list_manual.html")
    trips = Trip.objects.filter(visibility=Trip.PUBLIC)
    return HttpResponse(template.render({"trips": trips}, request))


@login_required
def trip_list_view(request):
    """Every public trip plus the signed-in traveler's private ones, soonest departure first."""
    trips = visible_trips(request.user).select_related("owner").prefetch_related("stops__destination")
    return render(request, "trips/trip_list.html", {"trips": trips})


class TripListView(ListView):
    """Community trips (public only). Shares its template with trip_list_view."""

    model = Trip
    template_name = "trips/trip_list.html"
    context_object_name = "trips"
    queryset = Trip.objects.filter(visibility=Trip.PUBLIC)


@login_required
def my_profile(request):
    """The signed-in member's own page: profile details, their trips and their join requests both ways."""
    me = Traveler.for_user(request.user)
    trips = me.trips.select_related("owner").prefetch_related("stops__destination")
    co_owned = (
        Trip.objects.filter(join_requests__requester=me, join_requests__status=JoinRequest.ACCEPTED)
        .select_related("owner").prefetch_related("stops__destination")
    )
    sent = JoinRequest.objects.filter(requester=me).select_related("trip").order_by("-requested_at")
    received = (
        JoinRequest.objects.filter(trip__owner=me).select_related("trip", "requester").order_by("-requested_at")
    )
    return render(request, "trips/traveler_profile.html", {
        "traveler": me, "trips": trips, "co_owned": co_owned, "sent": sent, "received": received,
        "pending_count": sum(1 for r in received if r.status == JoinRequest.PENDING),
    })


@login_required
@require_POST
def decide_join_request(request, pk, request_id):
    """
    The trip owner approves or rejects one pending request.

    Approving takes one open seat and makes the requester a co-owner (they can open the trip and use
    its planning tools). The trip row is locked while seats are counted so two approvals at the same
    moment cannot both take the last seat.
    """
    me = Traveler.for_user(request.user)
    trip = get_object_or_404(Trip, pk=pk, owner=me)         # only the owner decides; anyone else gets 404
    decision = request.POST.get("decision")
    if decision not in ("approve", "reject"):
        return HttpResponseBadRequest("Unknown decision.")
    with transaction.atomic():
        trip = Trip.objects.select_for_update().get(pk=trip.pk)
        join = get_object_or_404(JoinRequest.objects.select_related("requester"), pk=request_id, trip=trip)
        name = join.requester.display_name
        if join.status != JoinRequest.PENDING:
            messages.info(request, f"{name}'s request was already {join.get_status_display().lower()}.")
        elif decision == "reject":
            join.status = JoinRequest.DECLINED
            join.save(update_fields=["status"])
            messages.success(request, f"You rejected {name}'s request.")
        elif trip.seats_open < 1:
            messages.error(request, f"No seats left on this trip, so {name} cannot be approved. Reject the "
                                    "request or open another seat first.")
        else:
            join.status = JoinRequest.ACCEPTED
            join.save(update_fields=["status"])
            trip.seats_open -= 1
            trip.save(update_fields=["seats_open"])
            messages.success(request, f"{name} is now a co-owner of this trip. "
                                      f"{trip.seats_open} seat{'s' if trip.seats_open != 1 else ''} left.")
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = trip.get_absolute_url()
    return redirect(target)


def itinerary_by_day(trip):
    """The trip's itinerary items grouped by day, each day in time order: [(day_number, [items])]."""
    items = ItineraryItem.objects.filter(stop__trip=trip).select_related("stop__destination")
    days = {}
    for item in items.order_by("day_number", "start_time", "item_id"):
        days.setdefault(item.day_number, []).append(item)
    return sorted(days.items())


class TripDetailView(LoginRequiredMixin, View):
    """
    One trip: its route, its join requests and the "Request to join" form.

    GET shows the page with an empty form. POST validates the form, saves a join request from the
    signed-in traveler and redirects back to the trip. Requires login.
    """

    def _render(self, request, trip, form, status=200):
        me = Traveler.for_user(request.user)
        is_owner = trip.owner == me
        co_owners = list(trip.co_owners())
        is_co_owner = me in co_owners
        return render(
            request,
            "trips/trip_detail.html",
            {
                "trip": trip,
                "stops": trip.stops.all(),
                "is_owner": is_owner,
                "is_co_owner": is_co_owner,
                "can_plan": is_owner or is_co_owner,
                "co_owners": co_owners,
                "item_days": itinerary_by_day(trip),
                # Who asked to join is the owner's business only; other members just see the form.
                "join_requests": trip.join_requests.select_related("requester") if is_owner or is_co_owner else [],
                "my_request": None if is_owner else trip.join_requests.filter(requester=me).first(),
                "form": form,
            },
            status=status,
        )

    def get(self, request, pk):
        trip = get_object_or_404(visible_trips(request.user), pk=pk)
        return self._render(request, trip, JoinRequestForm(trip=trip))

    def post(self, request, pk):
        trip = get_object_or_404(visible_trips(request.user), pk=pk)
        form = JoinRequestForm(request.POST, trip=trip, requester=Traveler.for_user(request.user))
        if form.is_valid():
            form.save()
            return redirect(trip.get_absolute_url())  # redirect so a refresh cannot re-submit the form
        return self._render(request, trip, form, status=400)


class TripCreateView(LoginRequiredMixin, CreateView):
    """
    "Plan your trip" form. A valid submission saves the trip, owned by the signed-in traveler, with
    its stops and redirects to the new trip's page (CreateView falls back to Trip.get_absolute_url).
    """

    model = Trip
    form_class = TripForm
    template_name = "trips/trip_form.html"

    def form_valid(self, form):
        form.instance.owner = Traveler.for_user(self.request.user)
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
class TripSearchView(LoginRequiredMixin, ListView):
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

        # Totals and grouped summaries shown under the results. They count only what this member can
        # open (the same trips as the "All trips" page), never other members' private trips.
        user = self.request.user
        visible = visible_trips(user)
        requests = JoinRequest.objects.filter(trip__in=visible)
        ctx["total_trips"] = visible.count()
        ctx["public_trips"] = Trip.objects.filter(visibility=Trip.PUBLIC).count()
        ctx["total_requests"] = requests.count()
        ctx["trips_per_destination"] = destination_popularity(user)
        ctx["requests_per_status"] = (
            requests.values("status").annotate(n=Count("request_id")).order_by("status")
        )
        return ctx


# ---------------------------------------------------------------------------
# Chart image
# ---------------------------------------------------------------------------
@login_required
def trips_by_destination_chart(request):
    """
    GET /charts/trips-by-destination.png — public trips and your own private trips per destination as a PNG.

    The image is drawn into an in-memory buffer, so nothing is written to disk, and the figure is
    closed afterwards to release its memory.
    """
    rows = list(destination_popularity(request.user))
    labels = [d.name for d in rows]
    public = [d.n_public for d in rows]
    private = [d.n_trips - d.n_public for d in rows]

    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=130)
    if rows:
        ax.bar(labels, public, color="#1f3a68", label="Public (community)")
        ax.bar(labels, private, bottom=public, color="#9fb6d3", label="Your private trips")
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
# JSON API (read-only, public trips only, sign-in required)
# ---------------------------------------------------------------------------
@api_login_required
def api_ping_jsonresponse(request):
    """Health check answered with JsonResponse (Content-Type: application/json)."""
    return JsonResponse({"ok": True})


@api_login_required
def api_ping_httpresponse_manual_json(request):
    """Health check built by hand: json.dumps plus an explicit application/json header."""
    return HttpResponse(json.dumps({"ok": True}), content_type="application/json")


@api_login_required
def api_ping_httpresponse_default(request):
    """Health check with Django's default HttpResponse type (text/html; charset=utf-8)."""
    return HttpResponse('{"ok": true}')


@api_login_required
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


@api_login_required
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


@method_decorator(api_login_required, name="dispatch")
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


@api_login_required
def api_popular_destinations(request):
    """GET /api/destinations/popular/ — parallel label and count arrays."""
    rows = destination_popularity()
    return JsonResponse({
        "labels": [d.name for d in rows],
        "public_trips": [d.n_public for d in rows],
    })
