"""Pages for the AI helpers. Only the trip's owner can use them."""

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings

from ..models import Traveler, Trip
from ..views import visible_trips
from . import guardrails, itinerary, model, remote, suggestions, verify

SESSION_KEY = "day_draft_{}"
SLOT_LABELS = {"morning": "Morning", "afternoon": "Afternoon", "evening": "Evening"}


class DayPlanForm(forms.Form):
    interests = forms.CharField(
        required=False, max_length=guardrails.MAX_INTERESTS_LENGTH * 2,
        label="What are you into?",
        widget=forms.TextInput(attrs={"placeholder": "e.g. food, architecture, easy hikes"}),
    )
    with_kids = forms.BooleanField(required=False, label="Traveling with kids")

    def clean_interests(self):
        try:
            return guardrails.check_interests(self.cleaned_data["interests"])
        except guardrails.InvalidRequest as exc:
            raise forms.ValidationError(str(exc))


def owned_trip(request, pk):
    """The trip, if it belongs to the signed-in member; anyone else gets a 404."""
    trip = get_object_or_404(Trip, pk=pk)
    if trip.owner != Traveler.for_user(request.user):
        raise Http404
    return trip


def days_for_display(drafts):
    """Shape drafts for the template: one block per stop, one row per day."""
    return [
        {
            "city": d.stop.destination.name,
            "days": [
                {
                    "number": d.first_day + i,
                    "slots": [(SLOT_LABELS[s], day[s], d.notes.get((i, s), "")) for s in guardrails.SLOTS],
                }
                for i, day in enumerate(d.days)
            ],
        }
        for d in drafts
    ]


@login_required
def day_plan(request, pk):
    """Ask for a day-by-day draft of the trip, review it, and save it as itinerary items."""
    trip = owned_trip(request, pk)
    key = SESSION_KEY.format(trip.pk)
    form = DayPlanForm(request.POST or None) if request.POST.get("action") == "draft" else DayPlanForm()
    error, status = "", 200

    if request.method == "POST" and request.POST.get("action") == "save":
        drafts = itinerary.from_session(trip, request.session.get(key))
        if drafts:
            itinerary.save_drafts(drafts)
            request.session.pop(key, None)
            return redirect(trip.get_absolute_url() + "#days")
        error, status = "That draft has expired. Please create a new one.", 400

    elif request.method == "POST" and form.is_valid():
        if not guardrails.allow_request(request.user.pk, settings.AI_DRAFTS_PER_HOUR):
            error, status = "You have reached the hourly limit for drafts. Please try again later.", 429
        else:
            try:
                drafts = itinerary.draft_trip(
                    trip, form.cleaned_data["interests"], form.cleaned_data["with_kids"],
                )
                drafts, place_check = refine_drafts(request, drafts)
                request.session[key] = itinerary.to_session(drafts)
                request.session[key + "_check"] = place_check
            except model.ModelUnavailable as exc:
                error, status = str(exc), 503
            except itinerary.DraftFailed:
                error, status = "The assistant could not put a plan together this time. Please try again.", 502

    elif request.method == "POST":
        status = 400

    drafts = itinerary.from_session(trip, request.session.get(key))
    return render(
        request,
        "trips/day_plan.html",
        {
            "trip": trip, "form": form, "plan": days_for_display(drafts), "error": error,
            "place_check": request.session.get(key + "_check", "") if drafts else "",
        },
        status=status,
    )


def refine_drafts(request, drafts):
    """
    Have the hosted assistant check the places in a fresh draft, when it is set up.

    Returns (drafts, outcome) where outcome is "checked", "unchecked" (the check could not run) or "" (no
    hosted assistant on this server).
    """
    if not remote.configured():
        return drafts, ""
    if not guardrails.allow_request(request.user.pk, settings.AI_API_REQUESTS_PER_HOUR, scope="api"):
        return drafts, "unchecked"
    return drafts, "checked" if verify.verify_drafts(drafts) else "unchecked"


