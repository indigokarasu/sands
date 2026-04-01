# ocas-sands — Schedule and Navigation System

Version: 1.0.0
Author: Indigo Karasu
Visibility: public

---

## Trigger Conditions

Use this skill when the user:
- Asks what is on their calendar (today, tomorrow, this week, a specific date)
- Wants to create, reschedule, or cancel an event
- Asks whether they are free at a time
- Asks about conflicts in their schedule
- Wants a travel time block added between events
- Asks what they need to prepare for upcoming events
- Is generating a Vesper morning or evening briefing

Do not use for: reminders not tied to calendar events, task lists, general time questions.

---

## Responsibility Boundary

**Sands is responsible for:** reading and writing calendar events, conflict analysis,
flexibility classification, travel time insertion via Google Places API, and emitting
schedule signals to Vesper.

**Sands is not responsible for:** routing or sending communications (Dispatch), booking
travel reservations (Voyage), general research (Sift), location or entity knowledge
(Elephas/Weave).

**Adjacent skills:** Vesper consumes Sands schedule signals for briefings. Sands does not
depend on Vesper to function.

---

## Calendars

Sands operates across three calendar sources configured in `config.json`:

- `primary_calendar_ids` — personal and family Google Calendars (read/write)
- `work_calendar_id` — work calendar (free/busy read only; never write here)

When querying schedule, always pull from all `primary_calendar_ids`. Overlay work busy
blocks from `work_calendar_id` as unavailability markers. Never display work event titles
or descriptions — show only as "Busy (work)" blocks.

---

## Commands

### `sands.query`
Pull events for a time window.

Input: natural language time reference ("today", "this week", "March 15")
Action:
1. Resolve time window to ISO 8601 range
2. Query all `primary_calendar_ids` via `gcal_list_events`
3. Query `work_calendar_id` for busy overlay (titles suppressed)
4. Return chronological merged view with work blocks as "Busy (work)"
5. Write Observation Journal

### `sands.create`
Create a new event from natural language.

Input: natural language event description
Action:
1. Extract: title, date/time, duration, location (if any), attendees (if any)
2. Check for conflicts across all calendars before creating
3. If conflict exists, surface it and confirm with the user before proceeding
4. Create via `gcal_create_event` on the appropriate `primary_calendar_id`
5. If the event has a location and a prior event exists within 90 minutes, offer to run `sands.travel`
6. Write Action Journal


### `sands.modify`
Update an existing event from natural language.

Input: reference to an existing event + desired change
Action:
1. Locate event using `gcal_list_events` with search query
2. Confirm the correct event with the user if ambiguous
3. Apply update via `gcal_update_event`
4. Re-run conflict check after update
5. Write Action Journal

### `sands.conflicts`
Analyze a time window for scheduling conflicts and classify event flexibility.

Input: time window (defaults to next 7 days if unspecified)
Action:
1. Pull all events across `primary_calendar_ids` and work busy overlay
2. Identify overlapping or back-to-back events with insufficient gap
3. For each conflict pair, classify flexibility — see `references/flexibility_rules.md`
4. Present each conflict with: event names, times, flexibility classification, suggested resolution
5. Do not automatically move anything — present options only
6. Write Observation Journal

### `sands.travel`
Insert a travel time block between two consecutive events using Google Places API.

Input: target event (the destination event), or invoked automatically after `sands.create`
Action:
1. Identify destination event and its location string
2. Look at the immediately prior event on the calendar
3. Determine departure point — see `references/travel_time_logic.md`
4. Call Google Places API to resolve both locations to place coordinates
5. Call Google Places Distance Matrix API to get driving travel time
6. Add `travel_buffer_minutes` (from config, default 10) to the result
7. Check that the gap between events is sufficient — if not, surface a conflict
8. Create "🚗 Travel → [destination event title]" event filling the gap
9. Write Action Journal

### `sands.brief`
Generate a structured schedule summary for Vesper emission.

Input: target date (defaults to tomorrow for evening brief, today for morning brief)
Brief type is determined by calling context:
- **Evening brief (next day):** full event list with context, conflicts flagged, prep items called out
- **Morning brief (today):** prep items only — actionable, not a flat event list

