---
name: ocas-sands
description: Calendar management skill. Use when the user wants to view, query, create, modify, delete, or analyze their calendar events. Handles natural-language scheduling, conflict detection with flexibility classification, free slot finding, automatic travel time event insertion between consecutive appointments using Google Places API, and daily schedule briefings for Vesper.
metadata: {"openclaw":{"emoji":"🏜️"}}
---

# ocas-sands — Schedule and Navigation System

Version: 1.1.0
Author: Indigo Karasu

---

## Visibility

public

---

## Trigger Conditions

Use this skill when the user:
- Asks what is on their calendar (today, tomorrow, this week, a specific date)
- Wants to create, reschedule, or cancel an event
- Asks whether they are free at a time
- Asks when they are free for a specific duration ("find me a 1-hour slot this week")
- Asks about conflicts in their schedule
- Wants a travel time block added between events
- Asks what they need to prepare for upcoming events
- Is generating a Vesper morning or evening briefing
- Wants to undo a recent calendar action

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

## Ontology Mapping

Sands extracts and manages two entity types from `spec-ocas-ontology.md`:

**Place** — event locations resolved via Google Places API during `sands.travel`. Each
location is resolved to a place ID and coordinates. Sands does not emit Place signals to
Elephas; location data is retained in `decisions.jsonl` as decision context only.

**Event** (Concept subclass) — calendar events created or modified via `sands.create` and
`sands.modify`. Sands does not emit Event signals to Elephas; calendar events are managed
through Google Calendar, not Chronicle.

Sands queries entity context from:
- **Weave** (read-only) — attendee identity resolution during conflict classification
- **Elephas / Chronicle** — current location context for travel departure resolution

---

## Calendars

Sands operates across three calendar sources configured in `config.json`:

- `primary_calendar_ids` — personal and family Google Calendars (read/write)
- `work_calendar_id` — work calendar (free/busy read only; never write here)

When querying schedule, always pull from all `primary_calendar_ids`. Overlay work busy
blocks from `work_calendar_id` as unavailability markers. Never display work event titles
or descriptions — show only as "Busy (work)" blocks.

---

## Timezone Handling

Sands always works in the user's current timezone, resolved in priority order:

1. Explicit user statement ("I'm in Tokyo", "show times in ET")
2. System location context (Weave → Chronicle)
3. Calendar timezone setting from Google Calendar API
4. `default_timezone` from `config.json`

Rules:
- When displaying times, always use the user's current timezone.
- If an event's timezone differs from the user's current timezone (e.g., a meeting set in
  ET while the user is in PT), show both: "2:00 PM PT (5:00 PM ET)".
- When creating events, set the event timezone to the user's current timezone unless they
  specify otherwise.
- Travel calculations must account for timezone boundaries (rare but possible for
  cross-border travel).

---

## Commands

### `sands.query`
Pull events for a time window.

Input: natural language time reference ("today", "this week", "March 15")
Action:
1. Resolve time window to ISO 8601 range in the user's current timezone
2. Query all `primary_calendar_ids` via `gcal_list_events`
3. Query `work_calendar_id` for busy overlay (titles suppressed)
4. Return chronological merged view with work blocks as "Busy (work)"
5. Display all-day events at the top of each day's listing, visually distinct from timed events
6. Write Observation Journal

### `sands.create`
Create a new event from natural language.

Input: natural language event description
Action:
1. Extract: title, date/time, duration, location (if any), attendees (if any), timezone,
   all_day flag, recurrence pattern (if any)
2. If no explicit duration provided, apply smart defaults — see `references/duration_defaults.md`
3. If the description implies recurrence (e.g., "every Tuesday", "weekly standup"), extract
   recurrence pattern as RRULE
4. If the event spans a full day or multiple days ("vacation June 5-8", "all day"), create as
   an all-day event using date-only start/end
5. Check for conflicts across all calendars before creating
6. If conflict exists, surface it and confirm with the user before proceeding
7. Create via `gcal_create_event` on the appropriate `primary_calendar_id`
8. If the event has a location and a prior event exists within 90 minutes, offer to run `sands.travel`
9. Write Action Journal

### `sands.modify`
Update an existing event from natural language.

Input: reference to an existing event + desired change
Action:
1. Locate event using `gcal_list_events` with search query
2. Confirm the correct event with the user if ambiguous
3. If event is recurring, ask user for scope before applying change: "Just this occurrence,
   this and future occurrences, or all occurrences?"
4. For attendee changes ("add Sarah", "remove Jake"): resolve names via Weave if only a name
   is given; add or remove the attendee email. After attendee changes, re-run conflict
   classification (attendee count affects FIXED/FLEXIBLE).
5. Apply update via `gcal_update_event`
6. Re-run conflict check after update
7. Write Action Journal