SUGGESTION_KEY = "place_suggestions_{}"


class SuggestionForm(forms.Form):
    stop = forms.IntegerField(widget=forms.HiddenInput)
    category = forms.ChoiceField(choices=list(suggestions.CATEGORIES.items()))
    interests = forms.CharField(required=False, max_length=guardrails.MAX_INTERESTS_LENGTH * 2, label="What are you into?")

    def clean_interests(self):
        try:
            return guardrails.check_interests(self.cleaned_data["interests"])
        except guardrails.InvalidRequest as exc:
            raise forms.ValidationError(str(exc))


@login_required
def place_suggestions(request, pk):
    """Browse suggested places and things to do for one city of the trip and add the ones you like."""
    trip = owned_trip(request, pk)
    stops = list(trip.stops.select_related("destination"))
    key = SUGGESTION_KEY.format(trip.pk)
    saved = request.session.get(key) or {}
    stop = next((s for s in stops if s.pk == saved.get("stop_id")), stops[0] if stops else None)
    category = saved.get("category") if saved.get("category") in suggestions.CATEGORIES else "activity"
    error, notice, status = "", "", 200

    if not remote.configured():
        error, status = "Place suggestions are not set up on this server.", 503
    elif request.method == "POST" and request.POST.get("action") == "add":
        places = saved.get("places") or []
        index = request.POST.get("index", "")
        if stop is None or not index.isdigit() or int(index) >= len(places):
            error, status = "That suggestion is no longer available.", 400
        else:
            _, created = suggestions.add_place(stop, category, places[int(index)])
            notice = "Added to your itinerary." if created else "Already in your itinerary."
    elif request.method == "POST":
        form = SuggestionForm(request.POST)
        chosen = next((s for s in stops if form.is_valid() and s.pk == form.cleaned_data["stop"]), None)
        if not form.is_valid() or chosen is None:
            error, status = "; ".join(e for errs in form.errors.values() for e in errs) or "Choose a city.", 400
        elif not guardrails.allow_request(request.user.pk, settings.AI_API_REQUESTS_PER_HOUR, scope="api"):
            error, status = "You have reached the hourly limit. Please try again later.", 429
        else:
            stop, category = chosen, form.cleaned_data["category"]
            try:
                places = suggestions.suggest_places(stop, category, form.cleaned_data["interests"], trip)
                request.session[key] = {"stop_id": stop.pk, "category": category, "places": places}
                saved = request.session[key]
            except remote.ApiFailed:
                error, status = "The assistant could not come up with suggestions this time. Please try again.", 502

    places = saved.get("places") or []
    shown = [
        (i, p) for i, p in enumerate(places)
        if (request.GET.get("free") != "1" or p["free"]) and (request.GET.get("gems") != "1" or p["hidden_gem"])
    ] if stop is not None and saved.get("stop_id") == stop.pk else []
    return render(request, "trips/place_suggestions.html", {
        "trip": trip, "stops": stops, "stop": stop, "category": category, "categories": suggestions.CATEGORIES,
        "shown": shown, "error": error, "notice": notice, "form": SuggestionForm(),
        "only_free": request.GET.get("free") == "1", "only_gems": request.GET.get("gems") == "1",
    }, status=status)


@login_required
def packing_list(request, pk):
    """A suggested packing checklist for a trip the member can see."""
    trip = get_object_or_404(visible_trips(request.user), pk=pk)
    items, error, status = [], "", 200
    if not remote.configured():
        error, status = "The packing list is not set up on this server.", 503
    elif not guardrails.allow_request(request.user.pk, settings.AI_API_REQUESTS_PER_HOUR, scope="api"):
        error, status = "You have reached the hourly limit. Please try again later.", 429
    else:
        try:
            items = suggestions.packing_list(trip)
        except remote.ApiFailed:
            error, status = "The assistant could not put a list together this time. Please try again.", 502
    return render(request, "trips/packing_list.html", {"trip": trip, "items": items, "error": error}, status=status)
