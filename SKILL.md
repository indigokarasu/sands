---
name: ocas-sands
source: https://github.com/indigokarasu/sands
install: openclaw skill install https://github.com/indigokarasu/sands
description: Calendar management skill. Use when the user wants to view, query, create, modify, delete, or analyze their calendar events. Handles natural-language scheduling, conflict detection with flexibility classification, free slot finding, automatic travel time event insertion between consecutive appointments using Google Places API, recurring event management, and daily schedule briefings for Vesper. Trigger phrases: 'what's on my calendar', 'schedule a meeting', 'am I free', 'when am I free for an hour', 'cancel my dentist', 'add travel time', 'any conflicts this week', 'what do I need to prepare for tomorrow', 'undo that', 'update sands'. Do not use for reminders without calendar context, task management, or general time/timezone questions.
metadata: {"openclaw":{"emoji":"🏜️"}}
---

# Sands

Sands manages calendar events through natural language — creating, querying, modifying, and deleting events across personal and work calendars. It detects scheduling conflicts with flexibility classification, finds free time slots, inserts travel time blocks via Google Places API, and emits structured schedule briefs to Vesper for morning and evening briefings.


## When to use

- View, query, create, modify, or delete calendar events
- Find free time slots for a given duration
- Detect and classify scheduling conflicts
- Insert travel time blocks between events
- Generate schedule briefs for Vesper briefings
- Undo a recent calendar action


## When not to use

- Reminders not tied to calendar events
- Task lists or project management
- General time or timezone questions
- Booking travel reservations — use Voyage
- Sending meeting invitations or communications — use Dispatch


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


## Run completion

After every Sands command:

1. Persist event interactions to `events.jsonl` (event_id, calendar_id, title, start, end, action, recurrence_scope, previous_values)
2. Log material decisions (conflict resolutions, travel insertions) to `decisions.jsonl`
3. Write journal via `sands.journal` — Observation Journal for query/free/conflicts/status, Action Journal for create/modify/delete/travel/brief/undo


## Hard boundaries

- Never write to `work_calendar_id` — read/overlay as busy blocks only
- All-day events do not trigger conflicts with timed events unless explicitly asked
- Never auto-resolve conflicts — present options, let the user choose
- Never use a hardcoded home address or assume a fixed city for travel departure
- Never silently fall back to distance heuristics if Google Places API is unavailable — surface warning and ask for manual estimate
- Undo window is 24 hours; recurring event scope changes cannot be undone


## Storage layout

```
~/openclaw/data/ocas-sands/
  config.json
  decisions.jsonl
  events.jsonl
~/openclaw/journals/ocas-sands/
  YYYY-MM-DD/{run_id}.json
```

Default config.json:
```json
{
  "skill_id": "ocas-sands",
  "skill_version": "2.0.0",
  "config_version": "2",
  "created_at": "",
  "updated_at": "",
  "primary_calendar_ids": ["primary"],
  "work_calendar_id": "",
  "google_places_api_key": "",
  "travel_buffer_minutes": 10,
  "default_travel_mode": "driving",
  "conflict_lookahead_days": 7,
  "default_timezone": "America/Los_Angeles",
  "working_hours": { "start": "09:00", "end": "18:00" },
  "retention": { "days": 90, "max_records": 10000 }
}
```


## OKRs

Universal OKRs from spec-ocas-journal.md apply to all runs.

```yaml
skill_okrs:
  - name: conflict_detection_accuracy
    metric: fraction of actual conflicts correctly identified and surfaced
    direction: maximize
    target: 0.95
    evaluation_window: 30_runs
  - name: travel_time_api_success_rate
    metric: fraction of sands.logistics.travel runs completing via Google Places API
    direction: maximize
    target: 0.90
    evaluation_window: 30_runs
  - name: calendar_write_success_rate
    metric: fraction of create/modify runs with no calendar API error
    direction: maximize
    target: 0.98
    evaluation_window: 30_runs
```


## Optional skill cooperation

