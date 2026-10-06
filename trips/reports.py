"""Community report: grouped summaries of public trips with links to the downloadable exports."""

from django.db.models import Avg, Count, Q, Sum
from django.views.generic import TemplateView

from .models import Destination, JoinRequest, Trip


class ReportsView(TemplateView):
    """GET /reports/ — what the community has posted, summarised and ready to download."""

    template_name = "trips/reports.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        public = Trip.objects.filter(visibility=Trip.PUBLIC)
        public_stop = Q(stops__trip__visibility=Trip.PUBLIC)

        # Summary 1: where public trips go, split by whether they are still ahead or already taken.
        ctx["trips_per_destination"] = (
            Destination.objects
            .annotate(
                n_trips=Count("stops__trip", filter=public_stop, distinct=True),
                n_planned=Count(
                    "stops__trip", filter=public_stop & Q(stops__trip__status=Trip.PLANNED), distinct=True
                ),
                n_completed=Count(
                    "stops__trip", filter=public_stop & Q(stops__trip__status=Trip.COMPLETED), distinct=True
                ),
            )
            .filter(n_trips__gt=0)
            .order_by("-n_trips", "name")
        )

        # Summary 2: public trips by status, with the typical budget and open seats in each group.
        status_labels = dict(Trip.STATUS_CHOICES)
        ctx["trips_per_status"] = [
            {**row, "label": status_labels.get(row["status"], row["status"])}
            for row in (
                public.values("status")
                .annotate(
                    n_trips=Count("trip_id"),
                    avg_budget_min=Avg("budget_min_usd"),
                    avg_budget_max=Avg("budget_max_usd"),
                    seats_open=Sum("seats_open"),
                )
                .order_by("status")
            )
        ]

        # Summary 3: join requests on public trips by outcome.
        request_labels = dict(JoinRequest.STATUS_CHOICES)
        ctx["requests_per_status"] = [
            {**row, "label": request_labels.get(row["status"], row["status"])}
            for row in (
                JoinRequest.objects.filter(trip__visibility=Trip.PUBLIC)
                .values("status")
                .annotate(n_requests=Count("request_id"))
                .order_by("status")
            )
        ]

        # Totals line.
        ctx["total_trips"] = public.count()
        ctx["total_seats_open"] = public.aggregate(total=Sum("seats_open"))["total"] or 0
        ctx["total_requests"] = JoinRequest.objects.filter(trip__visibility=Trip.PUBLIC).count()
        ctx["total_destinations"] = Destination.objects.filter(
            stops__trip__visibility=Trip.PUBLIC
        ).distinct().count()
        return ctx
