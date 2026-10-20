"""
Client for the hosted language-model service.

Uses the `openai` package, which also talks to other providers that expose the same style of endpoint
(set AI_API_BASE_URL). Replies are asked for as JSON and parsed with the same checks as the on-device model.
"""

from django.conf import settings

from . import guardrails

ATTEMPTS = 2


class ApiNotConfigured(Exception):
    """No key or model is set, so hosted features are switched off."""


class ApiFailed(Exception):
    """The service was unreachable or did not return usable JSON."""


def configured():
    return bool(settings.AI_API_KEY and settings.AI_API_MODEL)


def _client():
    from openai import OpenAI

    return OpenAI(
        api_key=settings.AI_API_KEY,
        base_url=settings.AI_API_BASE_URL or None,
        timeout=settings.AI_API_TIMEOUT_SECONDS,
        max_retries=0,
    )


def chat_json(messages, max_tokens=900):
    """Send chat messages and return the reply parsed as a JSON object."""
    if not configured():
        raise ApiNotConfigured("The hosted assistant is not set up on this server.")
    last_error = None
    for _ in range(ATTEMPTS):
        try:
            reply = _client().chat.completions.create(
                model=settings.AI_API_MODEL, messages=messages, max_tokens=max_tokens, temperature=0.3,
            )
            data = guardrails.extract_json(reply.choices[0].message.content or "")
        except Exception as exc:  # network error, bad key, rate limit at the provider...
            last_error = exc
            continue
        if isinstance(data, dict):
            return data
    raise ApiFailed(f"The hosted assistant did not answer: {last_error or 'unusable reply'}")
