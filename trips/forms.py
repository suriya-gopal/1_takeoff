"""
Forms for user input.

* TripForm        -> the "Plan your trip" form (dates, budget range, group size,
                     "Looking for travel companions?" checkbox, ordered stops).
* JoinRequestForm -> the "Request to join" form on a trip page.

Both are ModelForms: Django builds the fields from the model, validates them, and
form.save() writes the row. Extra checks in clean() turn database constraint
failures into friendly form errors instead of a 500 error page.
"""

from django import forms
from django.db import transaction

from .models import Destination, JoinRequest, Trip, TripStop


class TripForm(forms.ModelForm):
    # --- Not model fields: they only exist on the form -------------------------
    # Ticking this checkbox posts the trip publicly (visibility) so it appears in
    # the community trips.
    looking_for_companions = forms.BooleanField(
        required=False,
        label="Looking for travel companions?",
        help_text="Tick to post this trip publicly so others can request to join.",
    )

    # Three ordered pickers keep the route order (stop 1, 2, 3); each one becomes
    # a TripStop row.
    stop_1 = forms.ModelChoiceField(Destination.objects.all(), label="Stop 1")
    stop_2 = forms.ModelChoiceField(Destination.objects.all(), required=False, label="Stop 2 (optional)")
    stop_3 = forms.ModelChoiceField(Destination.objects.all(), required=False, label="Stop 3 (optional)")

    class Meta:
        model = Trip
        fields = [
            "owner", "title", "start_date", "end_date",
            "budget_min_usd", "budget_max_usd", "group_size", "seats_open",
        ]
        labels = {
            "budget_min_usd": "Budget minimum (USD)",
            "budget_max_usd": "Budget maximum (USD)",
            "seats_open": "Seats open for companions",
        }
        widgets = {
            # type="date" gives the browser's date picker instead of a text box.
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "owner": "There is no login yet, so pick who is planning this trip.",
        }

    def clean_title(self):
        """Strip stray spaces around the title."""
        return self.cleaned_data["title"].strip()

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        low, high = cleaned.get("budget_min_usd"), cleaned.get("budget_max_usd")

        if start and end and end < start:
            self.add_error("end_date", "The trip cannot end before it starts.")
        if low is not None and high is not None and high < low:
            self.add_error("budget_max_usd", "Maximum budget must be at least the minimum.")

        # A city may appear only once per trip (DB constraint uniq_destination_per_trip).
        stops = [cleaned.get(k) for k in ("stop_1", "stop_2", "stop_3") if cleaned.get(k)]
        if len(stops) != len(set(stops)):
            self.add_error("stop_2", "Each city can appear only once in a route.")

        if cleaned.get("looking_for_companions"):
            if not cleaned.get("seats_open"):
                self.add_error("seats_open", "Open at least 1 seat if you are looking for companions.")
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        """Save the trip AND its ordered stops together, or neither (atomic)."""
        trip = super().save(commit=False)
        looking = self.cleaned_data["looking_for_companions"]
        trip.visibility = Trip.PUBLIC if looking else Trip.PRIVATE
        trip.status = Trip.PLANNED if looking else Trip.DRAFT
        if not looking:
            trip.seats_open = 0

        if commit:
            trip.save()
            stops = [self.cleaned_data[k] for k in ("stop_1", "stop_2", "stop_3") if self.cleaned_data.get(k)]
            # Split the trip's nights across the cities; every stop gets at least 1.
            per_stop, extra = divmod(trip.duration_nights, len(stops))
            for i, city in enumerate(stops):
                nights = max(1, per_stop + (1 if i < extra else 0))
                TripStop.objects.create(trip=trip, destination=city, position=i + 1, nights=nights)
        return trip


class JoinRequestForm(forms.ModelForm):
    """'Request to join' form. The trip comes from the URL, not the form."""

    class Meta:
        model = JoinRequest
        fields = ["requester", "message"]
        labels = {"requester": "Requesting as"}
        help_texts = {"requester": "There is no login yet, so pick who is asking."}
        widgets = {"message": forms.Textarea(attrs={"rows": 3, "placeholder": "Say hi — no personal details until the owner accepts."})}

    def __init__(self, *args, trip=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.trip = trip

    def clean(self):
        cleaned = super().clean()
        requester = cleaned.get("requester")
        if self.trip is not None:
            if self.trip.visibility != Trip.PUBLIC or self.trip.status != Trip.PLANNED:
                raise forms.ValidationError("This trip is not open to join requests.")
            if self.trip.seats_open < 1:
                raise forms.ValidationError("No seats left on this trip.")
            if requester and requester == self.trip.owner:
                self.add_error("requester", "You cannot request to join your own trip.")
        return cleaned

    def save(self, commit=True):
        # Model rule: one request per person per trip, "re-asking edits the existing row".
        req, _ = JoinRequest.objects.update_or_create(
            trip=self.trip,
            requester=self.cleaned_data["requester"],
            defaults={"message": self.cleaned_data["message"], "status": JoinRequest.PENDING},
        )
        return req
