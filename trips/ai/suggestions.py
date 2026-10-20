"""
Place suggestions and packing lists from the hosted assistant.

Both are built only from facts the trip already holds (cities, nights, dates, budget, the member's interests
and the items already planned) and the hosted reply is validated before use.
"""

import hashlib
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from ..models import ItineraryItem
from . import guardrails, remote

CATEGORIES = {ItineraryItem.ACTIVITY: "Places and things to do", ItineraryItem.FOOD: "Food"}
PACKING_CACHE_SECONDS = 6 * 3600

PLACES_RULES = (
    "You are {site}'s travel assistant. Reply ONLY with JSON in this format: "
    '{{"places": [{{"name": "<place>", "why": "<one short sentence>", "cost_usd": <typical cost per person, 0 if free>, '
    '"hidden_gem": <true or false>, "tags": ["<word>"]}}]}}. '
    "Suggest only real, specific places or experiences that exist in the named city. If you are not sure a place "
    "exists, leave it out."
)
PACKING_RULES = (
    "You are {site}'s packing assistant. Reply ONLY with JSON in this format: "
    '{{"items": [{{"item": "<thing to pack>", "reason": "<short reason tied to the trip>"}}]}}. '
    "Give 10 to 14 practical items based on the route, the dates, the typical weather in those cities at that time of "
    "year and the planned activities."
)


def places_messages(stop, category, interests, per_night):
    city = stop.destination
    request = (
        f"City: {city.name}, {city.country}. Category: {CATEGORIES[category]}. "
        f"Traveler interests: {interests or 'general sightseeing'}. "
        f"Budget: about ${per_night} per person per night. "
        "Give 6 suggestions, at least 2 of them lesser-known spots (hidden_gem true)."
    )
    return [{"role": "system", "content": PLACES_RULES.format(site=settings.SITE_NAME)},
            {"role": "user", "content": request}]


def suggest_places(stop, category, interests, trip):
    """Six place ideas for one stop; raises remote.ApiFailed when the reply is unusable."""
    per_night = int(trip.budget_max_usd / max(trip.duration_nights, 1))
    data = remote.chat_json(places_messages(stop, category, interests, per_night))
    places = guardrails.validate_places(data)
    if not places:
        raise remote.ApiFailed("No usable suggestions in the reply.")
    return places


def stop_first_day(stop):
    """Trip day on which this stop begins."""
    earlier = stop.trip.stops.filter(position__lt=stop.position)
    return 1 + sum(max(s.nights, 1) for s in earlier)


@transaction.atomic
def add_place(stop, category, place):
    """Add a suggestion to the itinerary at the start of its stop; no time is set (scheduled later)."""
    item, created = ItineraryItem.objects.get_or_create(
        stop=stop, category=category, title=place["name"][: guardrails.MAX_ITEM_LENGTH],
        defaults={
            "day_number": stop_first_day(stop),
            "estimated_cost_usd": Decimal(str(place["cost_usd"])),
            "is_hidden_gem": place["hidden_gem"],
        },
    )
    return item, created


def packing_messages(trip):
    stops = list(trip.stops.select_related("destination"))
    route = ", ".join(f"{s.destination.name} ({s.nights} nights)" for s in stops)
    planned = [t for t in (guardrails.safe_title(i.title) for i in
                           ItineraryItem.objects.filter(stop__trip=trip).order_by("day_number", "start_time")[:30]) if t]
    request = (
        f"Trip: {trip.start_date:%B %d} to {trip.end_date:%B %d, %Y}, {trip.duration_nights} nights. "
        f"Route: {route}. Group size: {trip.group_size}. "
        f"Planned: {'; '.join(planned) if planned else 'nothing planned yet'}."
    )
    return [{"role": "system", "content": PACKING_RULES.format(site=settings.SITE_NAME)},
            {"role": "user", "content": request}]


def packing_list(trip):
    """The packing checklist for a trip. Identical requests are reused for six hours to save calls."""
    messages = packing_messages(trip)
    key = "packing-" + hashlib.sha1(messages[-1]["content"].encode()).hexdigest()
    items = cache.get(key)
    if items is None:
        items = guardrails.validate_packing(remote.chat_json(messages))
        if not items:
            raise remote.ApiFailed("No usable packing list in the reply.")
        cache.set(key, items, PACKING_CACHE_SECONDS)
    return items
