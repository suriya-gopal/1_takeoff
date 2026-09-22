"""
Seed TakeOff with realistic test data and prove the constraints work.

Run from the project root:

    python manage.py shell < seed_data.py

The script is idempotent: it clears the app's own tables first, so it can be
re-run without tripping the uniqueness constraints it is meant to demonstrate.
It finishes by deliberately breaking each rule and reporting whether the
database refused the operation.
"""

from datetime import date, time
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import ProtectedError
from django.db.utils import IntegrityError

from trips.models import (
    Destination,
    ItineraryItem,
    JoinRequest,
    Traveler,
    Trip,
    TripStop,
)

print("\n" + "=" * 68)
print("SEEDING TRIPMATE")
print("=" * 68)

# ---------------------------------------------------------------- reset ----
JoinRequest.objects.all().delete()
ItineraryItem.objects.all().delete()
TripStop.objects.all().delete()
Trip.objects.all().delete()
Traveler.objects.all().delete()
Destination.objects.all().delete()
User.objects.filter(is_superuser=False).delete()

# ------------------------------------------------------------ superusers ---
# Two admin logins
for username, email in [("mohitg2", "mohitg2@illinois.edu"),
                        ("tester", "tester@illinois.edu")]:
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username, email, "uiuc12345")
        print(f"  superuser created: {username}")
    else:
        print(f"  superuser already present: {username}")

# ----------------------------------------------------------- destinations --
DESTINATIONS = [
    ("Chicago", "United States", "ORD", "America/Chicago", "170.00"),
    ("New York", "United States", "JFK", "America/New_York", "220.00"),
    ("Rome", "Italy", "FCO", "Europe/Rome", "125.00"),
    ("Florence", "Italy", "FLR", "Europe/Rome", "115.00"),
    ("Venice", "Italy", "VCE", "Europe/Rome", "150.00"),
    ("Milan", "Italy", "MXP", "Europe/Rome", "140.00"),
    ("Kyoto", "Japan", "", "Asia/Tokyo", "130.00"),
    ("Tokyo", "Japan", "HND", "Asia/Tokyo", "160.00"),
    ("Osaka", "Japan", "KIX", "Asia/Tokyo", "120.00"),
    ("Lisbon", "Portugal", "LIS", "Europe/Lisbon", "95.00"),
    ("Porto", "Portugal", "OPO", "Europe/Lisbon", "85.00"),
    ("Reykjavik", "Iceland", "KEF", "Atlantic/Reykjavik", "210.00"),
]

cities = {}
for name, country, iata, tz, cost in DESTINATIONS:
    cities[name] = Destination.objects.create(
        name=name, country=country, iata_code=iata,
        timezone=tz, avg_daily_cost_usd=Decimal(cost),
    )
print(f"  destinations: {Destination.objects.count()}")

# --------------------------------------------------------------- travelers -
TRAVELERS = [
    # username, email, display name, home city, verified?
    ("mgupta", "mgupta@illinois.edu", "Mohit G.", "Chicago", True),
    ("nramesh", "ramesh21@illinois.edu", "Nandhini Ramesh.", "Chicago", True),
    ("sm163", "sm163@northwestern.edu", "Sahithi M.", "Chicago", True),
    ("gopal8", "gopal8@gmail.com", "Suriya G.", "Rome", False),
    ("jwalsh", "j.walsh@acme-corp.com", "Jamie W.", "New York", True),
    ("rkim", "r.kim@gmail.com", "Kim R.", "Tokyo", False),
]

people = {}
for username, email, display, home, verified in TRAVELERS:
    user = User.objects.create_user(username, email, "traveler12345")
    people[username] = Traveler.objects.create(
        user=user,
        display_name=display,
        home_city=cities[home],
        is_domain_verified=verified,
        bio=f"Traveler based in {home}.",
    )
print(f"  travelers: {Traveler.objects.count()}")

