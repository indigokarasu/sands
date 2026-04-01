# ocas-sands

**Schedule and Navigation System** — OpenClaw Agent Skill

Sands manages your calendar: querying events, creating and modifying appointments, detecting conflicts, inserting travel time blocks via Google Places API, and emitting structured schedule signals to Vesper for morning and evening briefings.

---

## Commands

| Command | Description |
|---|---|
| `sands.query` | Pull events for a time window (today, this week, a specific date) |
| `sands.create` | Create a new event from natural language |
| `sands.modify` | Update an existing event |
| `sands.conflicts` | Analyze a time window for conflicts with flexibility classification |
| `sands.travel` | Insert a travel time block between consecutive events via Google Places API |
| `sands.brief` | Generate a structured schedule summary for Vesper (evening or morning mode) |
| `sands.status` | Return skill health and configuration summary |

---

## Calendar Sources

Sands reads from two types of calendar sources configured in `config.json`:

- **Primary calendars** (`primary_calendar_ids`) — personal and family Google Calendars (read/write)
- **Work calendar** (`work_calendar_id`) — overlaid as "Busy (work)" blocks; titles never exposed (free/busy read only)

---

## Configuration

On first use, create `~/openclaw/data/ocas-sands/config.json`:

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

A Google Places API key is required for `sands.travel`. If unavailable, Sands will prompt for a manual travel time estimate rather than silently guessing.

---

## Skill Cooperation

Sands cooperates with other OpenClaw skills when present but never depends on them:

- **Vesper** — consumes `sands.brief` output for morning/evening briefings
- **Weave / Elephas** — location context for travel calculations
- **Voyage** — surfaces travel reservations detected in the calendar; Sands does not book them

---

## Storage Layout

```
~/openclaw/data/ocas-sands/
  config.json
  decisions.jsonl
~/openclaw/journals/ocas-sands/
  YYYY-MM-DD/{run_id}.json
```

---

## Part of the OpenClaw Agent System

[OpenClaw](https://github.com/indigokarasu) · Author: Indigo Karasu
