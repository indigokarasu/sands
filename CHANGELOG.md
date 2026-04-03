# CHANGELOG

## [2.0.0] - 2026-04-02

### Changed
- SKILL.md rewritten to comply with OCAS architecture standards (528 → ~280 lines)
- Commands renamed to hierarchical dot-notation: sands.calendar.query, sands.event.create, sands.event.modify, sands.event.delete, sands.event.undo, sands.schedule.free, sands.schedule.conflicts, sands.logistics.travel, sands.briefing.generate
- Cron registration updated to use correct openclaw cron CLI syntax (--cron, --session isolated, --message, --light-context, --tz)
- Background task commands updated to match new hierarchical names
- Section ordering aligned with build template

### Added
- Frontmatter fields: source, install (were missing)
- Run completion, Hard boundaries, Self-update, Support file map sections
- sands.journal command
- requires.credentials in skill.json for GOOGLE_PLACES_API_KEY
- New reference files: calendar_config.md, recurring_events.md, conflict_detection.md

### Removed
- Inline detail sections from SKILL.md moved to references/

## [1.2.0] - 2026-04-02

### Added
- Background tasks: sands:morning-brief, sands:evening-brief, sands:conflict-scan, sands:travel-check, sands:update
- sands.init command for directory/config/cron setup on first run
- sands.update command for self-update from GitHub

### Fixed
- Missing scheduled_tasks in skill.json

## [1.1.1] - 2026-04-02

### Changed
- Fixed missing skill_type and filesystem fields in skill.json

## [1.1.0] - 2026-04-02

### Added
- sands.delete, sands.free, sands.undo commands
- Timezone awareness, recurring event handling, multi-mode travel
- Smart duration defaults, attendee management, morning brief day-at-a-glance

## [1.0.0] - 2026-03-31

### Added
- Initial release: query, create, modify, conflicts, travel, brief, status
- Work calendar busy overlay, Google Places integration, conflict classification
