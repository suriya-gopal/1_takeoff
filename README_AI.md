# AI day-by-day drafts

TakeOff can draft a day-by-day outline for a trip. A small language model, **SmolLM2-1.7B-Instruct**, runs
inside the Django server (no outside service involved) and suggests a morning, afternoon and evening for
each day in each city of the route. Members review the draft and save what they like as itinerary items.

Open a trip you own and choose **Draft my days** (`/trips/<id>/days/`).

## How it works

1. The member optionally describes their interests and ticks "Traveling with kids".
2. For each stop on the route the server asks the model for one plan covering that stop's nights (up to 5 days per stop).
3. The reply is checked. If it is unusable the server retries (up to 3 attempts, the later ones with a little randomness).
4. The draft is shown for review. Nothing is stored until the member presses **Save to my itinerary**, which creates
   normal itinerary items at 09:00, 14:00 and 19:00 for each day.

## Data Input

- **Chosen by the member:** a short free-text "What are you into?" and a "Traveling with kids" checkbox.
- **Taken from the trip itself:** each city name and its number of nights (from the route stops) and the trip budget.
  The member never types a city, so the city text always comes from our own destination list.
- Only the trip's owner can open the page. Drafts are held in the member's session until saved.

## Preprocessing

Before anything reaches the model the server:

- normalises the interests text (Unicode normalisation, removes control characters, braces, quotes, backticks and
  angle brackets, collapses spaces) and trims it to 200 characters;
- turns the trip budget into a band (`low` under $100 per person per night, `moderate` under $250, otherwise `high`);
- adds "traveling with kids" to the interests when ticked, because small models respond better when this is stated
  as part of the request;
- builds one chat prompt: strict output rules, three worked examples (one of them a trip with kids), then the real
  request in the same one-line form as the examples. Worked examples were what kept the small model on the
  required JSON format in testing.

## Safety Guardrails

| Risk | What the server does |
|---|---|
| Text that tries to redirect the model ("ignore previous instructions", asking for keys or passwords) | Interests containing such phrases are rejected with a friendly message and never sent to the model |
| Oversized or odd input | Hard length limits, symbol stripping, and only the interests field is free text |
| Broken or off-format output | The JSON is extracted from the reply, then checked: right number of days, and a non-empty morning, afternoon and evening for each. Anything else is discarded |
| Over-long text in the output | Each item is trimmed to 120 characters before it is shown or stored |
| Failure after retries | The member sees a clear message and can try again; nothing is saved |
| Tampering with a saved draft | The draft lives on the server (session), not in the page, and is re-validated against the trip's own stops on save |
| Hanging requests | Generation has a time limit (`AI_LOCAL_TIMEOUT_SECONDS`) and runs one request at a time |
| Overuse | Each member gets `AI_DRAFTS_PER_HOUR` drafts per hour (default 10) |
| Model not available | If the model is switched off or cannot load, the page says so instead of failing |

Known limit: a small model can invent plausible place names. Drafts are suggestions for the member to check,
not bookings.

## Hosted assistant: place suggestions, packing list and place check

A second AI service, called over the internet, adds three features. It is optional: with no key set, these
pages say they are not set up and everything else works.

- **Find places** (`/trips/<id>/places/`, owner only): six ideas for things to do or eat in one city of the trip, with a
  reason, a typical cost, a "hidden gem" flag and tags. Filter to free or hidden-gem places, then **+ Add** puts one on
  the itinerary at the start of that city's stay with no time set, ready to schedule later.
- **Packing list** (`/trips/<id>/packing/`): a checklist built from the route, dates, typical weather for that time of
  year and the planned items. Identical requests are reused for six hours.
- **Place check on drafts**: after the on-device model writes a draft, the hosted service reads it once per city and
  says which places are real. Real places stay, a made-up one is replaced when a real alternative is offered, and
  anything unconfirmed is marked. If the service is unavailable the draft still appears, labelled as unchecked.

**Data input:** city names, nights, dates, budget and group size come from the trip; the member adds only the short
interests text. Titles of items already on the itinerary are included in the packing request.

**Preprocessing:** the same cleaning as above, plus item titles are cleaned and any that look like instructions to the
model are left out. Requests ask for strict JSON in a fixed shape.

**Safety Guardrails:** interests are screened before any call; only the trip's owner can ask for suggestions; the
city must be one of the trip's own stops; every reply is parsed and checked (unusable entries are dropped, text is
trimmed, costs are bounded); suggestions wait in the member's session until they press **+ Add**; there is a request
timeout, two attempts per call, and a per-member hourly limit (`AI_API_REQUESTS_PER_HOUR`). Suggestions can still be
wrong, and the pages say so.

| Setting (in `.env`) | Default | Meaning |
|---|---|---|
| `AI_API_KEY` | empty | Key from your provider. Leave empty to switch the hosted features off. Never commit it |
| `AI_API_MODEL` | empty | Model name as the provider lists it |
| `AI_API_BASE_URL` | empty (OpenAI) | Endpoint of any provider with an OpenAI-compatible API |
| `AI_API_TIMEOUT_SECONDS` | `30` | Longest wait for one call |
| `AI_API_REQUESTS_PER_HOUR` | `30` | Hosted requests per member per hour |

Cost, scaling and when to prefer which service are discussed in `notes.txt`.

## Running it

```bash
pip install -r requirements.txt
python manage.py runserver
```

The first draft downloads the model weights (about 3.4 GB) from Hugging Face and caches them on disk; later
drafts reuse them. The model is not gated, so no token is needed. Weights are never committed.

To see how fast it runs on your machine:

```bash
python manage.py check_local_model
```

| Setting (in `.env`) | Default | Meaning |
|---|---|---|
| `AI_LOCAL_ENABLED` | `True` | Turn the on-device model off on hosts that cannot hold it |
| `AI_LOCAL_MODEL` | `HuggingFaceTB/SmolLM2-1.7B-Instruct` | Any chat-tuned causal model on the Hugging Face Hub |
| `AI_LOCAL_TIMEOUT_SECONDS` | `120` | Longest a single generation may run |
| `AI_DRAFTS_PER_HOUR` | `10` | Drafts per member per hour |

Memory: roughly 3.5 GB for the model. It uses an NVIDIA GPU or Apple GPU when present, otherwise the CPU (slower).
