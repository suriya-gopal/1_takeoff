"""Counts that match the trip lists, profile links, owner-only rules, packing ticks and added places."""

from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .factories import make_destination, make_traveler, make_trip
from .models import ItineraryItem, JoinRequest, PackingTick, Traveler, Trip
from .tests import TripDataTestCase


class CountsMatchListsTests(TripDataTestCase):
    """Every count shows the trips the viewer can open, the same set as the All trips page."""

    def counts(self):
        listed = len(self.client.get(reverse("trips:trip-list")).context["trips"])
        searched = self.client.get(reverse("trips:trip-search")).context["total_trips"]
        return listed, searched

    def test_other_member_sees_matching_counts(self):
        self.assertEqual(self.counts(), (2, 2))

    def test_owner_sees_matching_counts_including_own_private(self):
        self.client.force_login(self.alice.user)
        self.assertEqual(self.counts(), (3, 3))
        rows = {d.name: d for d in self.client.get(reverse("trips:trip-search")).context["trips_per_destination"]}
        self.assertEqual((rows["Lisbon"].n_trips, rows["Lisbon"].n_public), (1, 0))

    def test_private_trips_of_others_never_counted(self):
        names = [d.name for d in self.client.get(reverse("trips:home")).context["popular"]]
        self.assertNotIn("Lisbon", names)
        rows = [d.name for d in self.client.get(reverse("trips:insights")).context["rows"]]
        self.assertNotIn("Lisbon", rows)
        self.assertNotIn("Lisbon", self.client.get(reverse("trips:api-destinations-popular")).json()["labels"])

    def test_join_requests_count_only_visible_trips(self):
        self.assertEqual(self.client.get(reverse("trips:trip-search")).context["total_requests"], 0)


class ProfileTests(TripDataTestCase):
    def test_nav_has_profile_icon(self):
        page = self.client.get(reverse("trips:home"))
        self.assertContains(page, 'class="nav-profile"')
        self.assertContains(page, reverse("trips:my-profile"))

    def test_verified_member_gets_tick_on_icon_and_page(self):
        self.client.force_login(self.alice.user)
        page = self.client.get(reverse("trips:my-profile"))
        self.assertContains(page, "avatar-tick")
        self.assertContains(page, "Verified traveler")

    def test_profile_lists_my_trips_including_private(self):
        self.client.force_login(self.alice.user)
        page = self.client.get(reverse("trips:my-profile"))
        self.assertContains(page, "Italy loop")
        self.assertContains(page, "Secret Lisbon")

    def test_profile_lists_requests_both_ways(self):
        JoinRequest.objects.create(trip=self.public, requester=self.bob, message="Can I come?")
        bob_page = self.client.get(reverse("trips:my-profile"))            # signed in as Bob
        self.assertContains(bob_page, "Trips I asked to join")
        self.assertContains(bob_page, "Italy loop")
        self.assertContains(bob_page, "Not verified")
        self.client.force_login(self.alice.user)
        alice_page = self.client.get(reverse("trips:my-profile"))
        self.assertContains(alice_page, "Can I come?")
        self.assertEqual(alice_page.context["pending_count"], 1)

    def test_owner_name_shows_tick_without_link(self):
        page = self.client.get(self.public.get_absolute_url())
        self.assertContains(page, "verified-tick")
        self.assertNotContains(page, "traveler-link")

    def test_profile_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("trips:my-profile")).status_code, 302)


class JoinRequestsOnTripPageTests(TripDataTestCase):
    def setUp(self):
        super().setUp()
        self.carol = Traveler.objects.create(
            user=User.objects.create_user("carol", "carol@example.com", "pw"), display_name="Carol")
        JoinRequest.objects.create(trip=self.public, requester=self.carol, message="Hi from Carol")

    def test_other_member_sees_form_but_not_who_asked(self):
        page = self.client.get(self.public.get_absolute_url())             # Bob
        self.assertContains(page, "Request to join")
        self.assertNotContains(page, "Hi from Carol")
        self.assertNotContains(page, "Requests to join this trip")

    def test_owner_sees_requests_not_form_or_closed_note(self):
        self.client.force_login(self.alice.user)
        page = self.client.get(self.public.get_absolute_url())
        self.assertContains(page, "Requests to join this trip")
        self.assertContains(page, "Hi from Carol")
        self.assertNotContains(page, "<h3>Request to join</h3>")
        self.assertNotContains(page, "not open to join requests")

    def test_requester_sees_own_request_status_instead_of_form(self):
        self.client.force_login(self.carol.user)
        page = self.client.get(self.public.get_absolute_url())
        self.assertContains(page, "Your request to join")
        self.assertContains(page, "Pending")
        self.assertNotContains(page, "Hi from Carol")


