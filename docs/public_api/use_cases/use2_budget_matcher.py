"""
Use case 2: "Where can I go on my budget?" — a budget matcher.

Who would do this: a student-budget newsletter, a campus travel club's chatbot, or a partner site
that wants to suggest destinations. The public API gives every destination's average daily cost
and how many TakeOff trips go there, which is enough to answer the question.

What it does: takes a budget and a number of nights, estimates the cost of staying in each
destination (nights x average daily cost), keeps the ones that fit, and ranks them so that places
with the most community trips (= the best chance of finding travel companions) come first.

Run:  python use2_budget_matcher.py 1200 7
      python use2_budget_matcher.py 1200 7 https://<username>.pythonanywhere.com/api/insights/destinations/
"""

import sys

import requests

API_URL = "https://suriya.pythonanywhere.com/api/insights/destinations/"


def main():
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 1200
    nights = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    url = sys.argv[3] if len(sys.argv) > 3 else API_URL

    print(f"GET {url}")
    rows = requests.get(url, timeout=10).json()
    print(f"{len(rows)} destinations received\n")
    print(f"Budget: ${budget:,.0f} per person for {nights} nights (${budget / nights:,.0f} per day)\n")

    matches = []
    for row in rows:
        estimate = row["avg_daily_cost_usd"] * nights
        if estimate <= budget:
            matches.append({**row, "estimate": estimate, "left_over": budget - estimate})

    # Most community trips first (more people to travel with), then cheapest.
    matches.sort(key=lambda r: (-r["public_trips"], r["estimate"]))

    if not matches:
        print("No destination fits this budget. Try fewer nights or a bigger budget.")
        return

    print(f"{'#':<3}{'Destination':<14}{'Country':<16}{'Trips':>6}{'Estimate':>11}{'Left over':>11}")
    print("-" * 61)
    for i, r in enumerate(matches, 1):
        print(f"{i:<3}{r['destination']:<14}{r['country']:<16}{r['public_trips']:>6}"
              f"{r['estimate']:>11,.0f}{r['left_over']:>11,.0f}")
    print("-" * 61)
    print(f"{len(matches)} of {len(rows)} destinations fit the budget.")
    best = matches[0]
    print(f"Top pick: {best['destination']}, {best['country']}: {best['public_trips']} community "
          f"trip(s) to join, about ${best['estimate']:,.0f} for {nights} nights.")
    too_expensive = [r["destination"] for r in rows if r["avg_daily_cost_usd"] * nights > budget]
    if too_expensive:
        print(f"Over budget: {', '.join(too_expensive)}")


if __name__ == "__main__":
    main()
