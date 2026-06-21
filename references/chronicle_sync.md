# Sands → Chronicle Sync

## When to Use

Run `sands.chronicle.sync` to push calendar events into Chronicle as persistent facts.
Called by cron weekly, or manually after significant calendar changes (new travel, appointments added).

## What Gets Synced

| Chronicle predicate | Event criteria |
|---|---|
| `traveling_to` | Multi-day events with non-SF location, OR events with travel keywords (flight, hotel, trip, stay, vacation, visit) + location |
| `had_appointment` | Medical appointments (keywords: doctor, Dr., UCSF, appointment, visit, video visit, patient, therapy, dentist, sleep study) |
| `attended_event` | Significant personal events (birthday, anniversary, celebration, wedding, concert, show, graduation) |

**Skip**: recurring work meetings, all-day busy/blocked/focus markers, cancelled events, generic logistics (payday, tax), duplicates (same summary+date).

## Lookback / Lookforward Window

- Past: 18 months from today
- Future: 6 months from today
- Total window: ~24 months centered on today (weighted toward future for upcoming travel)

## Execution Pattern (Cron-Safe)

Since `execute_code` is blocked in cron, use `write_file` + `terminal`:

```
Step 1: Query calendar events via MCP tools
  - Use mcp_google_workspace_get_events (or direct fallback) for google-workspace-user
  - Also query contact@example.com, family08350553536598846140@group.calendar.google.com
  - Time window: 18 months back → 6 months forward from today
  - pageSize=250, singleEvents=True

Step 2: Classify each event
  - Apply criteria table above
  - Build value text (human-readable, see format below)
  - Set valid_from = event start date, valid_until = event end date (for multi-day)

Step 3: Write classified events to /tmp/sands_events_for_chronicle.json

Step 4: Run ingest script
  terminal("python3 <hermes-root>/scripts/sands_chronicle_sync.py /tmp/sands_events_for_chronicle.json")

Step 5: Update config.json last_chronicle_sync timestamp
```

## Value Text Format

**traveling_to**: `"Trip to {location} — {date_range} — {hotel_or_event}. {context}."`
  Example: `"Trip to Provincetown, MA — Jul 1–5, 2026 — AWOL Hotel Provincetown. Shannon's birthday trip. Flights UA 2356 (SFO→BOS) and UA 2400 (BOS→SFO)."`

**had_appointment**: `"{appointment_type} with {provider} ({org}) — {date} — {location}"`
  Example: `"New patient visit with Dr. Emily Eng (UCSF Ophthalmology) — Apr 15, 2024 — 490 Illinois St, San Francisco"`

**attended_event**: `"{event_name} — {date} — {location_if_any}"`
  Example: `"Wedding Anniversary — Jul 6, 2026"`

## Input JSON Schema

```json
[{
  "google_event_id": "...",          // Google Calendar event ID
  "chronicle_type": "travel",        // travel | medical | personal | professional
  "predicate": "traveling_to",       // traveling_to | had_appointment | attended_event
  "value": "...",                    // Human-readable fact text
  "valid_from": "YYYY-MM-DD",        // Event start date
  "valid_until": "YYYY-MM-DD",       // Event end date (null for single-day)
  "confidence": 0.9,                 // 0.0–1.0
  "location": "...",                 // Raw location string (or null)
  "source_summary": "...",
  "source_calendar": "personal|thetopaz|family"            // Original calendar event title
}]
```

## Deduplication

The ingest script deactivates all prior `external_sands` facts for the predicates in the batch before re-importing. This means each sync is a clean re-import of the current window — no stale facts accumulate.

## Chronicle DB

`<hermes-home>/commons/db/chronicle/chronicle.db`
Script: `<hermes-root>/scripts/sands_chronicle_sync.py`

## Auth Note

Direct Python OAuth for Google Calendar is stale (see `config.json auth_status: MCP_ONLY`).
Always use MCP calendar tools (`mcp_google_workspace_get_events`) when running in a Claude session.
The Python ingest script only writes to Chronicle DB — it does NOT need calendar auth.

## Calendars to Query

| Calendar | ID |
|---|---|
| Personal | `google-workspace-user` |
| TheTopaz | `contact@example.com` |
| Family | `family08350553536598846140@group.calendar.google.com` |

Skip: Work (`owner.operator@<employer>.com`) — read-only free/busy only, no event details.
