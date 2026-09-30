---
name: ocas-sands
license: MIT
description: 'Calendar management: view, query, create, modify, delete, and analyze calendar events via natural language. Use for scheduling ("book a meeting Thursday 3pm"), conflict detection with flexibility classification, free-slot finding, automatic travel-time block insertion between consecutive appointments, recurring event management, and daily schedule briefings for Vesper. Keywords: calendar, event, schedule, meeting, appointment, availability, free slot, conflict, booking, recurring, travel time, briefing. NOT for reminders without calendar context, plain task management or to-do lists, general time/timezone questions, or when a dedicated calendar skill already owns the request.'
source: https://github.com/<agent-handle>/sands
includes:
- references/**
- evals/**
- scripts/**
- templates/**
metadata:
  author: Indigo Karasu (indigokarasu)
  version: "2.4.0"
  activation:
    requires_tools: ["workspace_mcp"]
    fallback_for_tools: ["google_api_fallback"]
  hermes:
    category: productivity
    tags:
    - calendar
    - scheduling
    - events
    - OCAS-core
    config:
    - key: OCAS_OPERATOR_EMAIL
      description: Primary Google account email used for Calendar API access
      default: "<user-google-email>"
    - key: OCAS_AGENT_EMAIL
      description: Secondary/fallback Google account tried when the primary token is invalid
      default: "<agent-email>"
    - key: OCAS_FAMILY_CALENDAR_ID
      description: Shared family calendar id, queried alongside the personal calendar
      default: "<family-calendar-id>@group.calendar.google.com"
    - key: OCAS_TIMEZONE
      description: IANA timezone for target-date UTC offset computation in the briefing templates
      default: America/Los_Angeles
    - key: HERMES_HOME
      description: Hermes root used to locate scripts/google_auth_mcp.py
      default: "~/.hermes"
required_environment_variables:
- name: OCAS_OPERATOR_EMAIL
  prompt: Google account email with Calendar access
  help_url: https://hermes-agent.nousresearch.com/docs
  required_for: optional
- name: OCAS_FAMILY_CALENDAR_ID
  prompt: Shared family calendar id (group calendar)
  help_url: https://hermes-agent.nousresearch.com/docs
  required_for: optional
triggers:
- calendar view
- calendar event
- create event
- modify calendar
- schedule meeting
- find free time
- check conflicts
- travel time between events
---
## Interactive Menu

When invoked interactively (via `/` command), present a two-level menu. See `references/interactive-menu.md` for the menu structure and response parsing logic.

# Sands

Sands manages calendar events through natural language — creating, querying, modifying, and deleting events across personal and work calendars. It detects scheduling conflicts with flexibility classification, finds free time slots, inserts travel time blocks via Google Places API, and emits structured schedule briefs to Vesper for morning and evening briefings.

## When to Use

- Calendar event creation, modification, and deletion
- Multi-calendar coordination (Personal, Shannon, Family)
- Appointment scheduling with conflict detection
- Focus time and out-of-office management
- When any skill needs calendar operations

For example, when the user says "schedule a meeting with <operator> at 3pm tomorrow," Sands creates the event with conflict pre-check and smart duration defaults.

## When NOT to Use

- Email or message sending (use Dispatch)
- Content generation or research
- Booking non-calendar appointments (use Spot)
- Travel planning (use Voyage)

## Responsibility boundary

Sands owns calendar event management, conflict analysis, flexibility classification, travel time insertion via Google Places API, and emitting schedule signals to Vesper.

Sands does not own: communications (Dispatch), travel reservations (Voyage), general research (Sift), entity knowledge (Weave).

## Ontology types

Sands works with these types from [[`spec-ocas-ontology.md` ⚠️ Pending spec] ⚠️ Pending spec — not yet authored]:

- **Place** — event locations resolved via Google Places API during `sands.logistics.travel`. Location data retained in `decisions.jsonl` as decision context only.
- **Event** (Concept subclass) — calendar events managed through Google Calendar, not Chronicle.

Sands queries entity context from:
- **Weave** (read-only) — attendee identity resolution during conflict classification
- **Chronicle** — current location context for travel departure resolution

## Commands

- `sands.calendar.query` — pull events for a time window; merged view with work busy overlay
- `sands.event.create` — create event from natural language with conflict pre-check and smart duration defaults
- `sands.event.modify` — update event with recurring scope control and post-modify conflict re-check
- `sands.event.delete` — cancel event with travel block cleanup and recurring scope control
- `sands.event.undo` — revert most recent calendar action (within 24 hours)
- `sands.schedule.free` — find available time slots for a given duration with constraints
- `sands.schedule.conflicts` — analyze time window for conflicts with flexibility classification. See `references/conflict-report-format.md` for output template.
- `sands.logistics.travel` — insert travel time block between events via Google Places API
- `sands.briefing.generate` — generate structured schedule summary for Vesper emission
- `sands.status` — skill health, configured calendars, API connectivity, current timezone
- `sands.journal` — write journal for the current run; called at end of every run
- `sands.update` — pull latest from GitHub source; preserves journals and data
- `sands.chronicle.sync` — push travel, medical, and personal calendar events into Chronicle as persistent facts

See `references/briefing_windows.md` for morning/evening briefing time window definitions.
See `references/credential-files.md` for Google Places API key and OAuth token details, including token staleness handling.

## Run completion

After every Sands command:

- [ ] Persist event interactions to `events.jsonl` (event_id, calendar_id, title, start, end, action, recurrence_scope, previous_values)
- [ ] Log material decisions (conflict resolutions, travel insertions) to `decisions.jsonl`
- [ ] Write journal via `sands.journal` — Observation Journal for query/free/conflicts/status, Action Journal for create/modify/delete/travel/brief/undo

**Post-mutation verification**: After any create/modify/delete command, re-query the calendar for the affected event ID and confirm the change is reflected (correct title, time, calendar placement, or removal). If the event state does not match what was requested, log a `calendar_mismatch` entry in `evidence.jsonl` and alert the user — never silently assume the write succeeded.

### I/O examples

Appending a run record (the only supported way to write a Sands JSONL):

```
terminal("python3 <skill_dir>/scripts/append_jsonl.py \
  $DATA_DIR/evidence.jsonl \
  '{\"timestamp\":\"2026-09-27T06:00:00-07:00\",\"command\":\"sands.briefing.generate\",\
    \"status\":\"ok\",\"not_activity_reason\":null}'")
# → Appended. File now has 412 records.
```

Running the evening brief without persisting anything (safe probe):

```
terminal("python3 <skill_dir>/templates/sands_briefing_evening.py --dry-run")
# → prints the summary + ---BRIEFING_PAYLOAD_JSON--- block
# → "(dry-run) /tmp/sands_evening_briefing.json NOT written"
```

Reading a window (note the offset is for the *target* date, not today):

```
mcp_google_workspace_get_events(
  user_google_email="<user-google-email>",
  timeMin="2026-11-15T00:00:00-08:00",   # PST — November
  timeMax="2026-11-16T00:00:00-08:00",
  calendarId="<user-google-email>")
```


## Hard boundaries

Each of these is a hard stop rather than a default, because the failure mode is
silent and expensive:

- **Never write to `work_calendar_id`** — read/overlay as busy blocks only. It's another org's calendar; a write there fails silently or 403s, and Sands can't undo it.
- **All-day events do not trigger conflicts with timed events** unless explicitly asked. Per Google semantics an all-day event spans the whole day; treating it as busy would mark every day full.
- **Never auto-resolve conflicts** — present options, let the user choose. Which appointment moves is a human judgement, not a heuristic.
- **Overlap between DIFFERENT people's calendars is not a conflict by default.** The operator shares a household with others (spouse/family calendar) who have their own commitments. Two events at the same time — one on the operator's calendar, one on a housemate's — means each of them is busy somewhere, not that either has a double-booking. Only report a conflict when (a) two events overlap on the SAME calendar, or (b) the operator is expected at both. Overlays of a second calendar (work, spouse, family) are BUSY CONTEXT for feasibility, not conflict triggers. Ask before surfacing cross-calendar overlap as a conflict.
- **Never use a hardcoded home address or assume a fixed city for travel departure** — a wrong origin silently produces a wrong travel block, which is worse than no block because it looks authoritative.
- **Never silently fall back to distance heuristics if Google Places API is unavailable** — surface a warning and ask for a manual estimate. A guessed duration presented as a computed one is the exact failure this rule exists to prevent.
- **Undo window is 24 hours; recurring event scope changes cannot be undone** — an unbounded undo on a recurring series can silently rewrite a month of history.

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
- Chronicle — current location or travel context
- Voyage — travel reservations detected in calendar surfaced for Voyage to manage
- Vesper — Vesper reads Sands schedule briefs at journal payload fields (see interfaces specification) during briefing generation (cooperative write; Sands pushes to Vesper (via journal briefing payload))

## Journal outputs

- Observation Journal — sands.calendar.query, sands.schedule.free, sands.schedule.conflicts, sands.status
- Action Journal — sands.event.create, sands.event.modify, sands.event.delete, sands.event.undo, sands.logistics.travel, sands.briefing.generate

## Initialization

On first invocation of any Sands command, run `sands.init`:

- [ ] Create `{agent_root}/commons/data/ocas-sands/` directory
- [ ] Write default `config.json` with ConfigBase fields if absent
- [ ] Create empty JSONL files: `decisions.jsonl`, `events.jsonl`, `evidence.jsonl`, `intents.jsonl`
- [ ] Create `{agent_root}/commons/journals/ocas-sands/` and ensure both journal files exist (create empty if absent): `action.jsonl`, `observation.jsonl`
- [ ] Register cron jobs listed below if not already present (check the platform scheduling registry first)
- [ ] Log initialization as a DecisionRecord in `decisions.jsonl`

## Background tasks

Registered during `sands.init`. Always check existing jobs before registering:

| Job name | Schedule | Command | Purpose |
|---|---|---|---|
| `sands:morning-brief` | `0 6 * * *` | `sands.briefing.generate` | Today's schedule brief for Vesper |
| `sands:evening-brief` | `0 20 * * *` | `sands.briefing.generate` | Tomorrow's schedule brief for Vesper |
| `sands:conflict-scan` | `0 7 * * *` | `sands.schedule.conflicts` | Daily conflict scan for upcoming 7 days |
| `sands:travel-check` | `0 7 * * *` | `sands.logistics.travel` | Check next day's events for missing travel blocks |
| `sands:update` | `0 0 * * *` | `sands.update` | Self-update from GitHub source |
| `sands:chronicle-sync` | `0 8 * * 0` | `sands.chronicle.sync` | Weekly calendar → Chronicle fact sync (Sundays 8 AM) |

All cron jobs use: `--session isolated --light-context --tz America/Los_Angeles`.

Registration during `sands.init`:
Check the platform scheduling registry for existing tasks before registering each job. Tasks are declared in SKILL.md frontmatter `metadata.{platform}.cron`.

## Self-Update

See `references/self-update-sands.md`.

## Visibility

public

## Gotchas

Full pitfall list: `references/gotchas.md`. The three that cause data loss or
silent wrong answers most often:

- **`write_file` OVERWRITES — never use it for a JSONL append.** Use `scripts/append_jsonl.py`; for titles with emoji, see the Unicode-safe pattern in `references/cron_persistence.md`.
- **Zero-duration and midnight-crossing events break naive overlap math.** Exclude `start == end` before calling `span_minutes`, and add 1440 when `end_min <= start_min`. See `references/zero_duration_briefing.md`.
- **Every MCP Google Workspace call needs `user_google_email`.** Omitting it yields a Pydantic error that never says "missing parameter." See `references/gotchas.md` → MCP Tool Quirks.

## Error Handling

| Failure | Symptom | Handling |
|---|---|---|
| `invalid_grant` or `400 Bad Request` from `oauth2.googleapis.com/token` | `get_service()` raises for one account | Log the account, try the next in `ACCOUNTS_TO_TRY`; if all fail set `auth_status: STALE_OAUTH` and log `degraded: oauth_stale` |
| MCP server unreachable | `get_events` fails with a transport error | Wait ~40s (auto-retry cooldown) and retry once; only then log `degraded: google_workspace_mcp` |
| MCP auth error with the server reachable | 401/403 / `invalid_grant` from `mcp_google_workspace_*` | Switch to the direct Python fallback (`get_service`); it bypasses the MCP token layer. See `references/direct_calendar_access.md` |
| Cron run, no user present to re-auth | Interactive OAuth consent cannot run | Log `degraded: cron_cannot_reauth`, still update `last_*` timestamps so gap detection doesn't flag a scan that never happened |
| A configured calendar id 404s | `list`/`get` returns 404 for one id | Log it in `degraded`, continue with remaining calendars, surface the broken id to the user |
| `google_places_api_key` empty | Travel check finds consecutive pairs it cannot service | Run observationally; report the pairs and note `degraded`. Do not fabricate a distance |
| `FileNotFoundError` appending to a journal | Parent directory missing on first run | `mkdir -p "$DATA_DIR/journals"` and retry; `append_jsonl.py` handles files, not parent dirs |
| `execute_code` rejected in cron | Tool call refused — no user to approve | Use the `write_file` + `terminal` pattern; see `references/direct_calendar_access.md` |
| Post-write re-query disagrees with the request | Event state does not match | Log `calendar_mismatch` in `evidence.jsonl` and alert the user — never assume the write succeeded |

## Cron Script Templates

- `templates/sands_briefing_morning.py` — Reusable cron-compatible morning briefing script with multi-account fallback, dedup, conflict detection (zero-duration-safe), and prep-signal checking.
- `templates/sands_briefing_evening.py` — Evening counterpart: queries TOMORROW's events, omits prep-signal checks, emits `proposal_type: routine_prediction`, and excludes zero-duration events from conflict/free-hours math. Pure generator; the calling run persists evidence/action/config (see `references/zero_duration_briefing.md`).

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
| `references/conflict-report-format.md` | Before generating conflict scan report output |
| `references/recurring_events.md` | Before creating/modifying/deleting recurring events |
| `references/preparation_signals.md` | Before sands.briefing.generate |
| `references/travel_time_logic.md` | Before sands.logistics.travel |
| `references/vesper_emit_format.md` | Before sands.briefing.generate; formatting payload for Vesper |
| `references/self-update-sands.md` | Before running sands.update |
| `references/direct_calendar_access.md` | When MCP Google Workspace tools are unavailable; direct Python fallback pattern |
| `scripts/conflict_scan_template.py` | Reusable cron-compatible conflict scan script with multi-account OAuth fallback |
| `scripts/travel_check.py` | Reusable cron-compatible travel check. Pairs by located anchors, calls Routes v2 with the required `X-Goog-FieldMask`, resolves the canonical data dir and the Places key from secrets. `--dry-run` / `--target YYYY-MM-DD`. |
| `references/chronicle_sync.md` | Before sands.chronicle.sync; event classification rules, value format, ingest script path, cron auth pattern, classification pitfalls |
| `references/gotchas.md` | Common pitfalls, OAuth quirks, MCP tool limitations, cron-mode constraints, and UCSF MyChart double-import pattern |
| `references/cron_persistence.md` | Unicode-safe JSONL persistence in cron mode (emoji in titles) + why `config.json primary_calendar_ids` drifts from the briefing template's hardcoded calendar list |
| `templates/sands_briefing_morning.py` | Reusable cron-compatible morning briefing script — multi-account fallback, dedup, conflict detection, prep signals |
| `references/mcp_fallback_briefing.md` | When the morning briefing script raises a dependency or import error |
| `references/known-calendar-ids.md` | Before using a calendar id that isn't in config.json, or when a configured id returns 404 |
| `references/okrs.md` | When aligning a run's evidence record against the universal OKRs |
| `references/schemas.md` | Before writing any record to evidence/decision/event JSONL, or when adding a field |
| `references/google_calendar_api.md` | When a query needs a Calendar API parameter the MCP wrapper rejects (`orderBy`, `singleEvents`, `showDeleted`) |
| `references/oauth_recovery.md` | When both accounts fail auth and you need the escalation order before declaring degradation |
| `references/interactive-menu.md` | When invoked interactively via the `/` command, to render and parse the two-level menu |
| `references/zero_duration_briefing.md` | Before persisting a morning or evening brief, or when writing overlap/zero-duration math |
| `templates/sands_briefing_evening.py` | When generating the 20:00 evening brief for tomorrow |
| `scripts/append_jsonl.py` | Whenever appending a record to any Sands JSONL — never use `write_file` on one |
| `scripts/briefing_morning_regression.py` | After editing `templates/sands_briefing_morning.py`, or when a brief looks wrong — verifies `--help` stays side-effect free and that placeholder/unset calendar ids abort instead of 404ing |