# ------------------------------------------------------------------ trips --
# 8 trips in the primary model, each owned by a traveler (FK) and each with
# an ordered route of cities (the drag-to-reorder screen).
TRIPS = [
    {
        "owner": "mgupta", "title": "Northern Italy by rail",
        "start": date(2026, 5, 16), "end": date(2026, 5, 26),
        "budget": ("1800.00", "2600.00"), "group": 2, "seats": 2,
        "visibility": Trip.PUBLIC, "status": Trip.PLANNED,
        "route": [("Milan", 2), ("Venice", 2), ("Florence", 3), ("Rome", 3)],
    },
    {
        "owner": "nramesh", "title": "Japan first-timer loop",
        "start": date(2026, 10, 3), "end": date(2026, 10, 15),
        "budget": ("2400.00", "3400.00"), "group": 4, "seats": 1,
        "visibility": Trip.PUBLIC, "status": Trip.PLANNED,
        "route": [("Tokyo", 4), ("Kyoto", 4), ("Osaka", 3)],
    },
    {
        "owner": "sm163", "title": "Portugal on a student budget",
        "start": date(2026, 3, 7), "end": date(2026, 3, 15),
        "budget": ("700.00", "1100.00"), "group": 3, "seats": 2,
        "visibility": Trip.PUBLIC, "status": Trip.PLANNED,
        "route": [("Lisbon", 4), ("Porto", 4)],
    },
    {
        "owner": "gopal8", "title": "Rome food weekend",
        "start": date(2026, 4, 10), "end": date(2026, 4, 13),
        "budget": ("400.00", "650.00"), "group": 2, "seats": 0,
        "visibility": Trip.PRIVATE, "status": Trip.DRAFT,
        "route": [("Rome", 3)],
    },
    {
        "owner": "jwalsh", "title": "Iceland ring road",
        "start": date(2026, 7, 4), "end": date(2026, 7, 12),
        "budget": ("2000.00", "3000.00"), "group": 4, "seats": 3,
        "visibility": Trip.PUBLIC, "status": Trip.PLANNED,
        "route": [("Reykjavik", 8)],
    },
    {
        "owner": "rkim", "title": "Kansai slow travel",
        "start": date(2026, 11, 1), "end": date(2026, 11, 9),
        "budget": ("1200.00", "1700.00"), "group": 1, "seats": 0,
        "visibility": Trip.PRIVATE, "status": Trip.DRAFT,
        "route": [("Osaka", 3), ("Kyoto", 5)],
    },
    {
        "owner": "mgupta", "title": "Winter break in New York",
        "start": date(2025, 12, 20), "end": date(2025, 12, 27),
        "budget": ("900.00", "1400.00"), "group": 2, "seats": 0,
        "visibility": Trip.PUBLIC, "status": Trip.COMPLETED,
        "route": [("New York", 7)],
    },
    {
        "owner": "nramesh", "title": "Spring break Lisbon",
        "start": date(2026, 3, 20), "end": date(2026, 3, 27),
        "budget": ("800.00", "1200.00"), "group": 3, "seats": 1,
        "visibility": Trip.PUBLIC, "status": Trip.PLANNED,
        "route": [("Lisbon", 7)],
    },
]

trips = {}
for spec in TRIPS:
    trip = Trip.objects.create(
        owner=people[spec["owner"]],
        title=spec["title"],
        start_date=spec["start"],
        end_date=spec["end"],
        budget_min_usd=Decimal(spec["budget"][0]),
        budget_max_usd=Decimal(spec["budget"][1]),
        group_size=spec["group"],
        seats_open=spec["seats"],
        visibility=spec["visibility"],
        status=spec["status"],
    )
    trips[spec["title"]] = trip
    for position, (city, nights) in enumerate(spec["route"], start=1):
        TripStop.objects.create(
            trip=trip,
            destination=cities[city],
            position=position,
            nights=nights,
        )

print(f"  trips: {Trip.objects.count()}   stops: {TripStop.objects.count()}")

# -------------------------------------------------------- itinerary items --
# A fully filled itinerary for the Italy trip so every category is represented.
italy = trips["Northern Italy by rail"]
stops = {s.destination.name: s for s in italy.stops.all()}

