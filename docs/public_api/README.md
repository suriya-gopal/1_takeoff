# TakeOff public API

**Endpoint:** `https://suriya.pythonanywhere.com/api/insights/destinations/`

The one API anyone can call without logging in. Every other API on the site answers
`401 {"error": "Authentication required…"}` until you log in.

It returns a plain JSON array built live from the database: one record per destination that public
community trips visit, most visited first.

```json
[
  {"destination": "Lisbon", "country": "Portugal", "public_trips": 2, "avg_daily_cost_usd": 95.0},
  {"destination": "Florence", "country": "Italy", "public_trips": 1, "avg_daily_cost_usd": 115.0}
]
```

| Field | Meaning |
|---|---|
| `destination` | City name |
| `country` | Country of the city |
| `public_trips` | How many public (community) trips visit the city |
| `avg_daily_cost_usd` | Typical per-person daily spend in the city, in US dollars |

**Why this one is safe to make public:** it only holds counts and averages from public trips. No
names, emails, budgets, join requests or private trips. The Vega editor
(`https://vega.github.io`) is allowed to read it cross-origin (django-cors-headers).

## Vega-Lite chart

`group-x-vega-lite-API-demo.txt` is the full Vega-Lite spec. Paste it into
https://vega.github.io/editor/ (mode: Vega-Lite). It loads its data with
`"data": {"url": "<public API URL>"}` (no inline data) and draws:

1. a bar chart of community trips per destination, coloured by country;
2. a scatter plot of average daily cost against community trips.

## Three other ways to use the same API

| # | File | Who / why |
|---|---|---|
| 1 | `use_cases/use1_country_report.py` | **Python script, trends report.** A travel blogger or student club downloads the API with `requests`, groups the destinations by country and prints trips, cities and average daily cost per country, plus the most popular country and cheapest city. Shows that the API can feed a weekly summary without any access to the site's database. |
| 2 | `use_cases/use2_budget_matcher.py` | **Python script, budget matcher.** Given a budget and a number of nights (`python use2_budget_matcher.py 1000 7`), it estimates the cost of each destination (nights × average daily cost), keeps the ones that fit and ranks them by how many community trips go there, so a traveler sees affordable places where they are most likely to find companions. The same logic could power a chatbot or a partner website. |
| 3 | `use_cases/use3_statistics.ipynb` | **Jupyter notebook, statistics.** pandas reads the API straight into a DataFrame (`pd.read_json(API_URL)`), then the notebook runs descriptive statistics, the Pearson and Spearman correlation between cost and popularity, a cost-tier summary and each country's share of trips. It ends by saving a CSV that opens in Excel or Google Sheets. |

Each script prints the URL it called, the data it received and the result, which is what the
screenshots show. Set `API_URL` at the top of each file to the production URL (or pass the URL as
the last command-line argument to the two scripts).

Requirements for the use cases: `pip install requests pandas jupyter`.
