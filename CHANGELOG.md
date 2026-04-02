## [1.1.1] - 2026-04-02

### Changed
- Fixed missing skill_type and filesystem fields in skill.json; added YAML frontmatter to SKILL.md

# Changelog

All notable changes to ocas-sands will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html):
patch = bugfix or text, minor = new commands, major = new features.

---

## [1.1.0] — 2026-04-02

### Added
- `sands.delete` — cancel/delete events with associated travel block cleanup and recurring event scope support
- `sands.free` — find available time slots for a given duration with optional constraints (day-of-week, time-of-day, working hours)
- `sands.undo` — revert the most recent calendar action (create, modify, or delete) within a 24-hour window
- Timezone awareness — resolve and display times in the user's current timezone; dual-timezone display when event and user timezones differ
- Recurring event handling — create, modify, and delete with scope control (this occurrence / this and future / all)
- All-day and multi-day event support in `sands.create` and `sands.query`
- Multi-mode travel in `sands.travel` — driving, transit, walking, bicycling with mode-aware emoji titles and distance-based inference
- Smart duration defaults for event creation — keyword-based mapping (see `references/duration_defaults.md`)
- Attendee management in `sands.modify` — add/remove attendees by name with Weave resolution
- Morning brief day-at-a-glance — full event list with `day_overview` summary, not just prep items
- `working_hours`, `default_timezone`, and `default_travel_mode` config fields
- `previous_values` and `recurrence_scope` fields in `events.jsonl` for undo support

### Changed
- Morning brief `proposal_type` changed from `routine_prediction` to `preparation_checklist`
- `sands.conflicts` treats all-day events as low-priority background blocks (no conflict with timed events unless explicitly asked)
- `config_version` bumped to `"2"` to reflect new fields

### Fixed
- README storage layout now includes `events.jsonl` (was missing in v1.0.0)
- `events.jsonl` action enum now includes `deleted` (was missing despite delete being a trigger condition)

---

## [1.0.0] — 2026-03-31

### Added
- `sands.query` — pull events for a natural-language time window
- `sands.create` — create events from natural language with conflict pre-check
- `sands.modify` — update existing events with post-modify conflict re-check
- `sands.conflicts` — analyze a time window with FIXED / FLEXIBLE / AMBIGUOUS classification
- `sands.travel` — insert travel time blocks via Google Places Distance Matrix API
- `sands.brief` — emit InsightProposal to Vesper intake (evening and morning modes)
- `sands.status` — skill health and configuration summary
- Work calendar busy overlay (titles suppressed, shown as "Busy (work)")
- Location-aware travel departure resolution (prior event → system location → user prompt)
- Preparation signal detection for morning briefs
- Journal output for every command run
