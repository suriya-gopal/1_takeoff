"""
AI usage dashboard: how the AI features perform, how members use them and what they cost.

The page (/dashboard/) shows three groups of questions. Each question is answered by a chart or table built from
the AIRequest records (trips/ai/telemetry.py):

    performance   response time spread, slower features and inputs, change over time
    behavior      what members ask about, how often features are used, what kinds of input arrive
    cost          cost per request, token-heavy requests, spend over time

Numbers that need statistics (mean, median, 95th percentile, spread, correlation, outliers) are computed here and
shown as tiles and tables. Charts are Vega-Lite specifications served as JSON (/dashboard/charts.json) over one
shared list of request rows, so every chart on the page always reflects the same filters.
"""

import math
import re
import statistics
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .access import api_login_required
from .ai.telemetry import TOPIC_LABELS
from .charts import CHART_COLORS, VEGA_LITE_SCHEMA
from .models import AIRequest

FEATURE_LABELS = dict(AIRequest.FEATURES)
STATUS_LABELS = dict(AIRequest.STATUSES)
EXECUTED = ("ok", "no_match", "fallback", "failed")   # the model or search actually ran
RANGES = [("7", "Last 7 days"), ("30", "Last 30 days"), ("90", "Last 90 days"), ("0", "All time")]
STOP_WORDS = set(
    "what which where when does should would could with from that this have there about into your you the and for "
    "are can how do we our any best some much many get go to in is it of a an or on at be if".split()
)
MAX_ROWS = 20000


# ---------------------------------------------------------------------------
# Small statistics helpers
# ---------------------------------------------------------------------------
def percentile(values, q):
    """The q-th percentile (0-100) with linear interpolation; None for no data."""
    data = sorted(values)
    if not data:
        return None
    pos = (len(data) - 1) * q / 100
    low, high = math.floor(pos), math.ceil(pos)
    return data[low] + (data[high] - data[low]) * (pos - low)


def mean(values):
    return statistics.fmean(values) if values else None


def spread(values):
    """Sample standard deviation (None with fewer than two values)."""
    return statistics.stdev(values) if len(values) > 1 else None


def correlation(xs, ys):
    """Pearson r between two lists; None when it is undefined (too few points or no variation)."""
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return statistics.correlation(xs, ys)


def outlier_count(values):
    """Values above Q3 + 1.5 x IQR, the usual box-plot rule for unusually slow requests."""
    if len(values) < 4:
        return 0
    q1, q3 = percentile(values, 25), percentile(values, 75)
    return sum(1 for v in values if v > q3 + 1.5 * (q3 - q1))


def rounded(value, digits=2):
    """Round for display; None stays None and a tiny negative never shows as "-0.0"."""
    return None if value is None else round(value, digits) + 0.0


def percent(value):
    """A whole-number percentage for display; None stays None."""
    return None if value is None else int(round(value))


# ---------------------------------------------------------------------------
# Filters and data
# ---------------------------------------------------------------------------
class Filters:
    """Time range, feature and data source chosen on the page (read from the query string)."""

    def __init__(self, params):
        self.days = params.get("days") if params.get("days") in dict(RANGES) else "30"
        self.feature = params.get("feature") if params.get("feature") in FEATURE_LABELS else ""
        self.real_only = params.get("data") == "real"

    def query(self):
        parts = [f"days={self.days}"]
        if self.feature:
            parts.append(f"feature={self.feature}")
        if self.real_only:
            parts.append("data=real")
        return "&".join(parts)

    def queryset(self):
        qs = AIRequest.objects.all()
        if self.days != "0":
            qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=int(self.days)))
        if self.feature:
            qs = qs.filter(feature=self.feature)
        if self.real_only:
            qs = qs.exclude(origin="simulated")
        return qs


def load_rows(filters):
    """One plain dict per request (newest first, capped), with labels ready for the charts. No member data."""
    rows = []
    for r in filters.queryset().order_by("-created_at")[:MAX_ROWS]:
        rows.append({
            "id": r.request_id,
            "date": r.created_at.date().isoformat(),
            "hour": r.created_at.hour,
            "feature": r.feature,
            "feature_label": FEATURE_LABELS[r.feature],
            "runtime": r.runtime,
            "status": r.status,
            "status_label": STATUS_LABELS[r.status],
            "executed": r.status in EXECUTED,
            "topic": r.topic,
            "topic_label": TOPIC_LABELS.get(r.topic, ""),
            "city": r.city,
            "input_chars": r.input_chars,
            "latency_s": round(r.latency_ms / 1000, 3),
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens,
            "cost_usd": float(r.cost_usd),
            "traveler": r.traveler_id,
            "origin": r.origin,
        })
    return rows


