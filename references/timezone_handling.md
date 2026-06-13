# Timezone Handling for Calendar Queries

Used by: all Sands commands that construct time_min / time_max for `get_events`.

---

## The Pacific Time Pitfall

`default_timezone` in config.json is `America/Los_Angeles`, which alternates between:

| Period | Offset | Abbrev |
|---|---|---|
| 2nd Sunday Mar – 1st Sunday Nov | `-07:00` | PDT (daylight saving) |
| 1st Sunday Nov – 2nd Sunday Mar | `-08:00` | PST (standard) |

When building RFC3339 timestamps for `time_min` and `time_max`, you MUST check which offset applies to the **target date** (the day you're querying), not today's date. The two dates can straddle the DST boundary.

**Wrong** (hardcoded offset):
```
time_min: 2026-05-30T00:00:00-08:00  # Always PST — wrong for May
```
On May 30, this actually queries 1:00 AM PDT midnight, missing the first hour.

**Wrong** (current-day offset applied to target date):
```
# Today is November (PST -08:00), so the agent uses -08:00 for all dates
time_min: 2026-06-15T00:00:00-08:00  # Should be -07:00 for June
```

**Right** (target-date-specific offset):
```
# May 30 2026 → PDT → -07:00
time_min: 2026-05-30T00:00:00-07:00
time_max: 2026-05-31T00:00:00-07:00
```

Concretely: May 30 midnight PDT = `2026-05-30T07:00:00Z`. Using `-08:00` would give you `2026-05-30T08:00:00Z`, which is 1:00 AM local time — you'd miss any 12:00–1:00 AM events entirely.

## DST Transition Days

On the days clocks change, be extra careful:

- **Spring forward** (2nd Sunday March, e.g. March 8 2026): 2:00 AM → 3:00 AM. The hour 02:00–02:59 does not exist.
- **Fall back** (1st Sunday November, e.g. November 1 2026): 2:00 AM → 1:00 AM. The hour 01:00–01:59 occurs twice; the offset is ambiguous for that hour unless you specify it.

For querying entire days, use UTC midnight-to-midnight equivalent to avoid ambiguity:
```
# "All of March 8 2026 in Pacific time"
time_min: 2026-03-08T08:00:00Z   # midnight PST (before spring forward)
time_max: 2026-03-09T07:00:00Z   # midnight PDT (after spring forward)
```

## Practical Rule for Travel-Check and Briefing

For `sands.logistics.travel` (tomorrow's events) and `sands.briefing.generate`:

1. Determine tomorrow's date.
2. Check if it falls in PDT or PST period.
3. Build time_min = tomorrow midnight local with correct offset.
4. Build time_max = day-after-tomorrow midnight local with correct offset.
5. If in doubt, use UTC equivalents: midnight PDT = 07:00Z, midnight PST = 08:00Z.

## Parsing Event Times from API Responses

**This is a separate pitfall from query construction.** Even with correct query timestamps, the *response* `dateTime` values may be in UTC or the event's own timezone. You MUST call `.astimezone(PDT)` (or the correct local tz) on parsed datetimes before displaying HH:MM to the user. See `references/direct_calendar_access.md` § "Parsing Event Times from API Responses" for the correct code pattern and a concrete example of the bug (showing `01:00` instead of `18:00` for a dinner event).
