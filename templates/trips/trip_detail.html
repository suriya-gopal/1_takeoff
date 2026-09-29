# TakeOff

A community-driven trip planning app built with Django. Users build a
multi-city itinerary, follow booking links out to third-party sites, and
optionally post the trip publicly so other travelers can ask to join.

---

## Naming

| Name | What it is | Why this name |
|---|---|---|
| `takeoff` | Django project (settings/URL container) | The product is a trip planner whose differentiator is finding trip *mates*. The project name names the product as a whole. |
| `trips` | Django app | The app owns one domain: a trip and everything hanging off it (route, itinerary items, join requests). |

---

## Features

- **Trip planning** — a trip is an ordered sequence of city stays
  (`TripStop`), each holding its own transport, hotel, activity, food and
  rental items (`ItineraryItem`).
- **Public/private trips** — a trip can stay private or be posted publicly
  so other travelers can request to join.
- **Community matching** — `JoinRequest` tracks pending/accepted/declined
  requests from other travelers to join a public trip.
- **Verified travelers** — accounts signing up with a `.edu` / company
  domain get a verified badge, so strangers feel comfortable joining each
  other's trips.
- **Django admin** — full CRUD over every model out of the box.

---

## Screenshots

**Home** — community trips and popular destinations
![Home page](docs/screenshots/home-page.png)

**Navigation bar** — every link is built with `{% url %}`
![Navigation](docs/screenshots/navigation.png)

**Trip detail** — opened from a trip card
![Trip detail page](docs/screenshots/trip-detail.png)

**Search** — forms and results at the top
![Search page](docs/screenshots/search-page.png)
![Filter search results](docs/screenshots/search-filter.png)
![Budget search results](docs/screenshots/search-budget.png)

**Styling** — custom CSS applied
![Styled page](docs/screenshots/styled-page.png)

**Chart** — trips per destination
![Chart](docs/screenshots/chart.png)

**Plan a trip** — validation and a saved trip
![Form validation](docs/screenshots/plan-trip-validation.png)
![Trip created](docs/screenshots/plan-trip-created.png)

**Request to join**
![Join request](docs/screenshots/request-to-join.png)

**JSON API**
![JSON output](docs/screenshots/api-json.png)

**Footer** — desktop and mobile
![Footer](docs/screenshots/footer.png)
![Footer on mobile](docs/screenshots/footer-mobile.png)

---

## Project structure

```
takeoff/
  ui-ux/static/css/    # normalize.css + style.css
  settings/
    base.py             # shared: INSTALLED_APPS, MIDDLEWARE, TEMPLATES, etc.
    development.py       # DEBUG = True, sqlite
    production.py        # DEBUG = False, DATABASE_URL / ALLOWED_HOSTS from env
  secrets_environment.py    # loads .env via django-environ
  urls.py
trips/
  forms.py               # TripForm (plan a trip), JoinRequestForm (request to join)
  models.py              # Destination, Traveler, Trip, TripStop, ItineraryItem, JoinRequest
  views.py                # pages, search, forms, chart, JSON API (FBV and CBV)
  urls.py
  static/trips/img/logo.png
templates/
  trips/
    base.html             # header (logo + "TakeOff"), nav, {% block content %}, footer
    home.html
    trip_list.html
    trip_list_manual.html
    trip_detail.html
    trip_search.html      # search forms, results, summaries
    trip_form.html        # plan a trip
    insights.html         # chart page
docs/
  wireframes/             # product wireframe deck
  notes/notes.txt          # running project notes
  screenshots/             # app screenshots used in this README
ER_Diagram/
  er_diagram.pdf
  er_diagram_chen.png
DESIGN_NOTES.md            # schema/design rationale
seed_data.py
```

---

## Views

| URL | View | Type |
|---|---|---|
| `/` | `home()` | FBV — landing page, preview of public community trips |
| `/trips/manual/` | `trip_manual_view` | FBV — manual `HttpResponse` via `loader.get_template()` |
| `/trips/` | `trip_list_view` | FBV — `render()` shortcut |
| `/trips/<pk>/` | `TripDetailView` | CBV — base `django.views.View` |
| `/trips/generic/` | `TripListView` | CBV — generic `ListView`, filtered to public trips |
| `/trips/search/` | `TripSearchView` | CBV — `ListView` that handles both the filter search and the budget search |
| `/trips/new/` | `TripCreateView` | CBV — `CreateView` for the "Plan your trip" form |
| `/insights/` | `insights()` | FBV — chart page |
| `/charts/trips-by-destination.png` | `trips_by_destination_chart()` | FBV — Matplotlib PNG |
| `/api/…` | see “JSON API” below | FBV + CBV JSON endpoints |
| `/admin/` | — | Django Admin |

`trip_list.html` is shared between the `render()` FBV and the generic
`ListView` — same template, two different ways of producing its context.

---

## Navigation and links

