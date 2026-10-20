"""
Prompt for the day-by-day draft.

The model is given strict output rules plus three worked examples (one of them a trip with kids), then
the real request. Worked examples keep a small model on the JSON format and make it notice constraints
such as travelling with children.
"""

import json

from django.conf import settings

SYSTEM_PROMPT = (
    "You are {site}'s trip planner. Create a day-by-day itinerary. "
    "Respond ONLY with valid JSON in this exact format, with no extra text:\n"
    '{{"destination": "<city>", "days": [{{"day": 1, "morning": "<activity>", '
    '"afternoon": "<activity>", "evening": "<activity>"}}]}}'
)

EXAMPLES = [
    ({"destination": "Denver", "days": 2, "interests": "outdoors; traveling with kids", "budget": "moderate"},
     {"destination": "Denver", "days": [
         {"day": 1, "morning": "Short, kid-friendly Trading Post Trail at Red Rocks Park",
          "afternoon": "Denver Museum of Nature & Science, which has hands-on exhibits for children",
          "evening": "Early family dinner and ice cream at Larimer Square"},
         {"day": 2, "morning": "Denver Zoo, easy walking paths for little legs",
          "afternoon": "Picnic and playground time at City Park",
          "evening": "Dinner at the Downtown Aquarium, a hit with kids"}]}),
    ({"destination": "San Diego", "days": 1, "interests": "beaches and tacos", "budget": "low"},
     {"destination": "San Diego", "days": [
         {"day": 1, "morning": "Free walk along La Jolla Cove to see sea lions",
          "afternoon": "Cheap fish tacos in Old Town, then the free Old Town State Historic Park",
          "evening": "Sunset at Ocean Beach Pier"}]}),
    ({"destination": "Paris", "days": 2, "interests": "art and cafes", "budget": "high"},
     {"destination": "Paris", "days": [
         {"day": 1, "morning": "Louvre with a reserved private guided tour",
          "afternoon": "Lunch at a classic Saint-Germain cafe, then the Musee d'Orsay",
          "evening": "Dinner cruise on the Seine"},
         {"day": 2, "morning": "Monet's Water Lilies at the Musee de l'Orangerie",
          "afternoon": "Pastries and boutique shopping in Le Marais",
          "evening": "Tasting menu at a well-reviewed bistro"}]}),
]


def user_prompt(city, days, interests, budget):
    return f"Plan a {days}-day trip to {city}. Interests: {interests}. Budget: {budget}."


def build_messages(city, days, interests, budget):
    """System rules, the worked examples as earlier turns, then the real request."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(site=settings.SITE_NAME)}]
    for trip, answer in EXAMPLES:
        messages.append({"role": "user", "content": user_prompt(trip["destination"], trip["days"], trip["interests"], trip["budget"])})
        messages.append({"role": "assistant", "content": json.dumps(answer)})
    messages.append({"role": "user", "content": user_prompt(city, days, interests, budget)})
    return messages