# ---------------------------------------------------------------------------
# Summary numbers
# ---------------------------------------------------------------------------
def feature_table(executed):
    """Per-feature comparison: how many, how fast, how steady, how costly."""
    table = []
    for feature, label in FEATURE_LABELS.items():
        rows = [r for r in executed if r["feature"] == feature]
        if not rows:
            continue
        latency = [r["latency_s"] for r in rows]
        avg = mean(latency)
        sd = spread(latency)
        table.append({
            "feature": label,
            "requests": len(rows),
            "mean_s": rounded(avg),
            "median_s": rounded(percentile(latency, 50)),
            "p95_s": rounded(percentile(latency, 95)),
            "spread_pct": percent(sd / avg * 100) if sd is not None and avg else None,
            "outliers": outlier_count(latency),
            "r_input": rounded(correlation([r["input_chars"] for r in rows], latency)),
            "mean_tokens": round(mean([r["total_tokens"] for r in rows])),
            "mean_cost": mean([r["cost_usd"] for r in rows]),
            "ok_pct": percent(sum(r["status"] == "ok" for r in rows) / len(rows) * 100),
        })
    return table


def common_terms(limit=10):
    """Most frequent words in members' questions (all members together; individual questions are never shown)."""
    words = Counter()
    for text in AIRequest.objects.filter(feature="ask").exclude(query_text="").values_list("query_text", flat=True):
        words.update(w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOP_WORDS)
    return [{"term": term, "count": count} for term, count in words.most_common(limit)]


def build_summary(rows, filters):
    """Everything the tiles and tables need, as plain numbers."""
    executed = [r for r in rows if r["executed"]]
    latency = [r["latency_s"] for r in executed]
    costs = [r["cost_usd"] for r in executed]
    tokens = [r["total_tokens"] for r in executed]
    asks = [r for r in rows if r["feature"] == "ask"]
    days_in_data = {r["date"] for r in rows}
    span_days = int(filters.days) if filters.days != "0" else max(len(days_in_data), 1)
    total_cost = sum(costs)
    avg = mean(latency)
    sd = spread(latency)
    topics = Counter(r["topic_label"] for r in asks if r["topic_label"])
    origins = Counter(r["origin"] for r in rows)

    return {
        "requests": len(rows),
        "executed": len(executed),
        "members": len({r["traveler"] for r in rows if r["traveler"]}),
        "requests_per_member": rounded(len(rows) / len({r["traveler"] for r in rows if r["traveler"]}), 1)
        if any(r["traveler"] for r in rows) else None,
        "latency": {
            "mean": rounded(avg), "median": rounded(percentile(latency, 50)),
            "p95": rounded(percentile(latency, 95)), "max": rounded(max(latency) if latency else None),
            "spread_pct": percent(sd / avg * 100) if sd is not None and avg else None,
            "outliers": outlier_count(latency),
        },
        "ok_pct": percent(sum(r["status"] == "ok" for r in executed) / len(executed) * 100) if executed else None,
        "refused_pct": rounded(sum(r["status"] in ("refused", "rate_limited") for r in rows) / len(rows) * 100, 1)
        if rows else None,
        "not_covered_pct": percent(sum(r["status"] == "no_match" for r in asks) / len(asks) * 100) if asks else None,
        "top_topic": topics.most_common(1)[0] if topics else None,
        "cost": {
            "total": round(total_cost, 4),
            "per_request": mean(costs),
            "per_1k_tokens": (total_cost / sum(tokens) * 1000) if sum(tokens) else None,
            "mean_tokens": round(mean(tokens)) if tokens else None,
            "per_month": total_cost / span_days * 30 if executed else None,
        },
        "by_feature": feature_table(executed),
        "heaviest": [
            {"date": r["date"], "feature": r["feature_label"], "topic": r["topic_label"] or "-",
             "tokens": r["total_tokens"], "seconds": r["latency_s"], "cost": r["cost_usd"]}
            for r in sorted(executed, key=lambda r: -r["total_tokens"])[:10]
        ],
        "common_terms": common_terms(),
        "origins": {"live": origins["live"], "evaluation": origins["evaluation"], "simulated": origins["simulated"]},
    }


# ---------------------------------------------------------------------------
# Chart definitions (Vega-Lite)
# ---------------------------------------------------------------------------
FEATURE_COLOR = {"field": "feature_label", "type": "nominal", "title": "Feature", "scale": {"range": CHART_COLORS}}
ONLY_RUN = {"filter": "datum.executed"}
ONLY_ASK = {"filter": "datum.feature === 'ask'"}


