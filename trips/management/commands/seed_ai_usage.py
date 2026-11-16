"""
Fill the AI usage dashboard with sample records.

    python manage.py seed_ai_usage                 # 45 days of simulated use + the saved evaluation run
    python manage.py seed_ai_usage --days 60 --seed 7
    python manage.py seed_ai_usage --clear         # remove everything this command added

Two kinds of record are added, and each is labelled so the dashboard can tell them apart:

  evaluation   the "Ask about this trip" cases in docs/ai_eval/ask_eval.csv. Their search and generation times were
               measured with the real models, so they are imported as they are.
  simulated    invented requests for demonstration. Sizes and speeds follow the measurements in notes.txt and the
               evaluation run (about 3 s per answer, 650 prompt and 120 completion tokens per city draft), but no
               value is a measurement of this server. The same --seed always gives the same records.
"""

import csv
import math
import random
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from trips.ai import telemetry
from trips.models import AIRequest, Traveler, Trip

CITIES = ["Kyoto", "Osaka", "Lisbon", "Porto", "Venice", "Rome", "Reykjavik", "New York", "Tokyo", "Paris", "Barcelona", "Bangkok"]
QUESTIONS = {
    "getting_around": ["How do I get from the airport to {c}?", "Is there a metro pass in {c}?", "What is the best way to get around {c} by train?"],
    "food": ["What local food should I try in {c}?", "Where can I eat cheaply in {c}?", "Which dish is {c} famous for?"],
    "sights": ["Do we need to book the museums in {c} ahead?", "What are the must see sights in {c}?", "Which tours in {c} are worth it?"],
    "costs": ["How much does a day in {c} cost?", "Is {c} expensive for a family?", "What is a cheap way to travel around {c}?"],
    "weather_season": ["Will it rain in {c} in November?", "What is the weather like in {c} in winter?", "Is summer too hot in {c}?"],
    "practical": ["Is {c} safe at night?", "Do I need a visa for {c}?", "Do people tip in {c}?"],
    "other": ["Tell me about {c}.", "Is {c} worth a visit?"],
}
TOPIC_WEIGHTS = {"getting_around": 24, "food": 20, "sights": 22, "costs": 14, "weather_season": 12, "practical": 6, "other": 2}
FEATURE_WEIGHTS = {"ask": 58, "day_plan": 16, "places": 12, "packing": 14}
INTERESTS = ["food and markets", "architecture", "easy hikes", "museums", "nightlife", "beaches", "history"]
# (median seconds, spread of the log, prompt tokens, completion tokens) per feature
SHAPE = {
    "ask": (2.8, 0.45, 430, 90), "day_plan": (6.5, 0.5, 650, 140), "places": (2.6, 0.35, 520, 620),
    "packing": (2.2, 0.35, 330, 460), "place_check": (1.7, 0.35, 160, 65),
}


def lognormal(rng, median, sigma):
    return median * math.exp(rng.gauss(0, sigma))


