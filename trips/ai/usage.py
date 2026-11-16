"""
Token counts for the AI call in progress.

The model clients (model.py, remote.py) report what they used with add(); telemetry.track() reads the total
when the call ends. Counts are kept per thread, so requests served at the same time do not mix.
"""

import threading

_state = threading.local()


def start():
    _state.prompt = 0
    _state.completion = 0
    _state.measured = False


def add(prompt_tokens, completion_tokens):
    """Add the tokens of one model call (a feature may make more than one)."""
    if not hasattr(_state, "prompt"):
        start()
    _state.prompt += int(prompt_tokens or 0)
    _state.completion += int(completion_tokens or 0)
    _state.measured = True


def totals():
    """(prompt_tokens, completion_tokens, measured) since start()."""
    return getattr(_state, "prompt", 0), getattr(_state, "completion", 0), getattr(_state, "measured", False)
