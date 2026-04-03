# Conflict Detection

Run conflict detection:
- Automatically after `sands.event.create` and `sands.event.modify`
- On demand via `sands.schedule.conflicts`

## Definition

A conflict exists when:
- Two events overlap by any amount of time, OR
- Travel time to an event would need to begin before the preceding event ends

All-day events are treated as low-priority background blocks: they do not trigger conflicts with timed events unless the user explicitly asks.

## Resolution

Do not auto-resolve conflicts. Present them with a flexibility assessment and candidate resolutions for the user to choose from. See `references/flexibility_rules.md`.

## Validation

Before creating any event:
- Confirm no exact-duplicate title+time exists on that calendar
- Confirm the slot is not blocked by a work busy period (warn, do not block)

Before inserting travel:
- Gap must be >= calculated travel time + buffer. If not, surface conflict instead of creating a truncated or overlapping travel block.
