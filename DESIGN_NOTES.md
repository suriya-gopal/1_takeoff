# TakeOff — Design Notes

Why the data model looks the way it does.

---

## 1. The decision that shaped everything: `TripStop`

The obvious first draft is `Trip → ItineraryItem`, with each item carrying a
day number and a city name. That falls apart the moment a user reorders their
route, which is a core interaction in this app:

- If Florence moves from day 6 to day 2, every item tagged "day 6" is now
  wrong, and there is no reliable way to know which of them moved with
  Florence and which belonged to the day itself.
- City would be a free-text string on every item, so "Florence", "florence"
  and "Firenze" would be three different places to the database.

So the model puts a stop between them:

```
Trip ──1:N── TripStop ──1:N── ItineraryItem
                 │
          FK → Destination
```

`TripStop` carries `position` (route order) and `nights` (length of stay).
Items attach to the *stop*, not to the trip and not to a bare day number.
Reordering then becomes a matter of rewriting `position` values — every item
follows its city for free, because it was never independently anchored.

This also gives the app the two numbers it needs everywhere else:
`position` drives the route screen, and `sum(nights)` per trip is what the
day-wise itinerary is generated from.

`Destination` is a separate table for the same reason: it is shared reference
data. Recommendations, "popular trips" and community search all group by
place, and that only works if every trip points at the same row.

---

## 2. `on_delete` choices

| Relationship | Choice | Reasoning |
|---|---|---|
| `Traveler.user` → `auth.User` | **CASCADE** | The profile is an extension of the account. A profile with no login behind it is orphaned data nobody can ever reach or fix. |
| `Traveler.home_city` → `Destination` | **SET_NULL** | Retiring a city from the catalog must never delete a person. The profile survives with an empty home city, which the UI can prompt them to reset. This is the one FK where losing the value is harmless. |
| `Trip.owner` → `Traveler` | **CASCADE** | A trip with no owner cannot be edited, posted, or joined. Deleting the account should take the itineraries with it — which is also the right answer for a data-deletion request. |
| `TripStop.trip` → `Trip` | **CASCADE** | A stop is a component of a trip, not an independent record. It has no meaning on its own. |
| `TripStop.destination` → `Destination` | **PROTECT** | This is the important one. Cities are shared, so deleting "Rome" would silently gut every live itinerary that visits it — and unlike the two above, the damage is spread across other people's data, not the deleter's own. PROTECT makes the database refuse and forces an admin to migrate or merge the city deliberately. |
| `ItineraryItem.stop` → `TripStop` | **CASCADE** | Drop a city from the route and the museum ticket chosen in that city goes with it. Keeping it would leave an item pointing at a place the trip no longer visits. |
| `JoinRequest.trip` / `.requester` | **CASCADE** on both | A request is meaningless if either the trip it targets or the person who made it is gone. |

The general rule applied: **CASCADE when the child is a part of the parent,
PROTECT when the parent is shared reference data, SET_NULL when the reference
is decorative and the row is fine without it.**

---

## 3. Why `JoinRequest` is a through model, not a plain M2M

`Trip.companions` is declared as a `ManyToManyField(Traveler,
through="JoinRequest")`, so `trip.companions.all()` reads naturally in code.
But the join row itself carries state the poster acts on:

- `status` — pending / accepted / declined. The poster controls acceptance,
  which is a product requirement, so the pairing needs a decision recorded
  on it.
- `message` — the intro note, so people can talk in-app before sharing
  personal details.
- `requested_at` — the poster's inbox is ordered newest-first.

A bare M2M table has room for none of that. Writing it as an explicit model
also means it can grow later (a `reviewed_at` timestamp, a decline reason)
without a schema migration that changes the relationship type.

---

## 4. Uniqueness constraints and what each one is actually for

Every constraint here corresponds to a real mistake a user or the UI can make:

- **`uniq_destination_per_trip`** — the drag-and-drop route builder makes it
  easy to drop the same city in twice. A return leg is modelled as a
  transport item, not as a second stay.
- **`uniq_stop_position_per_trip`** — reorder logic that writes positions in
  the wrong sequence would otherwise leave two cities in slot 3, and the route
  would render nondeterministically.
- **`uniq_item_per_stop_per_day`** — the classic mobile double-tap on "add".
- **`uniq_join_request_per_trip_per_traveler`** — stops someone spamming a
  poster. A second ask edits the existing row instead.
- **`uniq_destination_name_per_country`** — city names repeat worldwide, so
  neither `name` nor `country` is unique alone, but the pair must be.
- **`uniq_trip_title_per_owner_per_start`** — catches double submits on trip
  creation without blocking a user from running the same trip again next year,
  since the start date is part of the key.

These live at the database level rather than in form validation because the
app will eventually write to these tables from more than one place — the
importer, the "copy this community itinerary" flow, the seed script. Form
validation only protects the one path that goes through the form.

`trip_end_date_after_start_date` is a `CheckConstraint` rather than a unique
one: it enforces a relationship *between two columns of the same row*, which
uniqueness cannot express.

---

## 5. `Meta.ordering` choices

Each default ordering is the order that screen would actually display:

| Model | Ordering | Screen it serves |
|---|---|---|
| `Destination` | `country, name` | A grouped city picker |
| `Traveler` | `display_name` | Member lists, alphabetical |
| `Trip` | `start_date, title` | "My trips" — soonest departure first |
| `TripStop` | `trip, position` | The route, in travel order |
| `ItineraryItem` | `day_number, start_time, item_id` | The day-wise itinerary |
| `JoinRequest` | `-requested_at, requester` | The poster's inbox — newest first |

`ItineraryItem` falls back to `item_id` because `start_time` is nullable
(a hotel or a rental has no fixed clock time), and without a tiebreaker those
rows would come back in arbitrary order.

---

## 6. What is deliberately *not* modelled yet

Part 4 is the planning core. These are Phase 1+ and were left out on purpose
rather than stubbed:

- **Packing lists and reminders** — depends on weather and destination data
  from an external API; belongs in its own app.
- **Photo journal / memories** — needs file storage and EXIF location
  parsing, neither of which is a data-modeling concern yet.
- **Expense splitting** — needs a settled trip and real booked amounts, so it
  sits on top of `ItineraryItem.estimated_cost_usd` once booking status is
  reliable.
- **Reputation / star ratings** — meaningless until there are completed trips
  to rate.

`ItineraryItem.booking_status` already carries `partial`, and
`Trip.status` already carries `completed`, so the hooks those later features
need are in place without the features themselves.