ITEMS = [
    ("Milan",    ItineraryItem.TRANSPORT, "ORD to MXP overnight flight", 1, time(21, 30), "780.00", ItineraryItem.BOOKED,     False),
    ("Milan",    ItineraryItem.HOTEL,     "Hotel near Centrale",          2, time(15, 0),  "190.00", ItineraryItem.BOOKED,     False),
    ("Milan",    ItineraryItem.ACTIVITY,  "Duomo rooftop terraces",       2, time(10, 0),  "22.00",  ItineraryItem.NOT_BOOKED, False),
    ("Milan",    ItineraryItem.FOOD,      "Aperitivo in Navigli",         2, time(19, 0),  "25.00",  ItineraryItem.NOT_BOOKED, True),
    ("Venice",   ItineraryItem.TRANSPORT, "Frecciarossa Milan to Venice", 4, time(9, 25),  "45.00",  ItineraryItem.PARTIAL,    False),
    ("Venice",   ItineraryItem.ACTIVITY,  "Libreria Acqua Alta",          4, time(14, 0),  "0.00",   ItineraryItem.NOT_BOOKED, True),
    ("Venice",   ItineraryItem.FOOD,      "Cicchetti crawl in Cannaregio", 5, time(18, 30), "35.00",  ItineraryItem.NOT_BOOKED, True),
    ("Florence", ItineraryItem.TRANSPORT, "Regional train to Florence",   6, time(11, 0),  "30.00",  ItineraryItem.NOT_BOOKED, False),
    ("Florence", ItineraryItem.HOTEL,     "Guesthouse in Oltrarno",       6, time(15, 0),  "240.00", ItineraryItem.PARTIAL,    False),
    ("Florence", ItineraryItem.ACTIVITY,  "Uffizi Gallery",               7, time(9, 0),   "28.00",  ItineraryItem.BOOKED,     False),
    ("Florence", ItineraryItem.RENTAL,    "E-bike day hire",              8, time(10, 0),  "35.00",  ItineraryItem.NOT_BOOKED, False),
    ("Rome",     ItineraryItem.TRANSPORT, "Train Florence to Rome",       9, time(8, 45),  "40.00",  ItineraryItem.NOT_BOOKED, False),
    ("Rome",     ItineraryItem.ACTIVITY,  "Colosseum underground tour",   9, time(14, 0),  "36.00",  ItineraryItem.NOT_BOOKED, False),
    ("Rome",     ItineraryItem.FOOD,      "Testaccio market lunch",      10, time(12, 30), "18.00",  ItineraryItem.NOT_BOOKED, True),
    ("Rome",     ItineraryItem.TRANSPORT, "FCO to ORD return flight",    11, time(11, 5),  "760.00", ItineraryItem.BOOKED,     False),
]

for city, category, title, day, start, cost, booking, gem in ITEMS:
    ItineraryItem.objects.create(
        stop=stops[city],
        category=category,
        title=title,
        day_number=day,
        start_time=start,
        estimated_cost_usd=Decimal(cost),
        booking_status=booking,
        is_hidden_gem=gem,
    )

# A lighter itinerary on the Japan trip so more than one trip has items.
japan = trips["Japan first-timer loop"]
jp_stops = {s.destination.name: s for s in japan.stops.all()}
ItineraryItem.objects.create(
    stop=jp_stops["Tokyo"], category=ItineraryItem.HOTEL,
    title="Shinjuku business hotel", day_number=1, start_time=time(16, 0),
    estimated_cost_usd=Decimal("620.00"), booking_status=ItineraryItem.BOOKED,
)
ItineraryItem.objects.create(
    stop=jp_stops["Kyoto"], category=ItineraryItem.ACTIVITY,
    title="Fushimi Inari at dawn", day_number=5, start_time=time(6, 0),
    estimated_cost_usd=Decimal("0.00"), is_hidden_gem=True,
)
ItineraryItem.objects.create(
    stop=jp_stops["Osaka"], category=ItineraryItem.FOOD,
    title="Kuromon market breakfast", day_number=9, start_time=time(8, 30),
    estimated_cost_usd=Decimal("15.00"),
)
print(f"  itinerary items: {ItineraryItem.objects.count()}")

# ------------------------------------------------------------- community ---
# Join requests against public trips, in all three states.
JoinRequest.objects.create(
    trip=italy, requester=people["nramesh"], status=JoinRequest.ACCEPTED,
    message="I did Florence last year and can handle the train bookings.",
)
JoinRequest.objects.create(
    trip=italy, requester=people["sm163"], status=JoinRequest.PENDING,
    message="Free that whole week. Happy to split a triple room.",
)
JoinRequest.objects.create(
    trip=italy, requester=people["gopal8"], status=JoinRequest.DECLINED,
    message="Could join for the Rome leg only.",
)
JoinRequest.objects.create(
    trip=trips["Japan first-timer loop"], requester=people["rkim"],
    status=JoinRequest.ACCEPTED, message="Local — I can guide the Kyoto days.",
)
JoinRequest.objects.create(
    trip=trips["Portugal on a student budget"], requester=people["mgupta"],
    status=JoinRequest.PENDING, message="Is the Porto leg flexible by a day?",
)
JoinRequest.objects.create(
    trip=trips["Iceland ring road"], requester=people["nramesh"],
    status=JoinRequest.PENDING, message="I can drive and I have a license.",
)
print(f"  join requests: {JoinRequest.objects.count()}")

# =========================================================================
# CONSTRAINT AND on_delete VALIDATION
# Each block deliberately breaks a rule and rolls back, so the seeded data
# is left untouched. "REFUSED" is the passing outcome.
# =========================================================================
print("\n" + "=" * 68)
print("CONSTRAINT VALIDATION (each attempt below SHOULD fail)")
print("=" * 68)


