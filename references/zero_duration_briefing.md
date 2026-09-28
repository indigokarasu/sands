# Zero-Duration Events in Sands Briefings

## The bug (caught 2026-07-23, evening-brief run)

An event with `start == end` (e.g. `"12:45"` → `"12:45"`) is a **zero-duration**
artifact — almost always a UCSF MyChart double-import where the end time was
never captured. The skill's `span_minutes()` helper has a midnight-crossing
guard:

```python
def span_minutes(start_hhmm, end_hhmm):
    s = to_min(start_hhmm)
    e = to_min(end_hhmm)
    if e <= s:          # 12:45 -> 12:45 triggers this
        e += 1440       # expands to a 24-hour span (765 -> 2205)
    return s, e
```

For a zero-duration event this guard wrongly expands it into a **24-hour busy
span**. Two consequences:

1. **False conflicts** — the 24h span overlaps every later event. In the
   2026-07-23 run a `12:45 Appointment` was reported as overlapping `Gym`
   (13:30–15:30) by 120 minutes. There was no real conflict.
2. **Polluted free-hours** — `calc_free_hours` treated the 24h span as a full-day
   block, deflating the free-hours number.

## The fix

Exclude zero-duration events from BOTH conflict detection and free-hours math
**before** calling `span_minutes`. Flag them as `zero_duration` warnings in the
report instead.

```python
# at parse time
zero_duration = is_timed and (start_hhmm == end_hhmm)

# conflict detection: only compare durational events
durational_events = [e for e in timed_events if not e.get('zero_duration')]

# free hours: skip zero-duration events
if ev.get('zero_duration'):
    continue
```

Both `templates/sands_briefing_morning.py` and `templates/sands_briefing_evening.py`
exclude zero-duration events this way. The evening template was written correct from
the start; **the morning template's guard was claimed here since 2026-07-23 but was
never actually in the file** — found absent during the 2026-09-27 morning-brief run
and patched. A reference asserting a fix shipped is not evidence the fix shipped:
diff the template against this recipe before relying on it.

## The same class of defect, second instance (2026-09-28)

`check_prep_signals()` in the morning template flagged **any** event with a
location as prep_required, while `references/preparation_signals.md` counts a
location only when the venue is new in the last 30 days or a travel block was
inserted — and explicitly exempts solo personal activity and repeated titles with
no external attendees. Effect: 4 of 5 events flagged on 2026-09-28; after the fix,
2 (both genuine new-venue flags).

Two traps while fixing it, both of which the regression script caught and a visual
inspection of the brief would not have:

1. **Empty history reads as "everything is new."** Building the 30-day history with
   `datetime.fromisoformat(bare_date).utcoffset()` returns `None` (naive datetime),
   so the query raised and the history silently emptied — every located event then
   flagged as a new venue, which looks like the bug got worse, not better. Attach
   the timezone explicitly: `.replace(tzinfo=LOCAL_TZ)`.
2. **Venue strings vary cosmetically.** The same venue appears as `... CA` and
   `... CA 94133` and with a trailing `, USA`. Compare normalized street+city keys,
   or every event reads as a new venue.

**Generalized rule:** a rule implemented in `references/*.md` but not in the template
is a latent defect, and a reference claiming an implementation exists is worth
zero until diffed against the file. When a template change adds a new query or
derived data, make the regression script fail on the *degraded* path, not just the
success path — the empty-history bug passed every eyeball check and only failed
because the script asserts stdout contains no `ERROR`.

## Evening-brief run-completion persistence (2026-07-23 recipe)

The briefing templates are pure generators. The calling cron run must persist:

1. Dated brief JSON →
   `{journal_dir}/{target_date}_evening_brief.json` (full record: observation,
   events, summary_note, briefing_payload).
2. `evidence.jsonl` — append via
   `scripts/append_jsonl.py` (NEVER `write_file` — it overwrites).
   Fields: `timestamp`, `command: sands.briefing.generate`, `mode: evening`,
   `target_date`, `status`, `degraded`, `auth_account`, `auth_fallback_used`,
   `total_events`, `conflicts_detected`, `zero_duration_warnings`, `free_hours`.
3. `action.jsonl` — same `append_jsonl.py` helper (briefing.generate is an
   Action Journal command).
4. `config.json` — set `last_evening_brief` to the run timestamp.

Cron-mode note: `execute_code` is blocked in cron. Write the generator to
`/tmp/`, run it with `terminal("python3 /tmp/...py")`, read its stdout/JSON.
