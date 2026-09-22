"""
Data model for TakeOff — a community-driven trip planning app.

The model is built around one central idea from the product design:
a Trip is an ordered sequence of city stays (TripStop), and everything a
user picks transport, hotels, activities, food, rentals, hangs off the
stop it belongs to. That is why TripStop sits between Trip and
ItineraryItem instead of items pointing straight at the Trip: when a user
drags a city into a new position, all of that city's items travel with it.
"""

from django.conf import settings
from django.db import models


class Destination(models.Model):
    """
    Represents a real-world city (or town) a user can travel to or from.

    This is the shared reference table for the whole app. Trips, stops and
    a traveler's home location all point at the same Destination row so that
    recommendations, "popular trips" and community search can be grouped by
    place instead of by free-text strings the user typed.
    """

    destination_id = models.AutoField(primary_key=True)

    name = models.CharField(max_length=80)                 # e.g. "Florence"
    country = models.CharField(max_length=60)              # e.g. "Italy"
    iata_code = models.CharField(
        max_length=3,
        blank=True,
        default="",
        help_text="Primary airport code, e.g. FLR. Blank if the city has no airport.",
    )
    timezone = models.CharField(max_length=40, default="UTC")
    avg_daily_cost_usd = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        help_text="Rough per-person daily spend, used to sanity-check trip budgets.",
    )

    class Meta:
        # Group cities by country, then alphabetically — how a picker would show them.
        ordering = ["country", "name"]
        constraints = [
            # "Springfield" exists in many countries, so neither field is unique
            # on its own, but the pair must be.
            models.UniqueConstraint(
                fields=["name", "country"],
                name="uniq_destination_name_per_country",
            )
        ]

    def __str__(self):
        return f"{self.name}, {self.country}"


class Traveler(models.Model):
    """
    Represents a user's public travel profile, extending Django's auth User.

    It exists separately from User because the login/account concern (password,
    email, permissions) is different from the social concern (display name, bio,
    home city, verified badge). The verified flag backs the design note about
    giving a tick to people who sign up with a .edu or company domain, which is
    what makes strangers comfortable joining each other's trips.
    """

    traveler_id = models.AutoField(primary_key=True)

    # ONE-TO-ONE: exactly one profile per account, and it dies with the account.
    # CASCADE is correct here — a profile with no login behind it is orphaned data.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="traveler",
    )

    display_name = models.CharField(max_length=60)
    bio = models.CharField(max_length=200, blank=True, default="")

    # SET_NULL: removing a city from the catalog must never delete a person.
    # The profile survives with an unset home city, which the UI can prompt to fix.
    home_city = models.ForeignKey(
        Destination,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="residents",
    )

    is_domain_verified = models.BooleanField(
        default=False,
        help_text="True when the account email is on a verified .edu / company domain.",
    )
    joined_on = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self):
        return f"{self.display_name}{' (verified)' if self.is_domain_verified else ''}"


class Trip(models.Model):
    """
    Represents one planned journey owned by a single traveler.

    A Trip holds the constraints the user gives on the trip-input screen:
    dates, budget range, group size, plus whether the trip is private or
    posted to the community for others to join. It is the parent record that
    stops and itinerary items are attached to.
    """

    PRIVATE = "private"
    PUBLIC = "public"
    VISIBILITY_CHOICES = [
        (PRIVATE, "Private (only me)"),
        (PUBLIC, "Public (open to join requests)"),
    ]

    DRAFT = "draft"
    PLANNED = "planned"
    COMPLETED = "completed"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (PLANNED, "Planned"),
        (COMPLETED, "Completed"),
    ]

    trip_id = models.AutoField(primary_key=True)

    # CASCADE: a trip has no meaning without its owner. If the account is
    # deleted the itinerary, its stops and its items should all disappear too.
    owner = models.ForeignKey(
        Traveler,
        on_delete=models.CASCADE,
        related_name="trips",
    )

    title = models.CharField(max_length=100)               # e.g. "Northern Italy by rail"
    start_date = models.DateField()
    end_date = models.DateField()

    budget_min_usd = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    budget_max_usd = models.DecimalField(max_digits=9, decimal_places=2, default=0)

    group_size = models.PositiveSmallIntegerField(default=1)
    seats_open = models.PositiveSmallIntegerField(
        default=0,
        help_text="How many companions the poster will still accept. 0 = closed.",
    )

    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default=PRIVATE)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    # MANY-TO-MANY through an explicit join model. Declared here so that
    # trip.companions.all() reads naturally, while JoinRequest still carries
    # the extra columns (status, message, timestamp) a plain M2M cannot hold.
    companions = models.ManyToManyField(
        Traveler,
        through="JoinRequest",
        related_name="joined_trips",
        blank=True,
    )

    class Meta:
        # Soonest departures first — what a "my trips" list should show.
        ordering = ["start_date", "title"]
        constraints = [
            # The same person should not create two identically named trips
            # leaving on the same day; that is almost always a double submit.
            models.UniqueConstraint(
                fields=["owner", "title", "start_date"],
                name="uniq_trip_title_per_owner_per_start",
            ),
            # Guards the date range at the database level, not just in forms.
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="trip_end_date_after_start_date",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.start_date} to {self.end_date})"

    @property
    def duration_nights(self):
        """Total nights the trip spans, used to check against nights per stop."""
        return (self.end_date - self.start_date).days


