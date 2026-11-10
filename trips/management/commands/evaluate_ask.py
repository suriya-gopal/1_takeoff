"""
Run the 'Ask about this trip' test cases through the real models and save the results.

    python manage.py evaluate_ask                                  # current settings
    python manage.py evaluate_ask --chunk-words 0 --min-score 0 --label before
                                   # the setup before the A8 improvements: whole paragraphs, no match threshold

Each case is a trip's cities plus a question, as a member would ask it on the trip page. The command prints a table
and writes docs/ai_eval/ask_eval[_<label>].md and .csv (answers, sources, scores, timings) for README_AI.md.
"""

import csv
import re
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.test import override_settings

from trips.ai import ask, guardrails

# (id, trip cities, question, facts a good answer contains: each inner list is one fact, any word counts)
CASES = [
    ("T1", ["Kyoto, Japan", "Osaka, Japan"], "How do I get from the airport to Kyoto?",
     [["kansai", "kix"], ["haruka"]]),
    ("T2", ["Lisbon, Portugal", "Porto, Portugal"], "What local food should I try in Lisbon?",
     [["nata"], ["bacalhau", "cod", "sardine", "bifana"]]),
    ("T3", ["Venice, Italy", "Florence, Italy"], "Will Venice be flooded if we go in November?",
     [["acqua alta", "high tide", "high water", "flood"], ["mose", "barrier"]]),
    ("T4", ["Reykjavik, Iceland"], "Can we see the northern lights in July?",
     [["no", "not", "cannot", "unlikely"], ["dark", "midnight sun", "september", "april"]]),
    ("T5", ["Rome, Italy", "Florence, Italy"], "Do we need to book the Vatican Museums ahead, and are they open on Sunday?",
     [["advance", "ahead", "book"], ["sunday", "closed"]]),
    # Probes for the weaknesses A8 found: a fact the model thinks it already knows (A8 Q6), a near-topic question
    # the guides cannot answer, an off-topic question, and a comparison across two cities (A8 Q7)
    ("F1", ["New York, United States"], "What is a cheap way to ride the subway a lot in New York?",
     [["omny", "cap"], ["12", "twelve"]]),
    ("F2", ["Tokyo, Japan"], "What is the best sushi restaurant in Tokyo for a birthday dinner?",
     [["do not know", "don't know", "not mention", "no specific", "not provide"]]),
    ("F3", ["Lisbon, Portugal", "Porto, Portugal"], "What time does the Porto cathedral open on Sundays?",
     [["do not know", "don't know", "not mention", "not provide"]]),
    ("F4", ["Lisbon, Portugal", "Porto, Portugal"], "Which is cheaper per day, Lisbon or Porto?",
     [["porto"], ["85"], ["95"]]),
]


def fact_score(text, facts):
    lowered = " " + re.sub(r"[^a-z0-9 ]+", " ", text.lower()) + " "
    hit = sum(any((f" {w} " in lowered) if len(w) <= 3 else (w in text.lower()) for w in group) for group in facts)
    return round(1 + 9 * hit / len(facts), 1)


class Command(BaseCommand):
    help = "Run the Ask-about-this-trip evaluation cases and save the results."

    def add_arguments(self, parser):
        parser.add_argument("--top-k", type=int, default=None)
        parser.add_argument("--min-score", type=float, default=None)
        parser.add_argument("--chunk-words", type=int, default=None, help="0 = whole paragraphs")
        parser.add_argument("--label", default="")

    def handle(self, *args, **opts):
        overrides = {}
        if opts["top_k"]:
            overrides["AI_ASK_TOP_K"] = opts["top_k"]
        if opts["min_score"] is not None:
            overrides["AI_ASK_MIN_SCORE"] = opts["min_score"]
        if opts["chunk_words"] is not None:
            overrides["AI_ASK_CHUNK_WORDS"] = opts["chunk_words"]
        rows = []
        with override_settings(**overrides):
            self.stdout.write(f"embedding {settings.AI_EMBEDDING_MODEL} | generator {settings.AI_LOCAL_MODEL} | "
                              f"top-k {settings.AI_ASK_TOP_K} | min score {settings.AI_ASK_MIN_SCORE} | "
                              f"chunk words {settings.AI_ASK_CHUNK_WORDS or 'whole paragraphs'}")
            for case_id, cities, question, facts in CASES:
                started = time.perf_counter()
                try:
                    result = ask.answer_for_cities(cities, ask.check_question(question))
                except guardrails.InvalidRequest as exc:   # the same input check the page uses
                    result = {"status": f"rejected: {exc}", "sources": [], "answer": "", "unsupported": [],
                              "search_ms": 0, "generate_s": 0.0}
                total = time.perf_counter() - started
                sources = " | ".join(f"{s['id']} ({s['score']:.2f})" for s in result["sources"])
                context = " ".join(s["text"] for s in result["sources"])
                rows.append(dict(
                    case=case_id, cities="; ".join(cities), question=question, status=result["status"],
                    sources=sources, context_quality=fact_score(context, facts),
                    answer_quality=fact_score(result["answer"], facts) if result["answer"] else "",
                    unsupported=", ".join(result["unsupported"]), search_ms=result["search_ms"],
                    generate_s=result["generate_s"], total_s=round(total, 1), answer=result["answer"],
                ))
                self.stdout.write(f"\n{case_id} [{result['status']}] {question}\n  sources: {sources}\n"
                                  f"  answer ({result['generate_s']} s): {result['answer']}")
        self.save(rows, opts["label"])

    def save(self, rows, label):
        out = Path(settings.BASE_DIR) / "docs" / "ai_eval"
        out.mkdir(parents=True, exist_ok=True)
        stem = "ask_eval" + (f"_{label}" if label else "")
        with open(out / f"{stem}.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        cols = ["case", "question", "status", "sources", "context_quality", "answer_quality", "unsupported",
                "search_ms", "generate_s", "answer"]
        lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        lines += ["| " + " | ".join(str(r[c]).replace("|", "/").replace("\n", " ") for c in cols) + " |" for r in rows]
        (out / f"{stem}.md").write_text(
            f"Embedding {settings.AI_EMBEDDING_MODEL}, generator {settings.AI_LOCAL_MODEL}, "
            f"top-k {settings.AI_ASK_TOP_K}, min score {settings.AI_ASK_MIN_SCORE}, "
            f"chunk words {settings.AI_ASK_CHUNK_WORDS or 'whole paragraphs'}\n\n" + "\n".join(lines) + "\n",
            encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"\nSaved docs/ai_eval/{stem}.md and .csv"))
