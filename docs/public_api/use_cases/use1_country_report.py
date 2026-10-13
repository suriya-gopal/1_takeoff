"""
Use case 1: a travel-trends report in plain Python.

Who would do this: a travel blogger or a student club that wants a quick weekly summary of where
TakeOff's community is heading, without logging in or touching the database.

What it does: downloads the public API, groups the destinations by country, and prints how many
community trips each country has, how many of its cities appear, and its average daily cost.

Run:  python use1_country_report.py
      python use1_country_report.py https://<username>.pythonanywhere.com/api/insights/destinations/
"""

import sys
from collections import defaultdict

import requests

API_URL = "https://suriya.pythonanywhere.com/api/insights/destinations/"


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else API_URL
    print(f"GET {url}")
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    rows = response.json()   # a list of {"destination", "country", "public_trips", "avg_daily_cost_usd"}
    print(f"HTTP {response.status_code}, {len(rows)} destinations received (no login needed)\n")

    # Group by country.
    countries = defaultdict(lambda: {"cities": [], "trips": 0, "costs": []})
    for row in rows:
        c = countries[row["country"]]
        c["cities"].append(row["destination"])
        c["trips"] += row["public_trips"]
        c["costs"].append(row["avg_daily_cost_usd"])

    ranking = sorted(countries.items(), key=lambda item: (-item[1]["trips"], item[0]))

    print(f"{'Country':<16}{'Trips':>6}{'Cities':>8}{'Avg $/day':>11}  Cities")
    print("-" * 70)
    for name, c in ranking:
        avg_cost = sum(c["costs"]) / len(c["costs"])
        print(f"{name:<16}{c['trips']:>6}{len(c['cities']):>8}{avg_cost:>11.2f}  {', '.join(c['cities'])}")
    print("-" * 70)

    total = sum(c["trips"] for c in countries.values())
    top_name, top = ranking[0]
    print(f"Total community trips: {total} across {len(countries)} countries")
    print(f"Most popular country: {top_name} ({top['trips']} trips, {top['trips'] / total:.0%} of all)")
    cheapest = min(rows, key=lambda r: r["avg_daily_cost_usd"])
    print(f"Cheapest destination: {cheapest['destination']}, {cheapest['country']} "
          f"(${cheapest['avg_daily_cost_usd']:.0f}/day)")


if __name__ == "__main__":
    main()