See `references/vesper_emit_format.md` for the output schema.
Action:
1. Pull events for the target date via `sands.query`
2. Analyze for conflicts, prep signals, and travel gaps
3. Build InsightProposal payload
4. Write to `~/openclaw/data/ocas-vesper/intake/{proposal_id}.json`
5. Write Action Journal

### `sands.status`
Return skill health and configuration summary.

Output: SkillStatus object with: configured calendar IDs, Google Places API connectivity,
last run timestamp, last journal path.

---

## Location Context for Travel

Sands never uses a hardcoded home address or assumes any fixed city.

Priority order for resolving departure location:
1. Prior event within 90 minutes with a specific location → use that location
2. No prior event (or prior event has no location): query current location from the system
   (Weave → Chronicle → user's current lodging or home)
3. If traveling (hotel, Airbnb, out-of-town context): depart from current lodging
4. If at home: depart from home location
5. If location context unavailable: ask the user before proceeding

Never back-calculate travel from a home city if the user is traveling elsewhere.
See `references/travel_time_logic.md` for full decision rules and Google Places API call sequence.


---

## Google Places API Usage

Sands uses Google Places API for all travel time calculations.

API calls used:
- **Places Search / Find Place** — resolve a location string to a place ID and coordinates
- **Distance Matrix API** — get travel time between two coordinates by driving mode

Fallback (API unavailable): surface a warning to the user and ask them to confirm an
estimated travel time manually. Do not silently use a distance heuristic.

---

## Conflict Detection

Run conflict detection:
- Automatically after `sands.create` and `sands.modify`
- On demand via `sands.conflicts`

A conflict exists when:
- Two events overlap by any amount of time, OR
- Travel time to an event would need to begin before the preceding event ends

Do not auto-resolve conflicts. Present them with a flexibility assessment and candidate
resolutions for the user to choose from. See `references/flexibility_rules.md`.

---

## Preparation Detection

On morning briefs, flag events that likely need preparation.
See `references/preparation_signals.md` for the full signal list and output format.

---

## Optional Skill Cooperation

Sands may cooperate with these skills when present but never depends on them:

- **Weave** — resolve attendee identity or current location context
- **Elephas** — query current location or travel context from Chronicle
- **Voyage** — if a travel reservation is detected in the calendar, surface it for
  Voyage to manage; Sands does not book reservations itself

---

## Journal Outputs

| Command | Journal Type |
|---|---|
| `sands.query` | Observation |
| `sands.conflicts` | Observation |
| `sands.status` | Observation |
| `sands.create` | Action |
| `sands.modify` | Action |
| `sands.travel` | Action |
| `sands.brief` | Action |

Journal path: `~/openclaw/journals/ocas-sands/YYYY-MM-DD/{run_id}.json`

---

## Storage Layout

```
~/openclaw/data/ocas-sands/
  config.json
  decisions.jsonl
~/openclaw/journals/ocas-sands/
  YYYY-MM-DD/{run_id}.json
```

`config.json` minimum fields:

```json
{
  "skill_id": "ocas-sands",
  "skill_version": "1.0.0",
  "config_version": "1",
  "created_at": "",
  "updated_at": "",
  "primary_calendar_ids": [
    "primary",
    "family_calendar_id@group.calendar.google.com"
  ],
  "work_calendar_id": "work@company.com",
  "google_places_api_key": "",
  "travel_buffer_minutes": 10,
  "conflict_lookahead_days": 7
}
```

---

## Vesper Interface

Sands emits to: `~/openclaw/data/ocas-vesper/intake/{proposal_id}.json`
Format: InsightProposal schema from `spec-ocas-shared-schemas.md`
`proposal_type`: `opportunity_discovery`
See `references/vesper_emit_format.md` for the full payload structure.

---

## Validation Rules

Before creating any event:
- Confirm no exact-duplicate title+time exists on that calendar
- Confirm the slot is not blocked by a work busy period (warn, do not block)

Before inserting travel:
- Gap must be ≥ calculated travel time + buffer. If not, surface conflict instead of
  creating a truncated or overlapping travel block.

On journal write:
- Every run produces a journal file
- Journal must include: run_id, command, calendars queried, events affected (by title),
  decision summary, Google Places API calls made (if any)