Note: attendee changes only apply to `primary_calendar_ids` events. Never modify work
calendar events.

### `sands.delete`
Cancel and remove an existing event.

Input: reference to an existing event, natural language
Action:
1. Locate event using `gcal_list_events` with search query
2. Confirm the correct event with the user (always confirm before delete)
3. If event is recurring, ask user: "Delete just this occurrence, this and future
   occurrences, or all occurrences?" Pass the appropriate scope parameter to the calendar API.
4. Delete via `gcal_delete_event` on the appropriate calendar
5. Clean up: if a travel block references this event (title matches `Travel → [event title]`),
   offer to delete it too
6. Write Action Journal with action `deleted`

Safety rule: Never delete from `work_calendar_id`. Only delete from `primary_calendar_ids`.

### `sands.free`
Find available time slots for a given duration.

Input: desired duration (required), time window (defaults to next 7 days), optional
constraints (e.g., "mornings only", "not before 9am", "not Friday")
Action:
1. Pull all events across all calendars for the time window
2. Compute free intervals by subtracting all event blocks and work busy blocks
3. Exclude hours outside `working_hours` (from config, default 09:00–18:00) unless the user
   explicitly asks for off-hours availability
4. Exclude sleeping hours (00:00–07:00) unless the user explicitly asks
5. Filter intervals by minimum duration
6. Apply any user constraints (day-of-week, time-of-day, etc.)
7. Present top 5 candidate slots, ordered by earliest
8. Write Observation Journal

### `sands.conflicts`
Analyze a time window for scheduling conflicts and classify event flexibility.

Input: time window (defaults to next 7 days if unspecified)
Action:
1. Pull all events across `primary_calendar_ids` and work busy overlay
2. Identify overlapping or back-to-back events with insufficient gap
3. For each conflict pair, classify flexibility — see `references/flexibility_rules.md`
4. Present each conflict with: event names, times, flexibility classification, suggested resolution
5. All-day events do not trigger conflicts with timed events unless the user explicitly asks
6. Do not auto-resolve conflicts. Present options only
7. Write Observation Journal

### `sands.travel`
Insert a travel time block between two consecutive events using Google Places API.

Input: target event (the destination event), optional travel mode (`driving`, `transit`,
`walking`, `bicycling`), or invoked automatically after `sands.create`
Action:
1. Identify destination event and its location string
2. Look at the immediately prior event on the calendar
3. Determine departure point — see `references/travel_time_logic.md`
4. Call Google Places API to resolve both locations to place coordinates
5. Call Google Places Distance Matrix API to get travel time using the selected mode
6. If no mode specified, infer from distance — see `references/travel_time_logic.md`
7. Add `travel_buffer_minutes` (from config, default 10) to the result
8. Check that the gap between events is sufficient — if not, surface a conflict
9. Create travel event with mode-aware title and emoji — see `references/travel_time_logic.md`
10. Write Action Journal

### `sands.brief`
Generate a structured schedule summary for Vesper emission.

Input: target date (defaults to tomorrow for evening brief, today for morning brief)
Brief type is determined by calling context:
- **Evening brief (next day):** full event list with context, conflicts flagged, prep items called out
- **Morning brief (today):** full day-at-a-glance with prep items highlighted

See `references/vesper_emit_format.md` for the output schema.
Action:
1. Pull events for the target date via `sands.query`
2. Analyze for conflicts, prep signals, and travel gaps
3. Build InsightProposal payload
4. Write to `~/openclaw/data/ocas-vesper/intake/{proposal_id}.json`
5. Write Action Journal

### `sands.undo`
Revert the most recent calendar action.

Input: none (defaults to last action) or "undo [event name]"
Action:
1. Read the most recent `created`, `modified`, or `deleted` entry from `events.jsonl`
2. For `created`: delete the event
3. For `modified`: restore previous values from the `previous_values` field in `events.jsonl`
4. For `deleted`: re-create the event from the stored event details in `events.jsonl`
5. Confirm with the user before executing the reversal
6. Write Action Journal

Limitations:
- Only the most recent action per event is undoable
- Undo window: 24 hours. After that, direct the user to `sands.modify` or `sands.delete`
- Recurring event scope changes cannot be undone — warn the user at undo time

### `sands.status`
Return skill health and configuration summary.

Output: SkillStatus object with: configured calendar IDs, Google Places API connectivity,
last run timestamp, last journal path, current timezone.

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
- **Distance Matrix API** — get travel time between two coordinates (supports driving,
  transit, walking, bicycling modes)

Fallback (API unavailable): surface a warning to the user and ask them to confirm an
estimated travel time manually. Do not silently use a distance heuristic.

---

## Recurring Event Handling

