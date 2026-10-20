"""URL routes owned by the trips app."""

from django.contrib.auth.views import LogoutView
from django.urls import path

from . import accounts, budget, charts, exports, reports, views
from .ai import views as ai_views

app_name = "trips"

urlpatterns = [
    path("", views.home, name="home"),

    # Accounts: username/password login, signup and logout (logout accepts POST only)
    path("login/", accounts.TakeOffLoginView.as_view(), name="login"),
    path("signup/", accounts.SignUpView.as_view(), name="signup"),
    path("logout/", LogoutView.as_view(), name="logout"),

    # Trip pages
    path("trips/manual/", views.trip_manual_view, name="trip-manual"),
    path("trips/", views.trip_list_view, name="trip-list"),
    path("trips/generic/", views.TripListView.as_view(), name="trip-list-generic"),
    path("trips/<int:pk>/", views.TripDetailView.as_view(), name="trip-detail"),
    path("trips/<int:pk>/budget/", budget.trip_budget_page, name="trip-budget"),

    # Search and plan-a-trip form
    path("trips/search/", views.TripSearchView.as_view(), name="trip-search"),
    path("trips/<int:pk>/days/", ai_views.day_plan, name="day-plan"),
    path("trips/new/", views.TripCreateView.as_view(), name="trip-create"),

    # Insights: charts, their definitions and the chart image
    path("insights/", charts.insights_page, name="insights"),
    path("insights/specs/destinations.json", charts.destination_chart_json, name="chart-spec-destinations"),
    path("insights/specs/departures.json", charts.departure_chart_json, name="chart-spec-departures"),
    path("charts/trips-by-destination.png", views.trips_by_destination_chart, name="chart-trips-by-destination"),

    # Reports and downloads
    path("reports/", reports.ReportsView.as_view(), name="reports"),
    path("export/trips.csv", exports.export_trips_csv, name="export-trips-csv"),
    path("export/trips.json", exports.export_trips_json, name="export-trips-json"),

    # JSON API: trips and destinations
    path("api/trips/", views.api_trips, name="api-trips"),
    path("api/trips/<int:pk>/budget/", budget.api_trip_budget, name="api-trip-budget"),
    path("api/destinations/", views.DestinationsAPI.as_view(), name="api-destinations"),
    path("api/destinations/popular/", views.api_popular_destinations, name="api-destinations-popular"),

    # JSON API: chart feeds
    path("api/insights/destinations/", charts.api_destination_summary, name="api-insights-destinations"),
    path("api/insights/departures/", charts.api_monthly_departures, name="api-insights-departures"),

    # JSON API: health checks
    path("api/ping/json/", views.api_ping_jsonresponse, name="api-ping-json"),
    path("api/ping/http-manual-json/", views.api_ping_httpresponse_manual_json, name="api-ping-http-manual-json"),
    path("api/ping/http-default/", views.api_ping_httpresponse_default, name="api-ping-http-default"),
    path("api/ping/http-text/", views.api_ping_httpresponse_text, name="api-ping-http-text"),
]
