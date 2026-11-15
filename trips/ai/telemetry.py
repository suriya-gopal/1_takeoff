"""
Usage records for the AI features.

Each AI page wraps its model call in `track(...)`, which times it, collects the tokens the model clients report
(usage.py), estimates the cost and saves one AIRequest row for the dashboard. Recording never breaks a page:
if the row cannot be saved the error is logged and the member still gets their answer.

Cost basis
    on-device model   seconds the request ran x the hourly price of the server (AI_SERVER_COST_PER_HOUR)
    hosted model      prompt and completion tokens x the provider's price per million tokens
"""

import logging
import re
import time
from contextlib import contextmanager
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from ..models import AIRequest, Traveler
from . import usage

log = logging.getLogger(__name__)

TOPICS = {
    "getting_around": ("airport", "train", "bus", "metro", "subway", "transport", "taxi", "get around", "getting around",
                       "ferry", "transit", "pass", "ride", "get from", "fly"),
    "food": ("eat", "food", "restaurant", "cafe", "dish", "try", "cuisine", "dinner", "lunch", "breakfast", "sushi",
             "drink", "street food"),
    "sights": ("visit", "museum", "see", "tour", "attraction", "book", "open", "tickets", "cathedral", "temple",
               "hike", "beach", "sights", "things to do"),
    "costs": ("cost", "cheap", "price", "budget", "expensive", "money", "pay", "afford", "per day", "currency"),
    "weather_season": ("weather", "rain", "flood", "season", "snow", "northern lights", "aurora", "hot", "cold",
                       "winter", "summer", "spring", "autumn", "month", "temperature"),
    "practical": ("safe", "scam", "tip", "tipping", "visa", "vaccine", "sim", "plug", "language", "wifi", "luggage",
                  "kids", "family"),
}
TOPIC_LABELS = {
    "getting_around": "Getting around", "food": "Food", "sights": "Sights & tickets", "costs": "Costs",
    "weather_season": "Weather & season", "practical": "Practical tips", "other": "Other",
}


def classify_topic(text):
    """The first topic whose keywords appear in `text` (most specific list first); "other" if none, "" if no text."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return ""
    words = set(re.findall(r"[a-z']+", lowered))
    for topic, keys in TOPICS.items():
        if any((k in lowered) if " " in k else (k in words) for k in keys):
            return topic
    return "other"


def estimate_cost(runtime, latency_ms, prompt_tokens, completion_tokens):
    """Estimated dollars for one request (see the module notes for the basis)."""
    if runtime == "hosted":
        dollars = (prompt_tokens * settings.AI_API_PRICE_IN_PER_M + completion_tokens * settings.AI_API_PRICE_OUT_PER_M) / 1e6
    else:
        dollars = latency_ms / 1000 / 3600 * settings.AI_SERVER_COST_PER_HOUR
    return Decimal(str(round(dollars, 8)))


def estimate_tokens(chars):
    """Rough token count (about 4 characters each) for calls that did not report their own."""
    return max(1, round(chars / 4))


class Call:
    """What the page tells telemetry about the call in progress."""

    def __init__(self, text=""):
        self.status = "ok"
        self.text = text
        self.city = ""
        self.search_ms = None

    def from_ask(self, result):
        """Fill in status, city and retrieval time from an `ask.answer_for_cities` result."""
        self.status = {"answered": "ok", "no_match": "no_match", "no_guides": "no_match",
                       "sources_only": "fallback"}.get(result["status"], "failed")
        self.search_ms = result.get("search_ms")
        if result.get("sources"):
            self.city = result["sources"][0]["city"].split(",")[0]    # "Rome, Italy" -> "Rome"


def record(request, feature, *, status="ok", runtime="local", text="", input_chars=None, trip=None, city="",
           latency_ms=0, search_ms=None, tokens=(0, 0, False), when=None, origin="live"):
    """Save one AIRequest row. Returns it, or None if it could not be saved."""
    try:
        prompt, completion, measured = tokens
        chars = len(text) if input_chars is None else input_chars
        if not measured and status in ("ok", "fallback"):
            prompt, completion = estimate_tokens(chars), 0
        user = getattr(request, "user", None)
        return AIRequest.objects.create(
            created_at=when or timezone.now(), feature=feature, runtime=runtime,
            model_name=(settings.AI_API_MODEL if runtime == "hosted" else settings.AI_LOCAL_MODEL)[:120],
            traveler=Traveler.for_user(user) if user is not None and user.is_authenticated else None,
            trip=trip, status=status, topic=classify_topic(text), city=city[:80],
            query_text=text if feature == "ask" else "", input_chars=chars, latency_ms=latency_ms,
            search_ms=search_ms, prompt_tokens=prompt, completion_tokens=completion, tokens_measured=measured,
            cost_usd=estimate_cost(runtime, latency_ms, prompt, completion), origin=origin,
        )
    except Exception:  # never let bookkeeping break an AI page
        log.exception("Could not record the AI request")
        return None


@contextmanager
def track(request, feature, *, runtime="local", text="", trip=None):
    """
    Time the AI call inside the block and record it. The block sets `call.status` (and `call.city`,
    `call.search_ms`, or calls `call.from_ask(result)`); an exception that escapes is recorded as "failed".
    """
    call = Call(text)
    usage.start()
    started = time.perf_counter()
    try:
        yield call
    except Exception:
        call.status = "failed"
        raise
    finally:
        record(
            request, feature, status=call.status, runtime=runtime, text=text, trip=trip, city=call.city,
            latency_ms=round((time.perf_counter() - started) * 1000), search_ms=call.search_ms, tokens=usage.totals(),
        )