def base(description, height=280, **spec):
    chart = {
        "$schema": VEGA_LITE_SCHEMA, "description": description, "data": {"name": "rows"},
        "width": "container", "height": height,
    }
    chart.update(spec)
    return chart


def chart_specs():
    """Every chart on the page, by id. They all read the shared "rows" dataset."""
    count = {"aggregate": "count", "type": "quantitative", "title": "Requests", "axis": {"tickMinStep": 1, "format": "d"}}
    day = {"field": "date", "type": "temporal", "timeUnit": "yearmonthdate", "title": None, "axis": {"format": "%b %d", "labelAngle": -30}}
    return {
        # --- system performance ---
        "latency_hist": base("Distribution of response times", transform=[ONLY_RUN], mark={"type": "bar", "cornerRadiusEnd": 2},
            encoding={"x": {"field": "latency_s", "bin": {"maxbins": 24}, "type": "quantitative", "title": "Response time (seconds)"},
                      "y": count, "color": FEATURE_COLOR,
                      "tooltip": [{"field": "feature_label", "title": "Feature"}, {"aggregate": "count", "title": "Requests"}]}),
        "latency_box": base("Response time by feature", height=240, transform=[ONLY_RUN],
            mark={"type": "boxplot", "extent": 1.5, "size": 22},
            encoding={"y": {"field": "feature_label", "type": "nominal", "title": None},
                      "x": {"field": "latency_s", "type": "quantitative", "title": "Response time (seconds)"},
                      "color": {**FEATURE_COLOR, "legend": None}}),
        "latency_vs_input": base("Response time against input length", transform=[ONLY_RUN, {"filter": "datum.input_chars > 0"}],
            layer=[
                {"mark": {"type": "point", "filled": True, "opacity": 0.45, "size": 40},
                 "encoding": {"x": {"field": "input_chars", "type": "quantitative", "title": "Input length (characters)"},
                              "y": {"field": "latency_s", "type": "quantitative", "title": "Response time (seconds)"},
                              "color": FEATURE_COLOR,
                              "tooltip": [{"field": "feature_label", "title": "Feature"},
                                          {"field": "input_chars", "title": "Characters"}, {"field": "latency_s", "title": "Seconds"}]}},
                {"transform": [{"regression": "latency_s", "on": "input_chars", "groupby": ["feature_label"]}],
                 "mark": {"type": "line", "strokeWidth": 2},
                 "encoding": {"x": {"field": "input_chars", "type": "quantitative"}, "y": {"field": "latency_s", "type": "quantitative"},
                              "color": FEATURE_COLOR}}]),
        "latency_trend": base("Median response time per day", transform=[ONLY_RUN],
            layer=[{"mark": {"type": "line", "strokeWidth": 2, "point": {"filled": True, "size": 40}},
                    "encoding": {"x": day, "y": {"aggregate": "median", "field": "latency_s", "type": "quantitative", "title": "Median response time (s)"},
                                 "color": FEATURE_COLOR,
                                 "tooltip": [{"field": "date", "type": "temporal", "title": "Day"}, {"field": "feature_label", "title": "Feature"},
                                             {"aggregate": "median", "field": "latency_s", "title": "Median (s)", "format": ".2f"},
                                             {"aggregate": "count", "title": "Requests"}]}}]),
        # --- user behavior ---
        "topics": base("What members ask about", height=260, transform=[ONLY_ASK, {"filter": "datum.topic_label !== ''"}],
            mark={"type": "bar", "cornerRadiusEnd": 3, "color": CHART_COLORS[0]},
            encoding={"y": {"field": "topic_label", "type": "nominal", "sort": "-x", "title": None},
                      "x": count, "tooltip": [{"field": "topic_label", "title": "Topic"}, {"aggregate": "count", "title": "Questions"}]}),
        "cities": base("Cities members ask about", height=260,
            transform=[ONLY_ASK, {"filter": "datum.city !== ''"}, {"aggregate": [{"op": "count", "as": "n"}], "groupby": ["city"]},
                       {"window": [{"op": "rank", "as": "rank"}], "sort": [{"field": "n", "order": "descending"}]}, {"filter": "datum.rank <= 8"}],
            mark={"type": "bar", "cornerRadiusEnd": 3, "color": CHART_COLORS[2]},
            encoding={"y": {"field": "city", "type": "nominal", "sort": "-x", "title": None},
                      "x": {"field": "n", "type": "quantitative", "title": "Questions", "axis": {"tickMinStep": 1, "format": "d"}},
                      "tooltip": [{"field": "city", "title": "City"}, {"field": "n", "title": "Questions"}]}),
        "usage_daily": base("Requests per day by feature", mark={"type": "bar", "cornerRadiusEnd": 2},
            encoding={"x": day, "y": count, "color": FEATURE_COLOR,
                      "tooltip": [{"field": "date", "type": "temporal", "title": "Day"}, {"field": "feature_label", "title": "Feature"},
                                  {"aggregate": "count", "title": "Requests"}]}),
        "input_length": base("Length of questions", height=240, transform=[ONLY_ASK, {"filter": "datum.input_chars > 0"}],
            mark={"type": "bar", "cornerRadiusEnd": 2, "color": CHART_COLORS[1]},
            encoding={"x": {"field": "input_chars", "bin": {"maxbins": 15}, "type": "quantitative", "title": "Question length (characters)"},
                      "y": {**count, "title": "Questions"}}),
        "outcomes": base("How requests ended", height=240,
            mark={"type": "bar"},
            encoding={"y": {"field": "feature_label", "type": "nominal", "title": None},
                      "x": {"aggregate": "count", "type": "quantitative", "stack": "normalize", "title": "Share of requests", "axis": {"format": "%"}},
                      "color": {"field": "status_label", "type": "nominal", "title": "Outcome", "scale": {"range": CHART_COLORS + ["#c0504d"]}},
                      "tooltip": [{"field": "feature_label", "title": "Feature"}, {"field": "status_label", "title": "Outcome"},
                                  {"aggregate": "count", "title": "Requests"}]}),
        # --- cost ---
        "cost_per_feature": base("Estimated cost per 1,000 requests", height=240,
            transform=[ONLY_RUN, {"calculate": "datum.cost_usd * 1000", "as": "cost_1k"}],
            layer=[{"mark": {"type": "bar", "cornerRadiusEnd": 3},
                    "encoding": {"y": {"field": "feature_label", "type": "nominal", "sort": "-x", "title": None},
                                 "x": {"aggregate": "mean", "field": "cost_1k", "type": "quantitative", "title": "Mean cost per 1,000 requests (USD)", "axis": {"format": "$.2f"}},
                                 "color": {**FEATURE_COLOR, "legend": None},
                                 "tooltip": [{"field": "feature_label", "title": "Feature"},
                                             {"aggregate": "mean", "field": "cost_1k", "title": "USD per 1,000", "format": "$.3f"}]}},
                   {"mark": {"type": "errorbar", "extent": "ci", "ticks": True, "color": "#16233b"},
                    "encoding": {"y": {"field": "feature_label", "type": "nominal", "sort": "-x", "title": None},
                                 "x": {"field": "cost_1k", "type": "quantitative", "title": "Mean cost per 1,000 requests (USD)"}}}]),
        "tokens_by_group": base("Tokens per request by feature and topic", height=320,
            transform=[ONLY_RUN, {"calculate": "datum.topic_label ? 'Question · ' + datum.topic_label : datum.feature_label", "as": "group"},
                       {"aggregate": [{"op": "mean", "field": "prompt_tokens", "as": "Prompt"}, {"op": "mean", "field": "completion_tokens", "as": "Completion"}],
                        "groupby": ["group"]},
                       {"fold": ["Prompt", "Completion"], "as": ["kind", "tokens"]}],
            mark={"type": "bar"},
            encoding={"y": {"field": "group", "type": "nominal", "sort": {"op": "sum", "field": "tokens", "order": "descending"}, "title": None,
                            "axis": {"labelLimit": 260}},
                      "x": {"field": "tokens", "type": "quantitative", "title": "Mean tokens per request"},
                      "color": {"field": "kind", "type": "nominal", "title": "Tokens", "scale": {"range": [CHART_COLORS[0], CHART_COLORS[3]]}},
                      "tooltip": [{"field": "group", "title": "Group"}, {"field": "kind", "title": "Tokens"},
                                  {"field": "tokens", "title": "Mean", "format": ",.0f"}]}),
        "cost_cumulative": base("Spend building up over time",
            transform=[ONLY_RUN, {"timeUnit": "yearmonthdate", "field": "date", "as": "day"},
                       {"aggregate": [{"op": "sum", "field": "cost_usd", "as": "cost"}, {"op": "count", "as": "requests"}], "groupby": ["day"]},
                       {"window": [{"op": "sum", "field": "cost", "as": "running"}, {"op": "sum", "field": "requests", "as": "running_requests"}],
                        "sort": [{"field": "day"}], "frame": [None, 0]}],
            layer=[{"mark": {"type": "area", "color": CHART_COLORS[1], "opacity": 0.35, "line": {"color": CHART_COLORS[0], "strokeWidth": 2}},
                    "encoding": {"x": {"field": "day", "type": "temporal", "title": None, "axis": {"format": "%b %d", "labelAngle": -30}},
                                 "y": {"field": "running", "type": "quantitative", "title": "Cumulative estimated cost (USD)", "axis": {"format": "$.3f"}},
                                 "tooltip": [{"field": "day", "type": "temporal", "title": "Day"},
                                             {"field": "running", "title": "Spend to date (USD)", "format": "$.4f"},
                                             {"field": "running_requests", "title": "Requests to date"},
                                             {"field": "cost", "title": "That day (USD)", "format": "$.4f"}]}}]),
    }


