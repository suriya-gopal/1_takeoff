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

    # Search
    path("trips/search/", views.TripSearchView.as_view(), name="trip-search"),

    # Chart page and PNG image
    path("insights/", views.insights, name="insights"),
    path("charts/trips-by-destination.png", views.trips_by_destination_chart, name="chart-trips-by-destination"),
]