ON = override_settings(AI_API_KEY="k", AI_API_MODEL="m")
PACKING = [{"item": "Rain jacket", "reason": "Showers likely"}, {"item": "Passport", "reason": "Needed"}]


class PackingTickTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = make_traveler("alice")
        self.trip = make_trip(self.owner, make_destination("Chicago", "USA"), nights=3)
        self.client.force_login(self.owner.user)
        self.tick_url = reverse("trips:packing-tick", args=[self.trip.pk])

    def tick(self, item, checked):
        return self.client.post(self.tick_url, {"item": item, "checked": "1" if checked else "0"})

    def test_tick_and_untick_are_saved(self):
        self.assertEqual(self.tick("Rain jacket", True).json()["ok"], True)
        self.assertTrue(PackingTick.objects.filter(trip=self.trip, item="Rain jacket").exists())
        self.tick("Rain jacket", True)                                   # ticking twice keeps one row
        self.assertEqual(PackingTick.objects.count(), 1)
        self.tick("Rain jacket", False)
        self.assertFalse(PackingTick.objects.exists())

    @ON
    def test_saved_ticks_are_shown_checked(self):
        self.tick("Passport", True)
        with mock.patch("trips.ai.suggestions.packing_list", return_value=PACKING):
            page = self.client.get(reverse("trips:packing-list", args=[self.trip.pk]))
        self.assertEqual([e["ticked"] for e in page.context["items"]], [False, True])
        self.assertContains(page, "saved automatically")

    def test_ticks_are_per_traveler(self):
        self.trip.visibility = Trip.PUBLIC
        self.trip.save()
        self.tick("Passport", True)
        self.client.force_login(make_traveler("bob").user)
        self.tick("Rain jacket", True)
        self.assertEqual(PackingTick.objects.count(), 2)
        self.assertEqual(PackingTick.objects.get(traveler__display_name="Bob").item, "Rain jacket")

    def test_empty_item_rejected(self):
        self.assertEqual(self.tick("   ", True).status_code, 400)

    def test_get_not_allowed_and_private_trip_hidden(self):
        self.assertEqual(self.client.get(self.tick_url).status_code, 405)
        self.client.force_login(make_traveler("bob").user)
        self.assertEqual(self.tick("Passport", True).status_code, 404)


PLACES = {"places": [
    {"name": "Art Institute", "why": "Famous collection.", "cost_usd": 32, "hidden_gem": False, "tags": ["museum"]},
    {"name": "Lakefront Trail", "why": "Free views.", "cost_usd": 0, "hidden_gem": True, "tags": ["walk"]},
]}


@ON
class AddedPlaceDisappearsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = make_traveler("alice")
        self.trip = make_trip(self.owner, make_destination("Chicago", "USA"), nights=3)
        self.stop = self.trip.stops.get()
        self.url = reverse("trips:place-suggestions", args=[self.trip.pk])
        self.client.force_login(self.owner.user)

    def test_added_place_is_no_longer_offered(self):
        with mock.patch("trips.ai.remote.chat_json", return_value=PLACES):
            self.client.post(self.url, {"stop": self.stop.pk, "category": "activity", "interests": ""})
        page = self.client.post(self.url, {"action": "add", "index": "0"})
        self.assertEqual(ItineraryItem.objects.count(), 1)
        self.assertNotContains(page, "Famous collection.")        # the added card is gone
        self.assertContains(page, "Lakefront Trail")              # the others stay
        self.assertContains(page, "Added to your itinerary")


