"""Pages for the AI helpers. Only the trip's owner can use them."""

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings

from ..models import Traveler, Trip
from . import guardrails, itinerary, model

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
                drafts = refine_drafts(drafts)
                request.session[key] = itinerary.to_session(drafts)
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
        {"trip": trip, "form": form, "plan": days_for_display(drafts), "error": error},
        status=status,
    )


def refine_drafts(drafts):
    """Hook for extra checks on a fresh draft (none yet)."""
    return drafts
