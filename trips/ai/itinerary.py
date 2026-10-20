"""
Day-by-day drafts for a trip, built stop by stop with the on-device model.

A draft is only a suggestion: nothing is stored until the member saves it, and then each morning,
afternoon and evening becomes an ordinary itinerary item they can book or change like any other.
"""

from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal

from django.db import transaction

from ..models import ItineraryItem
from . import guardrails, model, prompts

MAX_DAYS_PER_STOP = 5          # keeps one request small enough for a small model
ATTEMPTS = 3
SLOT_TIMES = {"morning": time(9, 0), "afternoon": time(14, 0), "evening": time(19, 0)}


class DraftFailed(Exception):
    """The model did not return a usable plan, even after retries."""


@dataclass
class StopDraft:
    stop: object
    first_day: int                       # trip day number of this stop's first day
    days: list = field(default_factory=list)   # [{"morning": ..., "afternoon": ..., "evening": ...}]
    notes: dict = field(default_factory=dict)  # {(day_index, slot): text}, set by optional checks


def budget_band(trip):
    """low / moderate / high, from the trip's maximum budget per person per night."""
    per_night = trip.budget_max_usd / max(trip.duration_nights, 1)
    if per_night < Decimal("100"):
        return "low"
    return "moderate" if per_night < Decimal("250") else "high"


def interests_text(interests, with_kids):
    parts = [interests] if interests else ["sights and local food"]
    if with_kids:
        parts.append("traveling with kids")
    return "; ".join(parts)


def draft_city(city, days, interests, budget, generate=None):
    """Ask the model for `days` days in one city; retry, then give up with DraftFailed."""
    generate = generate or model.generate_text
    messages = prompts.build_messages(city, days, interests, budget)
    for attempt in range(ATTEMPTS):
        reply = generate(messages, max_new_tokens=90 * days + 60, sample=attempt > 0)
        plan = guardrails.validate_days(guardrails.extract_json(reply), days)
        if plan:
            return plan
    raise DraftFailed(f"No usable plan for {city}.")


def draft_trip(trip, interests, with_kids, generate=None):
    """Draft every stop of the trip, in route order. Returns a list of StopDraft."""
    budget = budget_band(trip)
    text = interests_text(interests, with_kids)
    drafts, day_offset = [], 0
    for stop in trip.stops.select_related("destination"):
        days = min(max(stop.nights, 1), MAX_DAYS_PER_STOP)
        draft = StopDraft(stop=stop, first_day=day_offset + 1)
        draft.days = draft_city(stop.destination.name, days, text, budget, generate)
        drafts.append(draft)
        day_offset += max(stop.nights, 1)
    return drafts


@transaction.atomic
def save_drafts(drafts):
    """Store a draft as itinerary items; returns how many were new (repeat saves add nothing twice)."""
    created = 0
    for draft in drafts:
        for index, day in enumerate(draft.days):
            for slot, start in SLOT_TIMES.items():
                _, was_new = ItineraryItem.objects.get_or_create(
                    stop=draft.stop,
                    day_number=draft.first_day + index,
                    start_time=start,
                    defaults={
                        "category": ItineraryItem.ACTIVITY,
                        "title": day[slot][: guardrails.MAX_ITEM_LENGTH],
                        "estimated_cost_usd": Decimal("0"),
                    },
                )
                created += was_new
    return created


def to_session(drafts):
    """Plain data for the session (stop ids instead of model objects)."""
    return [{"stop_id": d.stop.pk, "first_day": d.first_day, "days": d.days, "notes": {f"{i}:{s}": t for (i, s), t in d.notes.items()}} for d in drafts]


def from_session(trip, data):
    """Rebuild drafts from session data, re-checking every field against the trip and the output rules."""
    stops = {s.pk: s for s in trip.stops.select_related("destination")}
    drafts = []
    for entry in data or []:
        stop = stops.get(entry.get("stop_id"))
        days = guardrails.validate_days({"days": entry.get("days")}, len(entry.get("days") or []))
        if stop is None or not days:
            continue
        notes = {}
        for key, text in (entry.get("notes") or {}).items():
            i, _, slot = key.partition(":")
            if i.isdigit() and slot in SLOT_TIMES:
                notes[(int(i), slot)] = str(text)[:200]
        drafts.append(StopDraft(stop=stop, first_day=int(entry["first_day"]), days=days, notes=notes))
    return drafts
