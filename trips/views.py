"""
Homepage: a simple nav hub linking to the four Assignment 2 views.
"""

from django.http import HttpResponse
from django.shortcuts import render

from .models import Trip


def home(request):
    """Landing page — a preview of community-posted trips (Home/Landing wireframe, Screen 3)."""
    trips = (
        Trip.objects.filter(visibility=Trip.PUBLIC)
        .select_related("owner")
        .prefetch_related("stops__destination")[:6]
    )
    return render(request, "trips/home.html", {"trips": trips})


# ---------------------------------------------------------------------------
# Assignment 2
# ---------------------------------------------------------------------------
from django.template import loader
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import ListView


def trip_manual_view(request):
    """FBV 1 — HttpResponse (manual): load the template by hand."""
    trips = Trip.objects.filter(visibility=Trip.PUBLIC)
    template = loader.get_template('trips/trip_list_manual.html')
    context = {'trips': trips}
    return HttpResponse(template.render(context, request))


def trip_list_view(request):
    """FBV 2 — render() shortcut."""
    trips = (
        Trip.objects
        .select_related('owner')
        .prefetch_related('stops__destination')
    )
    return render(request, 'trips/trip_list.html', {'trips': trips})


class TripDetailView(View):
    """CBV 3 — base View, get() implemented manually."""

    def get(self, request, pk):
        trip = get_object_or_404(Trip, pk=pk)
        stops = trip.stops.all()
        join_requests = trip.join_requests.all()
        return render(
            request,
            'trips/trip_detail.html',
            {'trip': trip, 'stops': stops, 'join_requests': join_requests},
        )


class TripListView(ListView):
    """CBV 4 — generic ListView, reuses trip_list.html (shared with FBV 2)."""
    model = Trip
    template_name = 'trips/trip_list.html'
    context_object_name = 'trips'
    queryset = Trip.objects.filter(visibility=Trip.PUBLIC)

