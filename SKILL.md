---
name: ocas-sands
description: 'Calendar management skill. Use when the user wants to view, query, create,
  modify, delete, or analyze their calendar events. Handles natural-language scheduling,
  conflict detection with flexibility classification, free slot finding, automatic
  travel time event insertion between consecutive appointments using Google Places
  API, recurring event management, and daily schedule briefings for Vesper. Trigger
  phrases: ''what\''s on my calendar'', ''schedule a meeting'', ''am I free'', ''when
  am I free for an hour'', ''cancel my dentist'', ''add travel time'', ''any conflicts
  this week'', ''what do I need to prepare for tomorrow'', ''undo that'', ''update
  sands''. Do not use for reminders without calendar context, task management, or
  general time/timezone questions.

  '
license: MIT
includes:
- references/**
- evals/**
- scripts/**
metadata:
  author: Indigo Karasu (indigokarasu)
  version: 2.2.0
  hermes:
    tags:
    - calendar
    - scheduling
    - logistics
    category: signal
    cron:
    - name: sands:morning-brief
      schedule: 0 6 * * *
      command: sands.briefing.generate
    - name: sands:evening-brief
      schedule: 0 20 * * *
      command: sands.briefing.generate
    - name: sands:conflict-scan
      schedule: 0 7 * * *
      command: sands.schedule.conflicts
    - name: sands:travel-check
      schedule: 0 7 * * *
      command: sands.logistics.travel
    - name: sands:update
      schedule: 0 0 * * *
      command: sands.update
triggers:
- calendar view
- calendar event
- create event
- modify calendar
- schedule meeting
---
## Interactive Menu

When invoked interactively (via `/` command), present a two-level menu using the `clarify` tool so the user can pick which function to run.

**Level 1 — Category selection** (max 4 choices):

```python
result = clarify(
    question="What would you like to do?",
    choices=[
        "Events — query, create, modify, or delete calendar events",
        "Schedule — find free slots, detect conflicts, calculate travel time",
        "Briefings — generate morning/evening briefings",
        "Status — show system status",
    ]
)
```

**Level 2 — Action selection** based on Level 1 choice:

- **Events** → clarify with choices: "calendar.query — Query calendar events", "event.create — Create a calendar event", "event.modify — Modify an event", "event.delete — Delete an event"
- **Schedule** → clarify with choices: "schedule.free — Find free time slots", "schedule.conflicts — Detect scheduling conflicts", "logistics.travel — Calculate travel time"
- **Briefings** → run "briefing.generate — Generate briefing" directly (single action — no sub-menu needed)
- **Status** → run "status — Show system status" directly (single action — no sub-menu needed)

After the user selects an action, execute it following the relevant procedure in this skill. Loop back to the menu after each action completes, until the user chooses to exit or sends `/stop`.

### Response parsing

Match the user's response against the full choice string. Extract the action key by splitting on `" — "` and taking the first segment. If the response doesn't match any known choice (user typed free-form via "Other"), match key prefixes case-insensitively. Re-present the current menu level on no match.

### Platform adaptation

On CLI, choices are navigable with arrow keys. On messaging platforms, choices render as a numbered list. The two-level hierarchy ensures no more than 4 options appear at any level on any platform.


# Sands

Sands manages calendar events through natural language — creating, querying, modifying, and deleting events across personal and work calendars. It detects scheduling conflicts with flexibility classification, finds free time slots, inserts travel time blocks via Google Places API, and emits structured schedule briefs to Vesper for morning and evening briefings.

## When to Use

- Calendar event creation, modification, and deletion
- Multi-calendar coordination (Personal, Shannon, Family)
- Appointment scheduling with conflict detection
- Focus time and out-of-office management
- When any skill needs calendar operations

## When NOT to Use

- Email or message sending (use Dispatch)
- Content generation or research
- Booking non-calendar appointments (use Spot)
- Travel planning (use Voyage)

## Responsibility boundary

Sands owns calendar event management, conflict analysis, flexibility classification, travel time insertion via Google Places API, and emitting schedule signals to Vesper.

Sands does not own: communications (Dispatch), travel reservations (Voyage), general research (Sift), entity knowledge (Elephas/Weave).

## Ontology types

Sands works with these types from `spec-ocas-ontology.md`:

- **Place** — event locations resolved via Google Places API during `sands.logistics.travel`. Location data retained in `decisions.jsonl` as decision context only. Sands does not emit Place signals to Elephas.
- **Event** (Concept subclass) — calendar events managed through Google Calendar, not Chronicle. Sands does not emit Event signals to Elephas.

Sands queries entity context from:
- **Weave** (read-only) — attendee identity resolution during conflict classification
- **Elephas / Chronicle** — current location context for travel departure resolution

## Commands

- `sands.calendar.query` — pull events for a time window; merged view with work busy overlay
- `sands.event.create` — create event from natural language with conflict pre-check and smart duration defaults
- `sands.event.modify` — update event with recurring scope control and post-modify conflict re-check
- `sands.event.delete` — cancel event with travel block cleanup and recurring scope control
- `sands.event.undo` — revert most recent calendar action (within 24 hours)
- `sands.schedule.free` — find available time slots for a given duration with constraints
- `sands.schedule.conflicts` — analyze time window for conflicts with flexibility classification
- `sands.logistics.travel` — insert travel time block between events via Google Places API
- `sands.briefing.generate` — generate structured schedule summary for Vesper emission
- `sands.status` — skill health, configured calendars, API connectivity, current timezone
- `sands.journal` — write journal for the current run; called at end of every run
- `sands.update` — pull latest from GitHub source; preserves journals and data

See `references/briefing_windows.md` for morning/evening briefing time window definitions.
See `references/credential-files.md` for Google Places API key and OAuth token details, including token staleness handling.

## Run completion

After every Sands command:

1. Persist event interactions to `events.jsonl` (event_id, calendar_id, title, start, end, action, recurrence_scope, previous_values)
2. Log material decisions (conflict resolutions, travel insertions) to `decisions.jsonl`
3. Write journal via `sands.journal` — Observation Journal for query/free/conflicts/status, Action Journal for create/modify/delete/travel/brief/undo

**Post-mutation verification**: After any create/modify/delete command, re-query the calendar for the affected event ID and confirm the change is reflected (correct title, time, calendar placement, or removal). If the event state does not match what was requested, log a `calendar_mismatch` entry in `evidence.jsonl` and alert the user — never silently assume the write succeeded.

## Hard boundaries

- Never write to `work_calendar_id` — read/overlay as busy blocks only
- All-day events do not trigger conflicts with timed events unless explicitly asked
- Never auto-resolve conflicts — present options, let the user choose
- Never use a hardcoded home address or assume a fixed city for travel departure
- Never silently fall back to distance heuristics if Google Places API is unavailable — surface warning and ask for manual estimate
- Undo window is 24 hours; recurring event scope changes cannot be undone

## Recovery Behavior

This skill implements the recovery contract from `spec-ocas-recovery.md`.

- **Evidence**: Every scheduled run writes an evidence record to `{agent_root}/commons/data/ocas-sands/evidence.jsonl`, including no-op runs. The `not_activity_reason` field is mandatory when no side effects occur.
- **Gap detection**: On every wake, checks the evidence log. If gap exceeds cadence (24h for briefs, 24h for conflict-scan), logs `gap_detected`.
- **Degraded mode**: When Google Calendar API or Google Places API fail, logs `degraded: <api>` and continues with available data.
- **Log compaction**: Evidence and decision logs older than 30 days (no-op) or 90 days (error/gap) compacted. Last 7 days retained.

## Storage layout

See `references/schemas.md` for the full storage layout and default config.json.

## OKRs

Universal OKRs from spec-ocas-journal.md apply to all runs. See `references/okrs.md` for details.

## Optional skill cooperation

- Weave — attendee identity resolution and current location context
- Elephas — current location or travel context from Chronicle
- Voyage — travel reservations detected in calendar surfaced for Voyage to manage
- Vesper — Vesper reads Sands schedule briefs at journal payload fields (see interfaces specification) during briefing generation (cooperative write; Sands pushes to Vesper (via journal briefing payload))

## Journal outputs

- Observation Journal — sands.calendar.query, sands.schedule.free, sands.schedule.conflicts, sands.status
- Action Journal — sands.event.create, sands.event.modify, sands.event.delete, sands.event.undo, sands.logistics.travel, sands.briefing.generate

## Initialization

On first invocation of any Sands command, run `sands.init`:

1. Create `{agent_root}/commons/data/ocas-sands/` directory
2. Write default `config.json` with ConfigBase fields if absent
3. Create empty JSONL files: `decisions.jsonl`, `events.jsonl`, `evidence.jsonl`, `intents.jsonl`
4. Create `{agent_root}/commons/journals/ocas-sands/`
5. Register cron jobs listed below if not already present (check the platform scheduling registry first)
6. Log initialization as a DecisionRecord in `decisions.jsonl`

## Background tasks

Registered during `sands.init`. Always check existing jobs before registering:

| Job name | Schedule | Command | Purpose |
|---|---|---|---|
| `sands:morning-brief` | `0 6 * * *` | `sands.briefing.generate` | Today's schedule brief for Vesper |
| `sands:evening-brief` | `0 20 * * *` | `sands.briefing.generate` | Tomorrow's schedule brief for Vesper |
| `sands:conflict-scan` | `0 7 * * *` | `sands.schedule.conflicts` | Daily conflict scan for upcoming 7 days |
| `sands:travel-check` | `0 7 * * *` | `sands.logistics.travel` | Check next day's events for missing travel blocks |
| `sands:update` | `0 0 * * *` | `sands.update` | Self-update from GitHub source |

All cron jobs use: `--session isolated --light-context --tz America/Los_Angeles`.

Registration during `sands.init`:
Check the platform scheduling registry for existing tasks before registering each job. Tasks are declared in SKILL.md frontmatter `metadata.{platform}.cron`.

## Self-Update

See `references/self-update-sands.md`.

## Visibility

public

## Gotchas

- **⚠️ write_file OVERWRITES — JSONL append requires read-then-rewrite** — The `write_file` tool replaces the entire file. NEVER call `write_file` on `evidence.jsonl`, `decisions.jsonl`, or `events.jsonl` with only the new record — you will destroy all prior history. The correct append pattern is: (1) `read_file` the existing JSONL, (2) construct the full content (all existing lines + new line), (3) `write_file` with the complete content. Always verify line count increased by 1 after writing. If you accidentally overwrite, check session context for the original contents to restore from.
- **Work calendar is read-only** — Sands can overlay work calendar busy blocks but must never write to `work_calendar_id`. Writing to a read-only calendar will fail silently or produce API errors.
- **All-day events don't conflict with timed events** — Per the hard boundary, all-day events are excluded from conflict detection with timed events unless the user explicitly asks. This can hide real scheduling issues if the user expects otherwise.
- **Google Places API failure is surfaced, not silently handled** — If the Google Places API is unavailable, Sands does NOT fall back to distance heuristics. It surfaces a warning and asks for a manual estimate.
- **Undo window is 24 hours and non-recurring** — Event undo is only available within 24 hours of the original action. Recurring event scope changes cannot be undone at all.
- **OAuth tokens may stale between cron runs** — Calendar queries can fail with auth errors if the OAuth token expires between scheduled runs. Always trigger re-authentication before retrying; do not suppress the error.
  - **Compound failure: OAuth stale + MCP unreachable** — When `get_events` fails with an OAuth error, the corrective action is `start_google_auth`. But if the MCP *server* is also unreachable, `start_google_auth` will fail too (same transport). In this scenario: (1) note `degraded: google_workspace_mcp` AND `degraded: oauth_stale` in evidence, (2) update `config.json auth_status` to `STALE_OAUTH`, (3) surface to the user that TWO things need fixing — the MCP server process must be running AND OAuth must be re-authorized. Do NOT retry auth in a loop when the MCP server is unreachable; it will just burn tool calls.
- **Timezone offsets change with daylight saving** — Pacific time is `-08:00` (PST) in winter and `-07:00` (PDT) in summer. When building RFC3339 time_min/time_max for queries, determine the correct offset for the TARGET date, not today's date. Using the wrong offset shifts the query window by one hour and can return no events or wrong-day events. The `default_timezone` in config.json (`America/Los_Angeles`) is a hint — always check whether the target date falls in PDT (Mar–Nov) or PST (Nov–Mar) and use the matching offset.
- **Google Workspace MCP server may be transiently unreachable** — If `get_events` or other MCP calls fail with "unreachable" errors, wait ~40 seconds (the auto-retry cooldown) and try once more before logging `degraded`. A single cooldown wait resolves most transient failures. Only log `degraded: google_workspace_mcp` after the retry also fails.
- **Single event = no travel blocks needed** — When only one event exists on a travel-check day, there are nothing to insert between. Still write evidence (with `not_activity_reason: no_consecutive_events`) and update `config.json last_travel_check` so gap detection stops flagging the stale timestamp.
- **Google Places API key empty = travel check is observational** — When `google_places_api_key` is empty in config.json, travel blocks can never be auto-created. The travel-check command runs but will only report consecutive event pairs it cannot service. If the key is empty, note this in the evidence log's `degraded` field.

## Support File Map

| File | When to read |
|------|-------------|
| `references/briefing_windows.md` | Before sands.briefing.generate |
| `references/calendar_config.md` | Before configuring calendars or timezone handling |
| `references/credential-files.md` | Before first OAuth setup or when handling token staleness |
| `references/timezone_handling.md` | Before constructing time_min/time_max for get_events |
| `references/google_calendar_api_quirks.md` | Before manage_event calls |
| `references/duration_defaults.md` | Before sands.event.create |
| `references/flexibility_rules.md` | Before sands.schedule.conflicts |
| `references/conflict_detection.md` | Before conflict analysis |
| `references/recurring_events.md` | Before creating/modifying/deleting recurring events |
| `references/preparation_signals.md` | Before sands.briefing.generate |
| `references/travel_time_logic.md` | Before sands.logistics.travel |
| `references/vesper_emit_format.md` | Before sands.briefing.generate; formatting payload for Vesper |
| `references/self-update-sands.md` | Before running sands.update |

