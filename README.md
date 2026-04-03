# 🏜️ Sands

Sands manages calendar events through natural language -- creating, querying, modifying, and deleting events across personal and work calendars. It detects scheduling conflicts with flexibility classification, finds free time slots, inserts travel time blocks via Google Places API, and emits structured schedule briefs to Vesper for morning and evening briefings.

---

## Overview

Sands treats your calendar as a structured scheduling surface. It reads across personal and work calendars (work events shown only as busy blocks, titles suppressed), resolves natural-language time references to precise ISO 8601 ranges, and handles recurring events with scope control. Travel time blocks are computed via Google Places Distance Matrix API with mode-aware routing (driving, transit, walking, bicycling). Every calendar action is logged to events.jsonl with undo support within 24 hours.

## Commands

| Command | Description |
|---|---|
| `sands.query` | Pull events for a time window (today, this week, a specific date) |
| `sands.create` | Create a new event from natural language with conflict pre-check |
| `sands.modify` | Update an existing event with post-modify conflict re-check |
| `sands.delete` | Cancel and remove an event with travel block cleanup |
| `sands.free` | Find available time slots for a given duration |
| `sands.conflicts` | Analyze upcoming schedule for conflicts with flexibility classification |
| `sands.travel` | Insert travel time block between events via Google Places API |
| `sands.brief` | Generate structured schedule summary for Vesper briefings |
| `sands.undo` | Revert the most recent calendar action (within 24 hours) |
| `sands.status` | Skill health and configuration summary |
| `sands.update` | Pull latest from GitHub source (preserves journals and data) |

## Setup

`sands.init` runs automatically on first invocation and creates all required directories, config.json, JSONL files, and registers background tasks. No manual setup is required beyond configuring calendar IDs and Google Places API key in config.json.

## Dependencies

**OCAS Skills**
- [Weave](https://github.com/indigokarasu/weave) -- attendee identity resolution and current location context
- [Elephas](https://github.com/indigokarasu/elephas) -- current location context from Chronicle
- [Vesper](https://github.com/indigokarasu/vesper) -- consumes Sands schedule briefs for morning/evening briefings
- [Voyage](https://github.com/indigokarasu/voyage) -- travel reservations detected in calendar are surfaced for Voyage

**External**
- Google Calendar API (read/write for personal calendars, read-only for work calendar)
- Google Places API (location resolution and travel time calculation)

## Scheduled Tasks

| Job | Schedule | Command | Purpose |
|---|---|---|---|
| `sands:morning-brief` | `0 6 * * *` | `sands.brief` | Today's schedule brief for Vesper morning briefing |
| `sands:evening-brief` | `0 20 * * *` | `sands.brief` | Tomorrow's schedule brief for Vesper evening briefing |
| `sands:conflict-scan` | `0 7 * * *` | `sands.conflicts` | Daily conflict scan for upcoming 7 days |
| `sands:travel-check` | `0 7 * * *` | `sands.travel` | Check next day's events for missing travel blocks |
| `sands:update` | `0 0 * * *` | `sands.update` | Self-update from GitHub source |

## Changelog

### v1.2.0 -- April 2, 2026
- Added background tasks for brief, conflict scan, travel check, and self-update
- Added sands.init and sands.update commands
- Fixed missing scheduled_tasks in skill.json

### v1.1.0 -- April 2, 2026
- Added sands.delete, sands.free, sands.undo commands
- Timezone awareness with dual-timezone display
- Recurring event handling with scope control
- Multi-mode travel (driving, transit, walking, bicycling)
- Smart duration defaults, attendee management, morning brief day-at-a-glance

### v1.0.0 -- March 31, 2026
- Initial release: query, create, modify, conflicts, travel, brief, status
- Work calendar busy overlay, Google Places integration, conflict classification
- Preparation signal detection, journal output for every command

---

*Sands is part of the [OpenClaw Agent Suite](https://github.com/indigokarasu) -- a collection of interconnected skills for personal intelligence, autonomous research, and continuous self-improvement. Each skill owns a narrow responsibility and communicates with others through structured signal files, shared journals, and Chronicle, a long-term knowledge graph that accumulates verified facts over time.*