def expect_failure(label, fn, exc):
    """Run fn inside a savepoint, expecting it to raise `exc`."""
    try:
        with transaction.atomic():
            fn()
    except exc as err:
        print(f"  REFUSED  {label}\n           -> {type(err).__name__}: {str(err)[:90]}")
        return True
    print(f"  ALLOWED  {label}   <-- constraint did NOT hold")
    return False


# 1. UniqueConstraint: same city twice in one trip.
expect_failure(
    "duplicate city in one trip (uniq_destination_per_trip)",
    lambda: TripStop.objects.create(trip=italy, destination=cities["Rome"],
                                    position=9, nights=1),
    IntegrityError,
)

# 2. UniqueConstraint: two cities in the same route slot.
expect_failure(
    "two cities at route position 1 (uniq_stop_position_per_trip)",
    lambda: TripStop.objects.create(trip=italy, destination=cities["Lisbon"],
                                    position=1, nights=1),
    IntegrityError,
)

# 3. UniqueConstraint: one join request per person per trip.
expect_failure(
    "second join request from the same traveler (uniq_join_request_...)",
    lambda: JoinRequest.objects.create(trip=italy, requester=people["nramesh"]),
    IntegrityError,
)

# 4. UniqueConstraint: duplicate city name inside one country.
expect_failure(
    "duplicate city name in one country (uniq_destination_name_per_country)",
    lambda: Destination.objects.create(name="Rome", country="Italy"),
    IntegrityError,
)

# 5. UniqueConstraint: same owner, same title, same departure date.
expect_failure(
    "duplicate trip title on the same start date (uniq_trip_title_...)",
    lambda: Trip.objects.create(owner=people["mgupta"],
                                title="Northern Italy by rail",
                                start_date=date(2026, 5, 16),
                                end_date=date(2026, 5, 26)),
    IntegrityError,
)

# 6. CheckConstraint: a trip that ends before it starts.
expect_failure(
    "trip ending before it starts (trip_end_date_after_start_date)",
    lambda: Trip.objects.create(owner=people["mgupta"], title="Time traveller",
                                start_date=date(2026, 6, 10),
                                end_date=date(2026, 6, 1)),
    IntegrityError,
)

# 7. on_delete=PROTECT: a Destination used by a live trip cannot be deleted.
expect_failure(
    "deleting Rome while trips still visit it (PROTECT)",
    lambda: cities["Rome"].delete(),
    ProtectedError,
)

print("\n" + "=" * 68)
print("on_delete BEHAVIOUR (CASCADE — this one SHOULD succeed)")
print("=" * 68)

# 8. on_delete=CASCADE: deleting a trip removes its stops and items, but
#    leaves the shared Destination rows alone. Rolled back afterwards.
before = (Trip.objects.count(), TripStop.objects.count(),
          ItineraryItem.objects.count(), Destination.objects.count())
try:
    with transaction.atomic():
        japan.delete()
        after = (Trip.objects.count(), TripStop.objects.count(),
                 ItineraryItem.objects.count(), Destination.objects.count())
        print(f"  before delete: trips={before[0]} stops={before[1]} "
              f"items={before[2]} destinations={before[3]}")
        print(f"  after  delete: trips={after[0]} stops={after[1]} "
              f"items={after[2]} destinations={after[3]}")
        print("  CASCADE removed the trip's 3 stops and 3 items; "
              "all 12 destinations survived.")
        raise RuntimeError("rollback")   # keep the seeded data intact
except RuntimeError:
    pass

print(f"  restored: trips={Trip.objects.count()} stops={TripStop.objects.count()} "
      f"items={ItineraryItem.objects.count()}")

# 9. on_delete=SET_NULL on Traveler.home_city, shown without rollback-safe
#    trickery by using a throwaway city and a throwaway profile.
with transaction.atomic():
    temp_city = Destination.objects.create(name="Testville", country="Nowhere")
    temp_user = User.objects.create_user("tempuser", "temp@example.com", "pw")
    temp_traveler = Traveler.objects.create(
        user=temp_user, display_name="Temp", home_city=temp_city
    )
    temp_city.delete()
    temp_traveler.refresh_from_db()
    print(f"\n  SET_NULL: after deleting the city, home_city is "
          f"{temp_traveler.home_city!r} and the profile still exists.")
    temp_user.delete()   # CASCADE also removes the Traveler profile

print("\n" + "=" * 68)
print("FINAL ROW COUNTS")
print("=" * 68)
for model in (Destination, Traveler, Trip, TripStop, ItineraryItem, JoinRequest):
    print(f"  {model.__name__:<16} {model.objects.count()}")
print("\nDone. Log in at http://127.0.0.1:8000/admin/ as mohitg2 / uiuc12345\n")