Sands supports recurring events across create, modify, and delete commands.

**Creating recurring events:**
- Support patterns: daily, weekly, biweekly, monthly, yearly, and custom (e.g., "every
  Tuesday and Thursday", "first Monday of each month")
- Extract recurrence as RRULE from natural language in `sands.create`
- If the user says "every Tuesday" without an end date, default to no end date (infinite
  recurrence) and confirm with the user

**Modifying recurring events:**
- Always ask for scope before applying: "Just this occurrence, this and future occurrences,
  or all occurrences?"
- Pass the appropriate scope parameter to `gcal_update_event`
- Re-run conflict check for the affected scope

**Deleting recurring events:**
- Same scope question as modify
- Pass scope to `gcal_delete_event`
- Clean up associated travel blocks for affected occurrences

---

## Conflict Detection

Run conflict detection:
- Automatically after `sands.create` and `sands.modify`
- On demand via `sands.conflicts`

A conflict exists when:
- Two events overlap by any amount of time, OR
- Travel time to an event would need to begin before the preceding event ends

All-day events are treated as low-priority background blocks: they do not trigger
conflicts with timed events unless the user explicitly asks.

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
| `sands.free` | Observation |
| `sands.conflicts` | Observation |
| `sands.status` | Observation |
| `sands.create` | Action |
| `sands.modify` | Action |
| `sands.delete` | Action |
| `sands.travel` | Action |
| `sands.brief` | Action |
| `sands.undo` | Action |

Journal path: `~/openclaw/journals/ocas-sands/YYYY-MM-DD/{run_id}.json`

---

## Storage Layout

```
~/openclaw/data/ocas-sands/
  config.json
  decisions.jsonl
  events.jsonl
~/openclaw/journals/ocas-sands/
  YYYY-MM-DD/{run_id}.json
```

`events.jsonl` — append-only log of calendar events created, modified, deleted, or read by
Sands. One record per event interaction: `event_id`, `calendar_id`, `title`, `start`, `end`,
`action` (`created|modified|deleted|queried`), `recurrence_scope`
(`single|this_and_future|all`, optional — present only for recurring event actions),
`previous_values` (optional — present only for `modified` actions, stores the prior field
values to support `sands.undo`), `run_id`, `timestamp`.

`config.json` minimum fields:

```json
{
  "skill_id": "ocas-sands",
  "skill_version": "1.1.0",
  "config_version": "2",
  "created_at": "",
  "updated_at": "",
  "primary_calendar_ids": [
    "primary",
    "family_calendar_id@group.calendar.google.com"
  ],
  "work_calendar_id": "work@company.com",
  "google_places_api_key": "",
  "travel_buffer_minutes": 10,
  "default_travel_mode": "driving",
  "conflict_lookahead_days": 7,
  "default_timezone": "America/Los_Angeles",
  "working_hours": {
    "start": "09:00",
    "end": "18:00"
  },
  "retention": {
    "days": 90,
    "max_records": 10000
  }
}
```

---

## Vesper Interface

Sands emits to: `~/openclaw/data/ocas-vesper/intake/{proposal_id}.json`
Format: InsightProposal schema from `spec-ocas-shared-schemas.md`

`proposal_type` varies by brief type:
- Evening briefs: `routine_prediction`
- Morning briefs: `preparation_checklist`

If `preparation_checklist` is not yet in the InsightProposal schema enum, use
`actionable_insight` as a fallback, or request the type be added to
`spec-ocas-shared-schemas.md`.

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
- Every run produces a journal file per `spec-ocas-journal.md`
- Required `run_identity` fields: `comparison_group_id`, `run_id`, `role`, `skill_name`,
  `skill_version`, `timestamp_start`, `timestamp_end`, `normalized_input_hash`,
  `journal_spec_version`, `journal_type`
- Required `metrics` fields: `success_rate`, `retry_rate`, `latency_ms`
- Required `okr_evaluation` block — see Skill OKRs below
- `decision` block must include: calendars queried, events affected (by title),
  Google Places API calls made (if any)

---

## Skill OKRs

Skill-specific OKRs evaluated in the `okr_evaluation` journal block.

```yaml
skill_okrs:
  - name: conflict_detection_accuracy
    target: ">= 0.95"
    description: "Fraction of actual conflicts correctly identified and surfaced"
  - name: travel_time_api_success_rate
    target: ">= 0.90"
    description: "Fraction of sands.travel runs that complete via Google Places API (not manual fallback)"
  - name: calendar_write_success_rate
    target: ">= 0.98"
    description: "Fraction of sands.create and sands.modify runs with no calendar API error"
```

Universal OKRs (`success_rate` ≥ 0.95, `retry_rate` ≤ 0.10) also apply per `spec-ocas-journal.md` §13.
