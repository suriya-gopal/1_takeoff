# TakeOff — Part 4: Data Modeling & Admin Kickoff

A community-driven trip planning app. Users build a multi-city itinerary,
follow booking links out to third-party sites, and optionally post the trip
publicly so other travelers can ask to join.

---

## Naming

| Name | What it is | Why this name |
|---|---|---|
| `takeoff` | Django project (the settings/URL container) | The product is a trip planner whose differentiator is finding trip *mates*. The project name names the product as a whole. |
| `trips` | Django app | The app owns one domain: a trip and everything hanging off it (route, itinerary items, join requests). Plural, lowercase, matching Django's convention (`django.contrib.sessions`, `auth`). Later features that are genuinely separate concerns — packing lists, the photo journal — will become their own apps rather than being pushed into this one. |

---

## Running it

```bash
cd takeoff
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install django

python manage.py migrate
python manage.py runserver
```

Then open:

- `http://127.0.0.1:8000/` — plain-text list of public community trips with their routes
- `http://127.0.0.1:8000/admin/` — Django Admin

`db.sqlite3` is already at the project root with all test data loaded, so
migrate + runserver is enough. Nothing else needs to be run.

### Admin logins

| Username | Password | Note |
|---|---|---|
| `mohitg2` | `uiuc12345` | The superuser named in the assignment steps |
| `tester` | `uiuc12345` | The superuser named in the checklist |

Both are superusers; the assignment named a different one in each section, so
both exist.

### Re-seeding from scratch (optional)

```bash
python manage.py shell < seed_data.py
```

This wipes the app tables, reloads all test data, and then prints the
constraint / `on_delete` validation report described below.

### Running the automated checks

```bash
python manage.py test trips
```

Five tests, all passing. They assert the same rules the seed script
demonstrates, but in an isolated test database.

---

## Models at a glance

Six models, two features:

**Planning** — `Destination`, `Trip`, `TripStop`, `ItineraryItem`
**Community** — `Traveler`, `JoinRequest`

```
auth.User ──1:1── Traveler ──1:N── Trip ──1:N── TripStop ──1:N── ItineraryItem
                      │              │              │
                      │              └──1:N── JoinRequest
                      │                            │
                      └────────────1:N─────────────┘
Destination ──1:N── TripStop        (PROTECT)
Destination ──1:N── Traveler.home_city   (SET_NULL)
```

The shape that matters: **`TripStop` sits between `Trip` and `ItineraryItem`**
rather than items pointing straight at the trip. A trip is an ordered list of
city stays, and everything the user picks belongs to a city. When they drag a
city into a new position, its hotel, its restaurants and its museum tickets
move with it automatically, because they were never attached to a day number
in isolation. Full reasoning in `DESIGN_NOTES.md`.

---

## Requirement → where to find it

| Requirement | Where |
|---|---|
| Models with meaningful fields | `trips/models.py` |
| Docstring in every model class | `trips/models.py` — each class opens with one |
| ForeignKey | `Trip.owner`, `TripStop.trip`, `TripStop.destination`, `ItineraryItem.stop`, `JoinRequest.trip`, `JoinRequest.requester`, `Traveler.home_city` |
| OneToOneField | `Traveler.user` → `auth.User` |
| ManyToManyField | `Trip.companions` → `Traveler`, `through=JoinRequest` |
| Justified `on_delete` | CASCADE, PROTECT and SET_NULL all used; each is justified in an inline comment at the field, and in `DESIGN_NOTES.md` |
| `UniqueConstraint` (multi-field) | Six of them — see table below |
| `Meta.ordering` | Every model has one |
| Migrations run clean | `trips/migrations/0001_initial.py` |
| Admin registration | `trips/admin.py` — all six models, plus inlines |
| Superuser | `mohitg2` / `uiuc12345` |
| Test data | `seed_data.py`, already loaded into `db.sqlite3` |
| Uniqueness proof | `seed_data.py` validation section + `trips/tests.py` |
| `on_delete` proof | `seed_data.py` validation section + `trips/tests.py` |
| ER diagram | `docs/er_diagram.png` and `docs/er_diagram.pdf` |
| `db.sqlite3` at project root | yes |

---

## Constraints

| Constraint | Model | What it prevents |
|---|---|---|
| `uniq_destination_name_per_country` | Destination | Two "Springfield, United States" rows |
| `uniq_trip_title_per_owner_per_start` | Trip | One user double-submitting the same trip |
| `trip_end_date_after_start_date` | Trip | A trip that ends before it starts (CheckConstraint) |
| `uniq_stop_position_per_trip` | TripStop | Two cities in slot 3 of the same route |
| `uniq_destination_per_trip` | TripStop | The same city listed twice in one trip |
| `uniq_item_per_stop_per_day` | ItineraryItem | The same activity added twice to one day |
| `uniq_join_request_per_trip_per_traveler` | JoinRequest | Spamming the same trip with join requests |

---

## Test data loaded

| Table | Rows |
|---|---|
| Destination | 12 |
| Traveler | 6 |
| **Trip (primary model)** | **8** |
| TripStop | 15 |
| ItineraryItem | 18 |
| JoinRequest | 6 |

The 8 trips cover every state the app cares about: public and private,
draft / planned / completed, single-city and four-city routes, with and
without open seats. `Northern Italy by rail` (Milan → Venice → Florence →
Rome) is the fully worked example — 15 itinerary items spanning all five
categories and all three booking states, including partial bookings.

### Validation output from `seed_data.py`

Every rule below is deliberately broken, inside a rolled-back savepoint, so
the seeded data is left intact. `REFUSED` is the passing result:

```
REFUSED  duplicate city in one trip (uniq_destination_per_trip)
REFUSED  two cities at route position 1 (uniq_stop_position_per_trip)
REFUSED  second join request from the same traveler (uniq_join_request_...)
REFUSED  duplicate city name in one country (uniq_destination_name_per_country)
REFUSED  duplicate trip title on the same start date (uniq_trip_title_...)
REFUSED  trip ending before it starts (trip_end_date_after_start_date)
REFUSED  deleting Rome while trips still visit it (PROTECT)

CASCADE: deleting the Japan trip removed its 3 stops and 3 items;
         all 12 destinations survived.
SET_NULL: after deleting a city, the traveler's home_city became None
         and the profile still exists.
```

---

## References

- Django model field reference — https://docs.djangoproject.com/en/5.2/ref/models/fields/
- `UniqueConstraint` / `CheckConstraint` — https://docs.djangoproject.com/en/5.2/ref/models/constraints/
- `on_delete` options — https://docs.djangoproject.com/en/5.2/ref/models/fields/#django.db.models.ForeignKey.on_delete
- Many-to-many with a `through` model — https://docs.djangoproject.com/en/5.2/topics/db/models/#extra-fields-on-many-to-many-relationships
- Admin inlines — https://docs.djangoproject.com/en/5.2/ref/contrib/admin/#inlinemodeladmin-objects

Built and tested on Django 6.1 / Python 3.12. The course examples target
Django 5.2; the only version-sensitive line is `CheckConstraint(condition=...)`,
which was named `check=` before Django 5.1. If you run this on 5.0 or older,
rename that one keyword in `trips/models.py` and in the migration.