# What each widget answers. The page is built from this list, so every chart sits under the question it serves.
SECTIONS = [
    {
        "id": "performance", "title": "System performance",
        "blurb": "Is the AI fast, steady and reliable?",
        "widgets": [
            {"chart": "latency_hist", "question": "How does response time vary across requests, and how consistent is it?",
             "note": "Each bar counts requests in a time band. A narrow cluster means steady; a long right tail means occasional slow requests."},
            {"chart": "latency_box", "question": "Which features are slower, and how much do they vary?",
             "note": "Box = middle half of requests, line = median, dots = unusually slow requests (above Q3 + 1.5 x IQR)."},
            {"chart": "latency_vs_input", "question": "Do longer inputs make responses slower?",
             "note": "One dot per request with a fitted trend line per feature. The table below gives the correlation (r)."},
            {"chart": "latency_trend", "question": "Is response time getting better or worse over time?",
             "note": "Daily median response time for each feature."},
        ],
    },
    {
        "id": "behavior", "title": "User behavior",
        "blurb": "What do members ask, and how do they use the AI?",
        "widgets": [
            {"chart": "topics", "question": "What are members asking about most?",
             "note": "Questions grouped by topic from the words they use."},
            {"chart": "cities", "question": "Which cities do the questions concern?",
             "note": "The city of the best matching guide passage."},
            {"chart": "usage_daily", "question": "How often are the AI features used, and which ones?",
             "note": "Requests per day, stacked by feature."},
            {"chart": "input_length", "question": "What kind of input do members give?",
             "note": "Question length in characters: short keyword queries or full sentences."},
            {"chart": "outcomes", "question": "How often does a request end without a real answer?",
             "note": "Share of requests by outcome. Refused and rate-limited requests never reach the model."},
        ],
    },
    {
        "id": "cost", "title": "Cost",
        "blurb": "What does each request cost, and where does the money go?",
        "widgets": [
            {"chart": "cost_per_feature", "question": "What does a request cost, and which feature costs the most?",
             "note": "Mean estimated cost per 1,000 requests; the whisker is the 95% confidence interval of the mean."},
            {"chart": "tokens_by_group", "question": "Which kinds of requests use the most tokens?",
             "note": "Mean prompt and completion tokens, by feature and (for questions) topic."},
            {"chart": "cost_cumulative", "question": "How is spend building up over time?",
             "note": "Running total of estimated cost across all features. The monthly projection above uses the daily average."},
        ],
    },
]


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
@login_required
def dashboard_page(request):
    """The AI usage dashboard for signed-in members."""
    filters = Filters(request.GET)
    rows = load_rows(filters)
    summary = build_summary(rows, filters)
    return render(request, "trips/dashboard.html", {
        "filters": filters, "summary": summary, "sections": SECTIONS, "ranges": RANGES,
        "features": FEATURE_LABELS.items(), "charts_url": reverse("trips:dashboard-charts") + "?" + filters.query(),
        "summary_url": reverse("trips:api-dashboard-summary") + "?" + filters.query(),
        "has_data": bool(rows), "server_cost_per_hour": settings.AI_SERVER_COST_PER_HOUR,
    })


@api_login_required
def dashboard_charts_json(request):
    """GET /dashboard/charts.json: the shared request rows and every chart definition."""
    return JsonResponse({"rows": load_rows(Filters(request.GET)), "charts": chart_specs()})


@api_login_required
def api_dashboard_summary(request):
    """GET /api/dashboard/summary/: the tile and table numbers as JSON."""
    filters = Filters(request.GET)
    return JsonResponse(build_summary(load_rows(filters), filters))