class ApproveRejectTests(TripDataTestCase):
    """The owner approves or rejects requests; approval takes a seat and makes the requester a co-owner."""

    def setUp(self):
        super().setUp()
        self.join = JoinRequest.objects.create(trip=self.public, requester=self.bob, message="Hi")
        self.url = reverse("trips:decide-join-request", args=[self.public.pk, self.join.pk])

    def decide(self, decision, as_user=None):
        self.client.force_login((as_user or self.alice).user)
        return self.client.post(self.url, {"decision": decision})

    def test_owner_sees_buttons_on_trip_and_profile(self):
        self.client.force_login(self.alice.user)
        for url in (self.public.get_absolute_url(), reverse("trips:my-profile")):
            page = self.client.get(url)
            self.assertContains(page, 'value="approve"')
            self.assertContains(page, 'value="reject"')

    def test_approve_takes_a_seat_and_makes_co_owner(self):
        response = self.decide("approve")
        self.assertRedirects(response, self.public.get_absolute_url(), fetch_redirect_response=False)
        self.join.refresh_from_db(); self.public.refresh_from_db()
        self.assertEqual(self.join.status, JoinRequest.ACCEPTED)
        self.assertEqual(self.public.seats_open, 1)              # was 2
        self.assertIn(self.bob, self.public.co_owners())
        self.assertTrue(self.public.can_plan(self.bob))
        page = self.client.get(self.public.get_absolute_url())
        self.assertContains(page, "is now a co-owner")           # flash message after the redirect

    def test_reject_keeps_seats(self):
        self.decide("reject")
        self.join.refresh_from_db(); self.public.refresh_from_db()
        self.assertEqual((self.join.status, self.public.seats_open), (JoinRequest.DECLINED, 2))
        self.assertFalse(self.public.can_plan(self.bob))

    def test_cannot_decide_twice(self):
        self.decide("approve")
        self.decide("approve")
        self.public.refresh_from_db()
        self.assertEqual(self.public.seats_open, 1)              # the second approval did not take another seat

    def test_no_seats_left_blocks_approval(self):
        Trip.objects.filter(pk=self.public.pk).update(seats_open=0)
        self.decide("approve")
        self.join.refresh_from_db()
        self.assertEqual(self.join.status, JoinRequest.PENDING)
        page = self.client.get(self.public.get_absolute_url())
        self.assertContains(page, "No seats left")

    def test_only_owner_can_decide(self):
        carol = Traveler.objects.create(user=User.objects.create_user("carol", "c@example.com", "pw"), display_name="Carol")
        self.assertEqual(self.decide("approve", as_user=carol).status_code, 404)
        self.assertEqual(self.decide("approve", as_user=self.bob).status_code, 404)   # not even the requester
        self.join.refresh_from_db()
        self.assertEqual(self.join.status, JoinRequest.PENDING)

    def test_get_and_unknown_decision_rejected(self):
        self.client.force_login(self.alice.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.decide("maybe").status_code, 400)

    def test_next_must_be_on_this_site(self):
        self.client.force_login(self.alice.user)
        response = self.client.post(self.url, {"decision": "reject", "next": "https://evil.example.com/"})
        self.assertRedirects(response, self.public.get_absolute_url(), fetch_redirect_response=False)

    def test_co_owner_can_use_planning_tools_and_see_requests(self):
        self.decide("approve")
        self.client.force_login(self.bob.user)
        page = self.client.get(self.public.get_absolute_url())
        self.assertContains(page, "You are a co-owner")
        self.assertContains(page, reverse("trips:day-plan", args=[self.public.pk]))
        self.assertNotContains(page, 'value="approve"')          # the owner decides
        self.assertEqual(self.client.get(reverse("trips:day-plan", args=[self.public.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse("trips:my-profile")), "Trips I co-own")

    def test_co_owner_can_open_a_private_trip(self):
        JoinRequest.objects.create(trip=self.private, requester=self.bob, status=JoinRequest.ACCEPTED)
        self.client.force_login(self.bob.user)
        self.assertEqual(self.client.get(self.private.get_absolute_url()).status_code, 200)
        listed = [t.title for t in self.client.get(reverse("trips:trip-list")).context["trips"]]
        self.assertIn("Secret Lisbon", listed)
        self.assertEqual(self.client.get(reverse("trips:trip-search")).context["total_trips"], len(listed))

    def test_full_trip_shows_full_message_to_others(self):
        Trip.objects.filter(pk=self.public.pk).update(seats_open=0)
        carol = Traveler.objects.create(user=User.objects.create_user("carol", "c@example.com", "pw"), display_name="Carol")
        self.client.force_login(carol.user)
        self.assertContains(self.client.get(self.public.get_absolute_url()), "This trip is full")
