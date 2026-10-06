"""CSV and JSON downloads of public trips."""

import csv
import io
import json
import re
from datetime import date

from django.test import TestCase
from django.urls import reverse

from .factories import make_destination, make_traveler, make_trip
from .models import Trip


class ExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = make_traveler()
        rome = make_destination("Rome", "Italy")
        make_trip(owner, rome, "Italy loop", date(2026, 5, 1), visibility=Trip.PUBLIC, budget_min_usd=900, budget_max_usd=1500)
        make_trip(owner, rome, "=HYPERLINK(\"x\")", date(2026, 6, 1), visibility=Trip.PUBLIC)
        make_trip(owner, rome, "Secret", date(2026, 7, 1), visibility=Trip.PRIVATE)

    def test_csv_is_an_attachment_with_a_timestamped_name_and_header_row(self):
        response = self.client.get(reverse("trips:export-trips-csv"))
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertRegex(response["Content-Disposition"], r'^attachment; filename="trips_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.csv"$')
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0][:3], ["trip_id", "title", "status"])
        self.assertEqual(rows[1][1], "Italy loop")
        self.assertEqual(rows[1][7], "900.00")

    def test_csv_leaves_out_private_trips_and_defuses_formulas(self):
        body = self.client.get(reverse("trips:export-trips-csv")).content.decode()
        self.assertNotIn("Secret", body)
        self.assertIn("'=HYPERLINK", body)

    def test_json_has_metadata_and_the_same_records(self):
        response = self.client.get(reverse("trips:export-trips-json"))
        self.assertRegex(response["Content-Disposition"], r'filename="trips_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.json"')
        text = response.content.decode()
        self.assertIn("\n  ", text)  # indented
        data = json.loads(text)
        self.assertEqual(data["record_count"], 2)
        self.assertEqual(len(data["trips"]), 2)
        self.assertTrue(re.match(r"\d{4}-\d{2}-\d{2}T", data["generated_at"]))
        self.assertEqual(data["trips"][0]["route"], ["Rome"])

    def test_exports_are_read_only(self):
        self.assertEqual(self.client.post(reverse("trips:export-trips-csv")).status_code, 405)
        self.assertEqual(self.client.post(reverse("trips:export-trips-json")).status_code, 405)
