"""URL routes owned by the trips app."""

from django.urls import path

from . import views

app_name = "trips"

urlpatterns = [
    path("", views.home, name="home"),

    # Trip pages
    path("trips/manual/", views.trip_manual_view, name="trip-manual"),
    path("trips/", views.trip_list_view, name="trip-list"),
    path("trips/<int:pk>/", views.TripDetailView.as_view(), name="trip-detail"),
    path("trips/generic/", views.TripListView.as_view(), name="trip-list-generic"),

    # Search and plan-a-trip form
    path("trips/search/", views.TripSearchView.as_view(), name="trip-search"),
    path("trips/new/", views.TripCreateView.as_view(), name="trip-create"),

    # Chart page and PNG image
    path("insights/", views.insights, name="insights"),
    path("charts/trips-by-destination.png", views.trips_by_destination_chart, name="chart-trips-by-destination"),

    # JSON API
    path("api/ping/json/", views.api_ping_jsonresponse, name="api-ping-json"),
    path("api/ping/http-manual-json/", views.api_ping_httpresponse_manual_json, name="api-ping-http-manual-json"),
    path("api/ping/http-default/", views.api_ping_httpresponse_default, name="api-ping-http-default"),
    path("api/ping/http-text/", views.api_ping_httpresponse_text, name="api-ping-http-text"),
    path("api/trips/", views.api_trips, name="api-trips"),
    path("api/destinations/", views.DestinationsAPI.as_view(), name="api-destinations"),
    path("api/destinations/popular/", views.api_popular_destinations, name="api-destinations-popular"),
]