class TripStop(models.Model):
    """
    Represents one city stay inside a trip, at a fixed position in the route.

    This is the model behind the drag-to-reorder route screen: `position` is
    the order the cities are visited in and `nights` is how long the traveler
    stays. It exists as its own table because a trip visits many cities and a
    city appears in many trips, and each pairing needs its own order and
    length of stay.
    """

    stop_id = models.AutoField(primary_key=True)

    # CASCADE: stops are parts of a trip, not independent records.
    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name="stops",
    )

    # PROTECT: a Destination is shared reference data. Deleting "Rome" while
    # live itineraries point at it would silently gut people's trips, so the
    # database refuses and forces an admin to deal with it deliberately.
    destination = models.ForeignKey(
        Destination,
        on_delete=models.PROTECT,
        related_name="stops",
    )

    position = models.PositiveSmallIntegerField(
        help_text="1-based order of this city within the route.",
    )
    nights = models.PositiveSmallIntegerField(default=1)
    notes = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        # Route order is the only sensible default for a stop list.
        ordering = ["trip", "position"]
        constraints = [
            # Two cities cannot share slot 3 of the same trip.
            models.UniqueConstraint(
                fields=["trip", "position"],
                name="uniq_stop_position_per_trip",
            ),
            # And a trip cannot list the same city twice (a return leg is
            # modelled as transport, not as a duplicate stay).
            models.UniqueConstraint(
                fields=["trip", "destination"],
                name="uniq_destination_per_trip",
            ),
        ]

    def __str__(self):
        return f"{self.position}. {self.destination.name} ({self.nights}n)"


class ItineraryItem(models.Model):
    """
    Represents a single thing the traveler has chosen- a flight, a hotel
    night, a museum, a dinner, a scooter rental attached to one city stop.

    The category field is what powers the "levels" planning screen, where each
    category is browsed independently and in any order. Booking happens off
    platform, so the model stores a link and a status rather than a real
    reservation, including the partially-booked case.
    """

    TRANSPORT = "transport"
    HOTEL = "hotel"
    ACTIVITY = "activity"
    FOOD = "food"
    RENTAL = "rental"
    CATEGORY_CHOICES = [
        (TRANSPORT, "Transport"),
        (HOTEL, "Hotel / stay"),
        (ACTIVITY, "Place or activity"),
        (FOOD, "Food"),
        (RENTAL, "Rental"),
    ]

    NOT_BOOKED = "not_booked"
    PARTIAL = "partial"
    BOOKED = "booked"
    BOOKING_STATUS_CHOICES = [
        (NOT_BOOKED, "Not booked"),
        (PARTIAL, "Partially booked"),
        (BOOKED, "Booked"),
    ]

    item_id = models.AutoField(primary_key=True)

    # CASCADE: an item belongs to one stop. Remove the city from the route and
    # the museum ticket picked in that city goes with it.
    stop = models.ForeignKey(
        TripStop,
        on_delete=models.CASCADE,
        related_name="items",
    )

    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=120)               # e.g. "Uffizi Gallery"

    day_number = models.PositiveSmallIntegerField(
        help_text="Which day of the whole trip this falls on (day 1 = departure day).",
    )
    start_time = models.TimeField(null=True, blank=True)

    estimated_cost_usd = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    booking_url = models.URLField(blank=True, default="")
    booking_status = models.CharField(
        max_length=12,
        choices=BOOKING_STATUS_CHOICES,
        default=NOT_BOOKED,
    )
    is_hidden_gem = models.BooleanField(default=False)

    class Meta:
        # Day-wise itinerary order: by day, then by clock time within the day.
        ordering = ["day_number", "start_time", "item_id"]
        constraints = [
            # Stops the same activity being added twice to the same day of the
            # same city, which is the common double-tap mistake on mobile.
            models.UniqueConstraint(
                fields=["stop", "day_number", "title"],
                name="uniq_item_per_stop_per_day",
            )
        ]

    def __str__(self):
        return f"Day {self.day_number}: {self.title} [{self.get_category_display()}]"


class JoinRequest(models.Model):
    """
    Represents one traveler asking to join another traveler's public trip.

    This is the community-matching layer. It is a through table rather than a
    plain many-to-many because a request carries state the poster acts on:
    a message, an accept/decline decision, and when it was made.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (ACCEPTED, "Accepted"),
        (DECLINED, "Declined"),
    ]

    request_id = models.AutoField(primary_key=True)

    # CASCADE on both sides: a request is meaningless if either the trip it
    # points at or the person who made it no longer exists.
    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name="join_requests",
    )
    requester = models.ForeignKey(
        Traveler,
        on_delete=models.CASCADE,
        related_name="join_requests",
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    message = models.CharField(max_length=300, blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Newest requests first — this list is a poster's inbox.
        ordering = ["-requested_at", "requester"]
        constraints = [
            # One request per person per trip. Re-asking edits the existing row.
            models.UniqueConstraint(
                fields=["trip", "requester"],
                name="uniq_join_request_per_trip_per_traveler",
            )
        ]

    def __str__(self):
        return f"{self.requester.display_name} -> {self.trip.title} ({self.status})"