class Command(BaseCommand):
    help = "Add sample AI usage records (simulated, plus the saved evaluation run) for the AI usage dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=45, help="How many days back the simulated use spreads over.")
        parser.add_argument("--per-day", type=int, default=14, help="Average simulated requests on a busy day.")
        parser.add_argument("--seed", type=int, default=42, help="Random seed; the same seed gives the same records.")
        parser.add_argument("--clear", action="store_true", help="Delete the simulated and evaluation records and stop.")
        parser.add_argument("--no-evaluation", action="store_true", help="Skip importing docs/ai_eval/ask_eval.csv.")

    def handle(self, *args, **opts):
        removed, _ = AIRequest.objects.filter(origin__in=("simulated", "evaluation")).delete()
        if opts["clear"]:
            self.stdout.write(f"Removed {removed} sample records.")
            return
        travelers = self.members()
        trips = list(Trip.objects.all()[:20])
        rng = random.Random(opts["seed"])
        simulated = self.simulate(rng, opts["days"], opts["per_day"], travelers, trips)
        evaluated = 0 if opts["no_evaluation"] else self.import_evaluation(travelers)
        self.stdout.write(self.style.SUCCESS(
            f"Added {simulated} simulated and {evaluated} evaluation records (replaced {removed} earlier ones)."))

    def members(self):
        """A handful of members to attribute the sample records to; demo accounts are made if too few exist."""
        existing = list(Traveler.objects.all()[:8])
        for number in range(len(existing), 6):
            user, _ = User.objects.get_or_create(username=f"demo_traveler_{number + 1}",
                                                 defaults={"email": f"demo{number + 1}@example.com"})
            user.set_unusable_password()
            user.save()
            existing.append(Traveler.for_user(user))
        return existing

    def simulate(self, rng, days, per_day, travelers, trips):
        now = timezone.localtime()   # local time, so "weekday" and "daytime" mean Chicago time
        rows = []
        for back in range(days, -1, -1):
            day = now - timedelta(days=back)
            growth = 0.55 + 0.9 * (days - back) / max(days, 1)            # use grows over the period
            quiet = 0.6 if day.weekday() >= 5 else 1.0                      # quieter on Saturday and Sunday
            slow_spell = 1.35 if 14 <= back <= 18 else 1.0                   # one stretch of slower responses
            for _ in range(max(0, round(rng.gauss(per_day * growth * quiet, 2)))):
                feature = rng.choices(list(FEATURE_WEIGHTS), weights=FEATURE_WEIGHTS.values())[0]
                when = day.replace(hour=rng.choices(range(24), weights=[1] * 7 + [3, 5, 6, 6, 5, 5, 6, 6, 5, 5, 6, 7, 8, 8, 6, 4, 2])[0],
                                   minute=rng.randrange(60), second=rng.randrange(60))
                rows.append(self.one_request(rng, feature, when, slow_spell, travelers, trips))
                if feature == "day_plan" and rng.random() < 0.5:           # half of the drafts are place-checked
                    rows.append(self.one_request(rng, "place_check", when + timedelta(seconds=8), slow_spell, travelers, trips))
        AIRequest.objects.bulk_create(rows)
        return len(rows)

    def one_request(self, rng, feature, when, slow, travelers, trips):
        median, sigma, prompt, completion = SHAPE[feature]
        runtime = "hosted" if feature in ("places", "packing", "place_check") else "local"
        city = rng.choice(CITIES)
        text, topic, search_ms = "", "", None
        if feature == "ask":
            topic = rng.choices(list(TOPIC_WEIGHTS), weights=TOPIC_WEIGHTS.values())[0]
            text = rng.choice(QUESTIONS[topic]).format(c=city)
            if rng.random() < 0.18:
                text += " " + rng.choice(["We are travelling with two kids.", "We go in early March.", "Budget is tight for us."])
            search_ms = round(lognormal(rng, 22, 0.5))
        elif feature == "day_plan":
            text = rng.choice(INTERESTS)
        elif feature == "places":
            text = rng.choice(INTERESTS)
        chars = len(text) if feature != "packing" and feature != "place_check" else 0
        prompt_tokens = max(40, round(rng.gauss(prompt + chars * 0.25, prompt * 0.12)))
        completion_tokens = max(10, round(rng.gauss(completion, completion * 0.2)))
        latency = lognormal(rng, median, sigma) * slow * (1 + chars / 900)
        if runtime == "local":
            latency = latency * (0.7 + completion_tokens / (completion * 3.3))
        status = "ok"
        roll = rng.random()
        if feature == "ask":
            status = ("refused" if roll < 0.04 else "no_match" if roll < 0.13 else "fallback" if roll < 0.17
                      else "failed" if roll < 0.19 else "ok")
            if status == "no_match":
                latency, completion_tokens = (search_ms or 20) / 1000, 0
            if status == "refused":
                latency, prompt_tokens, completion_tokens, city, topic = 0, 0, 0, "", ""
        elif roll < 0.03:
            status, completion_tokens = "failed", 0
        elif feature == "day_plan" and roll > 0.985:
            status, latency = "unavailable", 0
        latency_ms = round(latency * 1000)
        cost = telemetry.estimate_cost(runtime, latency_ms, prompt_tokens, completion_tokens) if latency_ms else Decimal(0)
        return AIRequest(
            created_at=when, feature=feature, runtime=runtime, traveler=rng.choice(travelers),
            trip=rng.choice(trips) if trips else None,
            model_name=(settings.AI_API_MODEL or "hosted-model") if runtime == "hosted" else settings.AI_LOCAL_MODEL,
            status=status, topic=topic, city=city if feature in ("ask", "places") and status != "refused" else "",
            query_text=text if feature == "ask" and status != "refused" else "", input_chars=len(text),
            latency_ms=latency_ms, search_ms=search_ms if feature == "ask" and status != "refused" else None,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, tokens_measured=False,
            cost_usd=cost, origin="simulated",
        )

    def import_evaluation(self, travelers):
        """The measured evaluation cases, spread over the last few days so they appear in the shorter periods."""
        path = Path(settings.BASE_DIR) / "docs" / "ai_eval" / "ask_eval.csv"
        if not path.exists():
            return 0
        rows = []
        with path.open(newline="", encoding="utf-8") as handle:
            for i, case in enumerate(csv.DictReader(handle)):
                generate = float(case["generate_s"] or 0)
                search_ms = int(float(case["search_ms"] or 0))
                latency_ms = search_ms + round(generate * 1000)
                status = {"answered": "ok", "no_match": "no_match", "sources_only": "fallback"}.get(case["status"], "failed")
                text = case["question"]
                city = (case["cities"].split(";")[0].split(",")[0]).strip()
                prompt_tokens = telemetry.estimate_tokens(len(case["question"]) + 4 * 430)
                completion_tokens = telemetry.estimate_tokens(len(case["answer"])) if case["answer"] else 0
                rows.append(AIRequest(
                    created_at=timezone.now() - timedelta(days=2, hours=i), feature="ask", runtime="local",
                    model_name=settings.AI_LOCAL_MODEL, traveler=travelers[0], status=status,
                    topic=telemetry.classify_topic(case["question"]), city=city, query_text=text, input_chars=len(case["question"]),
                    latency_ms=latency_ms, search_ms=search_ms, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                    tokens_measured=False, cost_usd=telemetry.estimate_cost("local", latency_ms, prompt_tokens, completion_tokens),
                    origin="evaluation",
                ))
        AIRequest.objects.bulk_create(rows)
        return len(rows)
