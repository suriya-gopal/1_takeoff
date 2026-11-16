"""
"Ask about this trip": answer a traveler's question from TakeOff's destination guides.

Flow: clean the question → find the matching guide paragraphs for the trip's own cities (retrieval.py) →
build one prompt with the paragraphs as numbered sources → generate with the on-device model that already writes
day-by-day drafts (model.py) → check the reply → return the answer together with its sources.

When generation fails or times out, the sources are still returned, so the member gets the relevant guide text
instead of an error page.
"""

import re
import time

from django.conf import settings

from . import guardrails, model, retrieval

MAX_QUESTION_LENGTH = 300
MAX_ANSWER_LENGTH = 700

# The grounded prompt from A8 round 2: forbid added facts, keep the model on the question's city.
SYSTEM_PROMPT = (
    "You are {site}'s travel assistant. Answer the traveler's question using only facts stated in the numbered "
    "context below. Do not add prices, times, places or tips that are not in the context. "
    "Each passage starts with the city it is about; use only passages about the city in the question. "
    "If the context does not contain the answer, say that you do not know. "
    "Answer in two or three sentences."
)

_DONT_KNOW = re.compile(r"(do not|don't) know|not (mentioned|provided|available|in the context)", re.I)
_ECHO = re.compile(r"^\s*(context|question|sources?)\s*:", re.I | re.M)


class AskFailed(Exception):
    """Nothing useful could be produced for this question."""


def check_question(value):
    """Return the cleaned question, or raise guardrails.InvalidRequest with a message for the member."""
    raw = value or ""
    if len(raw) > MAX_QUESTION_LENGTH * 2:
        raise guardrails.InvalidRequest("Please keep your question under 300 characters.")
    text = guardrails.clean_text(raw, MAX_QUESTION_LENGTH)
    if len(re.findall(r"[A-Za-z]", text)) < 3:
        raise guardrails.InvalidRequest("Please type a question, for example: what should I eat in Lisbon?")
    if any(phrase in text.lower() for phrase in guardrails.BLOCKED_PHRASES):
        raise guardrails.InvalidRequest("Please ask a travel question in plain words.")
    return text


def trip_cities(trip):
    """'City, Country' names of the trip's stops, in route order and without repeats."""
    return list(dict.fromkeys(
        f"{s.destination.name}, {s.destination.country}" for s in trip.stops.select_related("destination")
    ))


def build_messages(question, sources):
    """Best passage last, directly before the question: small models weigh the most recent text most (A8)."""
    context = "\n\n".join(f"[{i + 1}] {s['text']}" for i, s in enumerate(reversed(sources)))
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(site=settings.SITE_NAME)},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]


def numbers(text):
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def clean_answer(text):
    """Keep the reply's first part, drop echoed prompt sections, trim at a sentence end. '' if unusable."""
    text = _ECHO.split(text or "")[0]
    text = " ".join(text.split())
    if len(text) > MAX_ANSWER_LENGTH:
        cut = text[:MAX_ANSWER_LENGTH]
        text = cut[:cut.rfind(". ") + 1] if ". " in cut else cut
    return text if len(re.findall(r"[A-Za-z]", text)) >= 3 else ""


def answer_question(trip, question):
    """Answer `question` using the guides for the trip's own cities (see answer_for_cities)."""
    return answer_for_cities(trip_cities(trip), question)


def answer_for_cities(trip_city_names, question):
    """
    Answer `question` from the guides of `trip_city_names` ('City, Country' strings). Returns a dict:

    answer: text ('' when only sources could be given), sources: the guide chunks used, status: one of
    "answered", "no_match" (nothing relevant in the guides), "no_guides" (none of the trip's cities has a guide),
    "sources_only" (the model failed, sources still shown); unsupported: numbers in the answer that the sources do
    not contain; search_ms and generate_s for timing.
    """
    cities = [c for c in trip_city_names if c in set(retrieval.guide_cities())]
    result = {"answer": "", "sources": [], "status": "", "unsupported": [], "search_ms": 0, "generate_s": 0.0,
              "cities": cities, "said_unknown": False, "reason": ""}
    if not cities:
        result["status"] = "no_guides"
        return result

    started = time.perf_counter()
    sources = retrieval.search(question, cities=cities)
    result.update(sources=sources, search_ms=round((time.perf_counter() - started) * 1000))
    if not sources:
        result["status"] = "no_match"
        return result

    messages = build_messages(question, sources)
    started = time.perf_counter()
    reply, reason = "", ""
    for attempt in range(2):          # one retry, with a little randomness, if the first reply is unusable
        try:
            reply = clean_answer(model.generate_text(messages, max_new_tokens=settings.AI_ASK_MAX_NEW_TOKENS,
                                                     sample=attempt > 0))
            reason = "" if reply else "The assistant's reply was not usable."
        except model.ModelUnavailable as exc:   # switched off or could not load: no point retrying
            reply, reason = "", str(exc)
            break
        except Exception:             # generation error: retry once, then fall back to the sources
            reply, reason = "", "The assistant could not write an answer this time."
        if reply:
            break
    result["generate_s"] = round(time.perf_counter() - started, 1)

    if not reply:
        result.update(status="sources_only", reason=reason)
        return result
    context = " ".join(s["text"] for s in sources)
    result.update(
        answer=reply, status="answered",
        unsupported=sorted(numbers(reply) - numbers(context) - numbers(question)),
        said_unknown=bool(_DONT_KNOW.search(reply)),
    )
    return result
