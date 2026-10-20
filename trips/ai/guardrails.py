"""
Checks around the model: clean what goes in, validate what comes out, limit how often it is used.
"""

import json
import re
import unicodedata

from django.core.cache import cache

MAX_INTERESTS_LENGTH = 200
MAX_ITEM_LENGTH = 120          # matches ItineraryItem.title
SLOTS = ("morning", "afternoon", "evening")

# Phrases that try to steer the model away from its job.
BLOCKED_PHRASES = (
    "ignore previous", "ignore all", "ignore the above", "disregard", "system prompt",
    "reveal", "api key", "password", "you are now", "act as",
)
_UNSAFE_CHARS = re.compile(r"[^\w\s,.;:'&/()!?+-]")   # braces, quotes, backticks, angle brackets...


class InvalidRequest(ValueError):
    """The member's text cannot be sent to the model."""


def clean_text(value, max_length=MAX_INTERESTS_LENGTH):
    """Normalise free text: strip control characters, unsafe symbols and extra spaces."""
    text = unicodedata.normalize("NFKC", value or "")
    text = "".join(ch for ch in text if ch.isprintable() or ch.isspace())
    text = _UNSAFE_CHARS.sub(" ", text)
    return " ".join(text.split())[:max_length]


def check_interests(value):
    """Return cleaned interests, or raise InvalidRequest when the text tries to redirect the model."""
    if len(value or "") > MAX_INTERESTS_LENGTH * 2:
        raise InvalidRequest("Please keep your interests short.")
    text = clean_text(value)
    lowered = text.lower()
    if any(phrase in lowered for phrase in BLOCKED_PHRASES):
        raise InvalidRequest("Please describe your interests in plain words, such as food, museums or hiking.")
    return text


def extract_json(text):
    """Pull the JSON object out of a reply that may carry extra words or a code fence; None if absent."""
    try:
        return json.loads(text[text.index("{"):text.rindex("}") + 1])
    except (ValueError, TypeError):
        return None


def validate_days(data, expected_days):
    """
    Check a reply has the shape {"days": [{"morning", "afternoon", "evening"}, ...]}.

    Returns a list of exactly `expected_days` dicts with trimmed text, or None when the reply is unusable.
    """
    days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(days, list) or len(days) < expected_days:
        return None
    result = []
    for entry in days[:expected_days]:
        if not isinstance(entry, dict):
            return None
        slots = {}
        for slot in SLOTS:
            value = entry.get(slot)
            if not isinstance(value, str) or not clean_text(value, MAX_ITEM_LENGTH):
                return None
            slots[slot] = clean_text(value, MAX_ITEM_LENGTH)
        result.append(slots)
    return result


def allow_request(user_id, limit):
    """Count one draft for this member; False once they pass `limit` within the hour."""
    key = f"ai-drafts-{user_id}"
    cache.add(key, 0, timeout=3600)
    return cache.incr(key) <= limit
