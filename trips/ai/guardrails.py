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


def allow_request(user_id, limit, scope="drafts"):
    """Count one request in `scope` for this member; False once they pass `limit` within the hour."""
    key = f"ai-{scope}-{user_id}"
    cache.add(key, 0, timeout=3600)
    return cache.incr(key) <= limit


def safe_title(value):
    """An item title that is fit to put in a prompt, or '' when it looks like an attempt to steer the model."""
    text = clean_text(value, MAX_ITEM_LENGTH)
    return "" if any(phrase in text.lower() for phrase in BLOCKED_PHRASES) else text


def _text(value, limit):
    return clean_text(value, limit) if isinstance(value, str) else ""


def validate_places(data, limit=8):
    """Place suggestions: a list of {name, why, cost, free, hidden_gem, tags}; unusable entries are dropped."""
    entries = data.get("places") if isinstance(data, dict) else None
    places = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        name, why = _text(entry.get("name"), MAX_ITEM_LENGTH), _text(entry.get("why"), 160)
        try:
            cost = max(0, min(float(entry.get("cost_usd", 0)), 10000))
        except (TypeError, ValueError):
            cost = 0
        tags = [t for t in (_text(t, 20) for t in entry.get("tags", []) if isinstance(t, str)) if t][:4]
        if name and why:
            places.append({
                "name": name, "why": why, "cost_usd": round(cost, 2), "free": cost == 0 or entry.get("free") is True,
                "hidden_gem": entry.get("hidden_gem") is True, "tags": tags,
            })
    return places[:limit] or None


def validate_packing(data, limit=14):
    """Packing list: a list of {item, reason}."""
    entries = data.get("items") if isinstance(data, dict) else None
    items = []
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict) and _text(entry.get("item"), 60) and _text(entry.get("reason"), 120):
            items.append({"item": _text(entry["item"], 60), "reason": _text(entry["reason"], 120)})
    return items[:limit] or None


def validate_checks(data):
    """Place checks: {(day_index, slot): {"real": bool, "fix": str}} keyed from 1-based day numbers."""
    entries = data.get("checks") if isinstance(data, dict) else None
    result = {}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("slot") not in SLOTS or not isinstance(entry.get("day"), int):
            continue
        result[(entry["day"] - 1, entry["slot"])] = {"real": entry.get("real") is True, "fix": _text(entry.get("fix"), MAX_ITEM_LENGTH)}
    return result