`/` is the home page. The header search and nav bar use `{% url %}` only (no
hard-coded paths). `Trip.get_absolute_url()` builds every link to a trip detail
page (`/trips/<pk>/`), so templates write `{{ trip.get_absolute_url }}`.

## Search (`/trips/search/`)

Two forms sit at the top of the page, with their results directly below.
The filter form searches public trips by destination, country, start date and
Planned/Completed tab; its choices go in the URL, so a search link can be shared.
The budget form finds open trips within a budget and group size and keeps the
budget out of the URL. Below the results are the full list of community trips
and summaries (totals, trips per destination, join requests per status).

## Styling

`takeoff/ui-ux/static/css/` holds `normalize.css` and the TakeOff `style.css`
(logo colours, header, cards, forms). Cache busting: a timestamp query string
in development and `ManifestStaticFilesStorage` (hashed file names) in production.

**Footer** (`base.html`, styled by `.footer-grid` in `style.css`): four columns —
a TakeOff blurb, Explore links, Get started links and Contact us (placeholder
address `xyz@takeoff.com`, Champaign, IL) — above a copyright line whose year
comes from `{% now "Y" %}`. The columns collapse to one on narrow screens. The
normalize.css MIT licence stays in that file's header comment.

## Chart (`/insights/`)

A stacked bar chart of public vs private trips per destination, computed from
the database and served as a PNG from `/charts/trips-by-destination.png`
(drawn in memory with `BytesIO`, nothing written to disk).

## Forms

- **Plan your trip** (`/trips/new/`): dates, budget range, group size, up to
  three ordered stops and a "looking for travel companions" checkbox. Ticking it
  posts the trip publicly. Includes `{% csrf_token %}` and friendly validation errors.
- **Request to join** (on each open public trip page): creates a join request.
- There is no login yet, so both forms ask who is acting from a dropdown.

## JSON API

Read-only, and only **public** trips are ever returned. Filters go in the
query string; a bad filter value returns a JSON `400` error.

| Endpoint | View | Filters |
|---|---|---|
| `/api/trips/` | function view `api_trips` | `q`, `country`, `status`, `max_budget`, `min_seats` |
| `/api/destinations/` | class view `DestinationsAPI` | `q`, `country` |
| `/api/destinations/popular/` | function view | — |
| `/api/ping/json/` | `JsonResponse` → `application/json` | — |
| `/api/ping/http-manual-json/` | `HttpResponse` + `json.dumps` → `application/json` | — |
| `/api/ping/http-default/` | `HttpResponse` → `text/html; charset=utf-8` | — |
| `/api/ping/http-text/` | `HttpResponse` → `text/plain` | — |

Example request: `/api/trips/?status=planned&max_budget=1500&min_seats=2`

```json
{"count": 1, "results": [{"trip_id": 51, "title": "Portugal on a student budget",
  "status": "planned", "start_date": "2026-03-07", "end_date": "2026-03-15", "nights": 8,
  "route": ["Lisbon", "Porto"], "budget_min_usd": 700.0, "budget_max_usd": 1100.0,
  "seats_open": 2, "owner": "Sahithi M.", "owner_verified": true, "url": "/trips/51/"}]}
```

**HttpResponse vs JsonResponse.** The four `/api/ping/…` URLs return the same
tiny message with different `Content-Type` headers (checked with `curl -i`):
`JsonResponse` sends `application/json` on its own; a plain `HttpResponse` is
labelled `text/html; charset=utf-8`, so clients would treat the JSON as a web
page; `HttpResponse(..., content_type="application/json")` fixes that by hand;
and `content_type="text/plain"` is read as plain text. `JsonResponse` is the
right tool for an API because it serialises the data and sets the header.

---

## Running it

```bash
git clone git@github.com:suriya-gopal/1_takeoff.git
cd 1_takeoff

python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # Django, django-environ, matplotlib

cp .env.example .env    # then replace the SECRET_KEY value with any random string

python manage.py migrate
python manage.py runserver
```

`db.sqlite3` ships with seeded data, so `migrate` + `runserver` is enough to
see the app working.

### Admin logins

| Username | Password |
|---|---|
| `mohitg2` | `uiuc12345` |
| `tester` | `uiuc12345` |

### Re-seeding from scratch

```bash
python manage.py shell < seed_data.py
```

Wipes the app tables, reloads all test data, then prints a constraint /
`on_delete` validation report.

### Running the automated tests

```bash
python manage.py test trips
```

Production static files: `DJANGO_SETTINGS_MODULE=takeoff.settings.production python manage.py collectstatic`.

---

## Configuration

Secrets (`SECRET_KEY`, any API keys) live in `.env` at the project root,
loaded through `takeoff/secrets_environment.py` via django-environ. `.env`
is gitignored. Nothing secret should ever land in `base.py`,
`development.py`, `production.py`, or git history.

---
