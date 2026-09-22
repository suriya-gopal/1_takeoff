"""URL routes owned by the trips app."""

from django.urls import path

from . import views

app_name = "trips"

urlpatterns = [
    path("", views.home, name="home"),

    # Assignment 2, Section 2 — the four required views
    path("trips/manual/", views.trip_manual_view, name="trip-manual"),
    path("trips/", views.trip_list_view, name="trip-list"),
    path("trips/<int:pk>/", views.TripDetailView.as_view(), name="trip-detail"),
    path("trips/generic/", views.TripListView.as_view(), name="trip-list-generic"),
]