- Weave — attendee identity resolution and current location context
- Elephas — current location or travel context from Chronicle
- Voyage — travel reservations detected in calendar surfaced for Voyage to manage
- Vesper — Vesper reads Sands schedule briefs at `~/openclaw/data/ocas-vesper/intake/` during briefing generation (cooperative write; Sands pushes to Vesper's intake)


## Journal outputs

- Observation Journal — sands.calendar.query, sands.schedule.free, sands.schedule.conflicts, sands.status
- Action Journal — sands.event.create, sands.event.modify, sands.event.delete, sands.event.undo, sands.logistics.travel, sands.briefing.generate


## Initialization

On first invocation of any Sands command, run `sands.init`:

1. Create `~/openclaw/data/ocas-sands/` directory
2. Write default `config.json` with ConfigBase fields if absent
3. Create empty JSONL files: `decisions.jsonl`, `events.jsonl`
4. Create `~/openclaw/journals/ocas-sands/`
5. Register cron jobs listed below if not already present (check `openclaw cron list` first)
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
```
openclaw cron list
# If sands:morning-brief absent:
openclaw cron add --name sands:morning-brief --cron "0 6 * * *" --session isolated --message "sands.briefing.generate" --light-context --tz America/Los_Angeles
# If sands:evening-brief absent:
openclaw cron add --name sands:evening-brief --cron "0 20 * * *" --session isolated --message "sands.briefing.generate" --light-context --tz America/Los_Angeles
# If sands:conflict-scan absent:
openclaw cron add --name sands:conflict-scan --cron "0 7 * * *" --session isolated --message "sands.schedule.conflicts" --light-context --tz America/Los_Angeles
# If sands:travel-check absent:
openclaw cron add --name sands:travel-check --cron "0 7 * * *" --session isolated --message "sands.logistics.travel" --light-context --tz America/Los_Angeles
# If sands:update absent:
openclaw cron add --name sands:update --cron "0 0 * * *" --session isolated --message "sands.update" --light-context --tz America/Los_Angeles
```


## Self-update

`sands.update` pulls the latest package from the `source:` URL in this file's frontmatter. Runs silently — no output unless the version changed or an error occurred.

1. Read `source:` from frontmatter → extract `{owner}/{repo}` from URL
2. Read local version from `skill.json`
3. Fetch remote version: `gh api "repos/{owner}/{repo}/contents/skill.json" --jq '.content' | base64 -d | python3 -c "import sys,json;print(json.load(sys.stdin)['version'])"`
4. If remote version equals local version → stop silently
5. Download and install:
   ```bash
   TMPDIR=$(mktemp -d)
   gh api "repos/{owner}/{repo}/tarball/main" > "$TMPDIR/archive.tar.gz"
   mkdir "$TMPDIR/extracted"
   tar xzf "$TMPDIR/archive.tar.gz" -C "$TMPDIR/extracted" --strip-components=1
   cp -R "$TMPDIR/extracted/"* ./
   rm -rf "$TMPDIR"
   ```
6. On failure → retry once. If second attempt fails, report the error and stop.
7. Output exactly: `I updated Sands from version {old} to {new}`


## Visibility

public


## Support file map

| File | When to read |
|---|---|
| `references/calendar_config.md` | Before configuring calendars, timezone handling, or Google Places API |
| `references/duration_defaults.md` | Before `sands.event.create`; explains smart duration defaults |
| `references/flexibility_rules.md` | Before `sands.schedule.conflicts`; explains FIXED/FLEXIBLE/AMBIGUOUS classification |
| `references/conflict_detection.md` | Before conflict analysis; explains detection rules and validation |
| `references/recurring_events.md` | Before creating/modifying/deleting recurring events; explains scope handling |
| `references/preparation_signals.md` | Before `sands.briefing.generate`; explains prep signal detection |
| `references/travel_time_logic.md` | Before `sands.logistics.travel`; explains departure resolution and mode inference |
| `references/vesper_emit_format.md` | Before `sands.briefing.generate`; explains InsightProposal payload schema |
