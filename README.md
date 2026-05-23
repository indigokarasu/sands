# 🏜️ Sands

> **Natural-language calendar management across multiple calendars.**

## Why Sands?

Managing a calendar shouldn't require clicking through five menus or remembering API syntax. Sands lets you talk to your calendar the way you'd talk to a person — "move my 2pm to tomorrow," "what does my afternoon look like," "find me 30 minutes before my next meeting." It handles multi-calendar conflict detection, travel time blocks, and recurring events so you don't have to.

Skill packages follow the [agentskills.io](https://agentskills.io/specification) open standard and are compatible with OpenClaw, Hermes Agent, Claude, and any agentskills.io-compliant client.

## Quick Start

```
# Ask about your schedule
"What does my afternoon look like?"

# Create an event
"Schedule a meeting with Alex tomorrow at 2pm"

# Find free time
"When am I free for a 30-minute call this week?"
```

Sands auto-initializes on first use. No manual setup required beyond configuring calendar IDs.

## What It Does

Sands treats your calendar as a structured scheduling surface. It reads across personal and work calendars (work events shown only as busy blocks, titles suppressed), resolves natural-language time references to precise ISO 8601 ranges, and handles recurring events with scope control. Travel time blocks are computed via Google Places Distance Matrix API. Every action is logged with undo support within 24 hours.

## Commands

| Command | Description |
|---|---|
| `sands.query` | Pull events for a time window |
| `sands.create` | Create a new event with conflict pre-check |
| `sands.modify` | Update an existing event |
| `sands.delete` | Cancel and remove an event |
| `sands.free` | Find available time slots |
| `sands.conflicts` | Analyze schedule for conflicts |
| `sands.travel` | Insert travel time blocks |
| `sands.brief` | Generate schedule summary for Vesper |
| `sands.undo` | Revert the most recent action (24h) |
| `sands.status` | Skill health and configuration |
| `sands.update` | Self-update from GitHub source |

## Dependencies

- [Weave](https://github.com/indigokarasu/weave) — attendee identity resolution
- [Elephas](https://github.com/indigokarasu/elephas) — current location context
- [Vesper](https://github.com/indigokarasu/vesper) — consumes schedule briefs
- [Voyage](https://github.com/indigokarasu/voyage) — travel reservations surfaced to Voyage
- Google Calendar API, Google Places API

## Scheduled Tasks

| Job | Schedule | Purpose |
|---|---|---|
| `sands:morning-brief` | `0 6 * * *` | Today's schedule for Vesper |
| `sands:evening-brief` | `0 20 * * *` | Tomorrow's schedule for Vesper |
| `sands:conflict-scan` | `0 7 * * *` | Daily conflict scan |
| `sands:travel-check` | `0 7 * * *` | Check for missing travel blocks |
| `sands:update` | `0 0 * * *` | Self-update |

## Changelog

### v2.1.4 — April 12, 2026
- Briefing time windows, OAuth staleness handling

### v1.2.0 — April 2, 2026
- Background tasks, sands.init and sands.update

### v1.0.0 — March 31, 2026
- Initial release

---

*Sands is part of the [OCAS Agent Suite](https://github.com/indigokarasu).*