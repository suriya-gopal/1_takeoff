"""
Second opinion on the on-device model's draft.

The small model sometimes invents place names. When the hosted assistant is set up, each draft is sent to it
once per city to be checked: real places stay, a made-up one is replaced with a real alternative when the
assistant offers one, and anything it cannot confirm is marked so the member knows to double-check it.
"""

from . import guardrails, remote

REPLACED = "replaced after a place check"
UNCONFIRMED = "could not confirm this place"

RULES = (
    "You check travel plans. For each activity listed, decide whether it names a real, specific place or experience "
    "that exists in the given city. Reply ONLY with JSON: "
    '{"checks": [{"day": 1, "slot": "morning", "real": true, "fix": ""}]}. '
    "If an activity is not real, or you cannot tell, set real to false and put in fix the name of a real place that "
    "fits the same idea (or an empty string)."
)


def check_messages(city, days):
    lines = [f"day {i + 1} {slot}: {day[slot]}" for i, day in enumerate(days) for slot in guardrails.SLOTS]
    return [{"role": "system", "content": RULES}, {"role": "user", "content": f"City: {city}\n" + "\n".join(lines)}]


def verify_drafts(drafts):
    """Check every stop's draft in place. Returns True when all stops were checked, False if any could not be."""
    checked = True
    for draft in drafts:
        try:
            data = remote.chat_json(check_messages(draft.stop.destination.name, draft.days))
        except (remote.ApiNotConfigured, remote.ApiFailed):
            checked = False
            continue
        for (index, slot), result in guardrails.validate_checks(data).items():
            if index >= len(draft.days) or result["real"]:
                continue
            if result["fix"]:
                draft.days[index][slot] = result["fix"]
                draft.notes[(index, slot)] = REPLACED
            else:
                draft.notes[(index, slot)] = UNCONFIRMED
    return checked
