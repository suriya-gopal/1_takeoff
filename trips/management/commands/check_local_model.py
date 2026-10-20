"""Time one day-plan draft on this machine: `python manage.py check_local_model`."""

import time

from django.core.management.base import BaseCommand
from django.conf import settings

from trips.ai import guardrails, model, prompts


class Command(BaseCommand):
    help = "Load the on-device model, draft a short sample plan and report how long it took."

    def handle(self, *args, **options):
        self.stdout.write(f"Model: {settings.AI_LOCAL_MODEL}")
        start = time.time()
        model._load()
        self.stdout.write(f"Loaded in {time.time() - start:.1f}s on {model._loaded['device']}")
        messages = prompts.build_messages("Chicago", 2, "food and architecture", "moderate")
        start = time.time()
        reply = model.generate_text(messages, max_new_tokens=240)
        seconds = time.time() - start
        plan = guardrails.validate_days(guardrails.extract_json(reply), 2)
        self.stdout.write(f"Generated in {seconds:.1f}s; usable plan: {'yes' if plan else 'no'}")
        self.stdout.write(reply)
