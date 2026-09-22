"""
Django Admin configuration for TakeOff.

Every model is registered so the data model can be validated by hand. The
inlines matter here: a trip is only understandable as a route, so stops are
edited inside the trip page and items inside the stop page, which also makes
the foreign key relationships visible without leaving the record.
"""

from django.contrib import admin

from .models import Destination, ItineraryItem, JoinRequest, Traveler, Trip, TripStop


class TripStopInline(admin.TabularInline):
    """Edit a trip's route (cities and their order) from the trip page."""

    model = TripStop
    extra = 1
    fields = ("position", "destination", "nights", "notes")
    ordering = ("position",)


class ItineraryItemInline(admin.TabularInline):
    """Edit the things chosen in a city directly from that stop."""

    model = ItineraryItem
    extra = 1
    fields = ("day_number", "start_time", "category", "title",
              "estimated_cost_usd", "booking_status", "is_hidden_gem")
    ordering = ("day_number", "start_time")


class JoinRequestInline(admin.TabularInline):
    """The poster's inbox of people asking to come along."""

    model = JoinRequest
    extra = 0
    fields = ("requester", "status", "message", "requested_at")
    readonly_fields = ("requested_at",)


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ("destination_id", "name", "country", "iata_code",
                    "avg_daily_cost_usd", "trip_count")
    search_fields = ("name", "country", "iata_code")
    list_filter = ("country",)
    ordering = ("country", "name")

    @admin.display(description="Used in trips")
    def trip_count(self, obj):
        """Shows the PROTECT relationship at a glance: non-zero means undeletable."""
        return obj.stops.count()


@admin.register(Traveler)
class TravelerAdmin(admin.ModelAdmin):
    list_display = ("traveler_id", "display_name", "user", "home_city",
                    "is_domain_verified", "joined_on")
    search_fields = ("display_name", "user__username", "user__email", "home_city__name")
    list_filter = ("is_domain_verified", "home_city__country")
    autocomplete_fields = ("home_city",)
    ordering = ("display_name",)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("trip_id", "title", "owner", "start_date", "end_date",
                    "visibility", "status", "seats_open", "stop_count")
    search_fields = ("title", "owner__display_name", "stops__destination__name")
    list_filter = ("visibility", "status", "start_date")
    date_hierarchy = "start_date"
    autocomplete_fields = ("owner",)
    inlines = [TripStopInline, JoinRequestInline]
    ordering = ("start_date",)

    @admin.display(description="Cities")
    def stop_count(self, obj):
        return obj.stops.count()


@admin.register(TripStop)
class TripStopAdmin(admin.ModelAdmin):
    list_display = ("stop_id", "trip", "position", "destination", "nights")
    search_fields = ("trip__title", "destination__name")
    list_filter = ("destination__country",)
    autocomplete_fields = ("trip", "destination")
    inlines = [ItineraryItemInline]
    ordering = ("trip", "position")


@admin.register(ItineraryItem)
class ItineraryItemAdmin(admin.ModelAdmin):
    list_display = ("item_id", "title", "category", "stop", "day_number",
                    "start_time", "estimated_cost_usd", "booking_status", "is_hidden_gem")
    search_fields = ("title", "stop__destination__name", "stop__trip__title")
    list_filter = ("category", "booking_status", "is_hidden_gem")
    autocomplete_fields = ("stop",)
    ordering = ("day_number", "start_time")


@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    list_display = ("request_id", "trip", "requester", "status", "requested_at")
    search_fields = ("trip__title", "requester__display_name")
    list_filter = ("status",)
    autocomplete_fields = ("trip", "requester")
    ordering = ("-requested_at",)
