# Conflict Detection

Run conflict detection:
- Automatically after `sands.event.create` and `sands.event.modify`
- On demand via `sands.schedule.conflicts`

## Definition

A conflict exists when:
- Two events overlap by any amount of time, OR
- Travel time to an event would need to begin before the preceding event ends, OR
- The same event appears on multiple calendars (cross-calendar duplicate), OR
- The same event appears twice on the *same* calendar (intra-calendar duplicate)

All-day events are treated as low-priority background blocks: they do not trigger conflicts with timed events unless the user explicitly asks.

## Cross-Calendar Duplicates

When the same event appears on multiple calendars (e.g., Personal + Family), detect by matching `summary` + `start` time + `location`. Normalize to local time before comparing — different calendars may store the same event with different UTC offsets (e.g., one at `-07:00`, another at `Z`), making them appear to be at different times when they are actually the same.

Flag as severity **DUPLICATE**. Recommend removing the copy from the non-canonical calendar (typically the family/shared calendar, keeping the primary calendar's copy).

## Intra-Calendar Duplicates

The same event can appear *twice on the same calendar*, typically caused by:
- **Booking platform double-imports** — Fresha, UCSF MyChart, and similar platforms sometimes create both a detailed event and a separate auto-generated summary event at the same time.
- **Calendar sync artifacts** — Syncing the same booking source via two different paths (e.g., email invite + calendar feed).

Detect by matching `summary.lower()` + `start_local` within the same `cal_id`. When found:
- If one has correct duration and the other is zero-duration → the zero-duration one is almost certainly the artifact. Recommend deleting it.
- If both have identical duration and details → recommend deleting one (they're the same booking).
- If both have different details (e.g., one has location, one doesn't) → keep the more detailed one, delete the sparser one.

Flag as severity **DUPLICATE** with `intra_calendar: true` in the evidence log.

## Resolution

Do not auto-resolve conflicts. Present them with a flexibility assessment and candidate resolutions for the user to choose from. See `references/flexibility_rules.md`.

## Zero-Duration Events

A zero-duration event has `start == end` (e.g., `2026-06-11T14:45:00-07:00` for both). These do not produce overlap conflicts by the standard definition, but they are almost always a data quality issue — the end time was likely not set correctly during creation.

**Action:** Flag as a `zero_duration` warning in the conflict report. Include the event title, start time, and a note suggesting the user verify the intended duration. Do not treat as a conflict — treat as a data integrity note.

Example:
```
WARNING: [NEW PATIENT VISIT with Niti Shahi] zero_duration: start == end at 2026-06-11T14:45-07:00. The description mentions 3:00 PM — the end time may not have been set correctly.
```

## Validation

Before creating any event:
- Confirm no exact-duplicate title+time exists on that calendar
- Confirm the slot is not blocked by a work busy period (warn, do not block)
- Confirm the end time is after the start time (non-zero duration)

Before inserting travel:
- Gap must be >= calculated travel time + buffer. If not, surface conflict instead of creating a truncated or overlapping travel block.

## Detection Algorithm (Cron-Compatible Pattern)

```python
# 1. Fetch all timed events (exclude all-day) from relevant calendars
# 2. Normalize all start/end to naive UTC for comparison
# 3. Sort by start_utc
# 4. Check all pairs for overlap: a.start < b.end AND b.start < a.end
# 5. For each overlap, calculate overlap_minutes
# 6. Classify each event per flexibility_rules.md
# 7. Check for zero-duration (duration_min == 0)
# 8. Check for cross-calendar duplicates: group by (summary.lower(), start_local, location.lower()) across different cal_ids
# 9. Check for intra-calendar duplicates: group by (summary.lower(), start_local) within the same cal_id