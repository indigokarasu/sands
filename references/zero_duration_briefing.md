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

## A third instance: `_norm_loc` and the embedded newline (2026-09-29)

Same family, different field. `_norm_loc()` split the location string on **commas
only**, so a multi-line Google location — venue on line 1, street on line 2
(`One Medical Group\n1285 4th Street, San Francisco, CA 94158`) — produced the key
`one medical group\n1285 4th street san francisco`, newline intact. A history entry
for the same address that omitted the venue name keyed on
`1285 4th street san francisco`. The two can never match, so "new venue" fires
spuriously. Fix: `re.split(r'[,\n]', loc)`.

**The trap was the diagnosis, not the code.** The first symptom — `Madeline Bell,
MD` at a clinic Jared has attended since April flagged as a new venue — invites
the conclusion "the normalization is broken, fix it." It wasn't. The last One
Medical appointment was 2026-07-20, **71 days before the brief**, outside the
30-day `PREP_LOCATION_HISTORY_DAYS` window, so the flag was the *specified*
behaviour and the brief was correct. Widening the window would have been a policy
change dressed as a bug fix.

**Rule:** before fixing a detection rule, confirm the flagged item is actually a
false positive by querying the underlying data for the true last occurrence. Fix
the key normalization only for the class of defect that IS real (a key that cannot
match its own twin), and record separately that the specific instance is expected.
Verify by asserting the day's output is **byte-identical before and after** — a
"fix" that changes today's correct answer is a policy change wearing a bug-fix
commit message. The docstring now says so explicitly, so the next run does not
re-derive this from scratch.

**Structural note:** this is the third prep-signal defect (the 2026-09-28 location
rule, the naive-datetime history wipe, and now the newline key), all in one
function's neighborhood, all passing the regression suite. The suite asserts the
template *runs*; it does not assert a flagged venue is *correct*. A unit test over
`_norm_loc` with the real multi-line/omitted-name venue pair would have caught the
newline class the day it was written.

## A fourth instance, and the general shape of all four (2026-10-01)

The coverage gap: the morning template hardcoded
`CALENDAR_IDS = [operator, family]` while the token reads **six** calendars. On
2026-10-01 that list dropped 2 of the day's 3 timed events ('SYLVIA and Judy Thank
you card' 09:00-11:00 on TheTopaz; 'House Cleaning' 09:30-11:00 on CC) and the
brief reported a complete-looking day. Not a math defect — a **scope** defect, and
the same shape as the three above: an invariant stated in a reference that the
template never implemented.

**Three runs flagged this gap and none fixed it** (2026-09-30T15:30 travel check,
2026-10-01T13:19 morning brief, and this run). That is the same pattern as the
"enforced by check 3f" claim in my own standing notes: evidence that names a gap
is not a fix for it.

Now `calendarList()` discovery. The general lesson:

**A list of calendars is a fact that expires; code that enumerates is a fact that
does not.** Every defect in this file was a hardcoded value standing in for
something that changes — a 30-day history window, a two-segment location key, a
two-calendar scope. Replace the list with the query.

### The trap: my own regression check passed on a broken feature

Adding discovery introduced a real bug. Conflict scoping was changed to compare
`_source_calendar`, but `parsed_events` never set that key, so both sides were
`None`, `None == None`, and **every cross-calendar pair became a "conflict"** —
3 false conflicts in a live brief.

The regression check I wrote to guard it grepped the template *source* for the
string `_source_calendar') == b.get('_source_calendar')` and reported PASS, because
the string was present. The feature was broken and the test was green.

**Rule: a test that asserts the source contains a string proves the string
exists, not that the code runs.** This is the same failure as the prep-signal
suite above, and it is the reason those defects survived three runs each. Assert
behaviour on real output: same-time events on three different calendars must give
`conflicts_detected == 0` and `cross_calendar_overlaps > 0`. That assertion would
have failed on the broken version immediately.

### The second trap: a fix that changes a correct answer is a policy change

Renaming the calendar label `family` -> `Family` changed every event's `calendar`
field while changing no decision the brief makes. The control that caught it is
the one from the 2026-09-29 section above: pin the old scope, confirm the output
is **identical before and after**, and only then trust the diff. Pinned-scope
output here reproduces the pre-patch artifact exactly, which is what proves the
overlap/free-hours/prep math is untouched and only the coverage grew.

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
