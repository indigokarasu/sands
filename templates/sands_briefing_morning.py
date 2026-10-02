#!/usr/bin/env python3
import os
"""
Sands Morning Briefing Template (cron-compatible)

Generates a Vesper-ready morning briefing for today's events:
- Multi-account OAuth fallback (owner → indigo)
- Multi-calendar query (configurable CALENDAR_IDS)
- Cross-calendar deduplication (summary + start time)
- Intra-calendar overlap detection
- Preparation signal flagging
- Free-hours calculation within working hours
- Vesper InsightProposal JSON payload output

Usage:
    1. Copy this template: cp templates/sands_briefing_morning.py /tmp/
    2. Set CALENDAR_IDS to match your config.json primary_calendar_ids
    3. Run: python3 /tmp/sands_briefing_morning.py
    4. Read JSON from /tmp/sands_morning_briefing.json

Flags:
    --help, -h   Print this help and exit 0 WITHOUT querying any calendar.
    --dry-run     Query calendars and print the summary, but do NOT write
                  /tmp/sands_morning_briefing.json or the payload marker.

Environment:
    OCAS_OPERATOR_EMAIL, OCAS_AGENT_EMAIL   accounts to try, in order
    OCAS_FAMILY_CALENDAR_ID                  family calendar id
    HERMES_HOME                              defaults to ~/.hermes

Output:
    - /tmp/sands_morning_briefing.json — full Vesper emit payload (suggested_follow_up)
    - stdout: human-readable summary line, then ---BRIEFING_PAYLOAD_JSON--- + JSON

Exit codes:
    0  briefing generated, or --help printed
    1  all accounts failed auth (degraded; no payload, no JSON written)
    2  usage error
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

_HELP_ARGS = {"--help", "-h"}
_DRY_RUN = "--dry-run" in sys.argv[1:]
# Guard BEFORE any import with side effects or network/auth work, so probing
# --help can never trigger a live calendar query.
if set(sys.argv[1:]) & _HELP_ARGS:
    print((__doc__ or "").strip() or "Usage: python3 sands_briefing_morning.py")
    sys.exit(0)
if _DRY_RUN:
    sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a != "--dry-run"]

sys.path.insert(0, os.path.expanduser(os.environ.get("HERMES_HOME", "~/.hermes")) + "/scripts")

# Interpreter-agnostic dependency shim (2026-09-29) — see the same block in
# templates/sands_briefing_evening.py. Cron's default `python3` has no
# google-api-python-client; it lives in the system interpreter's
# dist-packages. Append the real dirs instead of hardcoding a python path.
import glob as _glob
for _cand in _glob.glob("/usr/local/lib/python3.*/dist-packages") + _glob.glob(
    "/usr/lib/python3*/dist-packages"
):
    if _cand not in sys.path:
        sys.path.append(_cand)

from google_auth_mcp import get_service

# =============================================================================
# CONFIGURATION — update these to match config.json
# =============================================================================
def _require_env(name):
    """Return the env value or exit with a clear error.

    A redacted placeholder or a default email reaching the API produces a 404
    that reads like a transient fault. Fail loudly at startup instead.
    (See references/gotchas.md -> "Never ship a redacted <placeholder>".)
    """
    val = os.environ.get(name, "").strip()
    if not val or "<" in val or ">" in val or "example.com" in val:
        sys.exit(f"ABORT: {name} is unset or still a placeholder: {val!r}. "
                 f"Set it to a real calendar id before generating a briefing.")
    return val


OPERATOR_EMAIL = _require_env("OCAS_OPERATOR_EMAIL")
FAMILY_CALENDAR_ID = _require_env("OCAS_FAMILY_CALENDAR_ID")

# Fallback scope only. The EFFECTIVE calendar set is DISCOVERED from
# calendarList() after auth — see _discover_calendars(). See the coverage
# rationale below before adding anything here.
CALENDAR_IDS = [OPERATOR_EMAIL, FAMILY_CALENDAR_ID]
WORK_CALENDAR_ID = ""  # leave empty if no work calendar
ACCOUNTS_TO_TRY = [a for a in [OPERATOR_EMAIL, os.environ.get("OCAS_AGENT_EMAIL", "").strip()] if a]
WORKING_HOURS = {"start": "09:00", "end": "18:00"}

# ============================================================================
# CALENDAR COVERAGE — why this is discovered rather than hardcoded
# ============================================================================
# The original CALENDAR_IDS was a fixed two-calendar list (operator + Family).
# The operator token can actually read SIX calendars, and on 2026-10-01 that
# hardcoded list dropped 2 of the day's 3 timed events: 'SYLVIA and Judy Thank
# you card' 09:00-11:00 (TheTopaz) and 'House Cleaning' 09:30-11:00 (CC). The
# brief reported a complete-looking day built on a partial query, and nothing in
# the output signalled the truncation.
#
# The gap was FLAGGED, not fixed, by three consecutive runs (2026-09-30T15:30
# travel check, 2026-10-01T13:19 morning brief, and again on this run). Naming a
# known gap in evidence is not closing it — the same lesson as the
# "enforced by check 3f" claim. Enumerating calendarList() closes it
# structurally: a calendar added tomorrow is picked up with no template edit.
#
# Housekeeping:
#   OCAS_CALENDAR_IDS      comma-separated explicit set; pins scope, skips discovery
#   OCAS_CALENDAR_EXCLUDE  comma-separated ids to drop from discovery
# Holidays are excluded by default: all-day only, and the SKILL.md all-day
# boundary says they must never mark a day busy.
_HOLIDAY_CALENDAR_IDS = {"en.usa#holiday@group.v.calendar.google.com"}
_CALENDAR_LABELS = {}


def _discover_calendars(service):
    """Return (ids, ok). Falls back to the configured pair if discovery fails."""
    explicit = os.environ.get("OCAS_CALENDAR_IDS", "").strip()
    if explicit:
        ids = [c.strip() for c in explicit.split(",") if c.strip()]
        for cid in ids:
            # No calendarList summary is available for a pinned id, so use the
            # same human label the discovered path produces. Falling back to the
            # raw id here changed the 'calendar' field of every event without
            # changing any of the math, which reads as a behaviour change in
            # artifact diffs.
            _CALENDAR_LABELS.setdefault(
                cid, "Family" if "family" in cid else ("Personal" if cid == OPERATOR_EMAIL else cid))
        return ids, True
    exclude = {e.strip() for e in os.environ.get("OCAS_CALENDAR_EXCLUDE", "").split(",") if e.strip()}
    exclude |= _HOLIDAY_CALENDAR_IDS
    work = os.environ.get("OCAS_WORK_CALENDAR_ID", "").strip() or WORK_CALENDAR_ID
    if work:
        exclude.add(work)  # SKILL.md: work calendar is read/overlay only, never a primary
    try:
        items = service.calendarList().list(maxResults=250).execute().get("items", [])
    except Exception as e:
        print(f"  calendarList discovery FAILED ({str(e)[:60]}); using configured pair only")
        return [OPERATOR_EMAIL, FAMILY_CALENDAR_ID], False
    ids = []
    for c in items:
        cid = c.get("id", "")
        if not cid or cid in exclude:
            continue
        if c.get("accessRole") not in ("owner", "writer", "reader"):
            continue
        ids.append(cid)
        _CALENDAR_LABELS[cid] = c.get("summary") or c.get("summaryOverride") or cid
    if not ids:
        print("  calendarList discovery returned nothing usable; using configured pair")
        return [OPERATOR_EMAIL, FAMILY_CALENDAR_ID], False
    return ids, True

# =============================================================================
# DATE SETUP — offset derived per TARGET date via zoneinfo, never hardcoded.
# The SKILL.md DST gotcha applies to these templates too: an event window built
# with the wrong -07:00/-08:00 offset returns no events or wrong-day events.
# =============================================================================
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo(os.environ.get("OCAS_TIMEZONE", "America/Los_Angeles"))
now = datetime.now(LOCAL_TZ)
today_str = now.strftime('%Y-%m-%d')
tomorrow_str = (now + timedelta(days=1)).strftime('%Y-%m-%d')


def _offset_for(date_str: str) -> str:
    """RFC3339 UTC offset for midnight of date_str in the target timezone."""
    off = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=LOCAL_TZ).utcoffset()
    total = int(off.total_seconds())
    sign = '+' if total >= 0 else '-'
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


time_min = f"{today_str}T00:00:00{_offset_for(today_str)}"
time_max = f"{tomorrow_str}T00:00:00{_offset_for(tomorrow_str)}"

# =============================================================================
# OAUTH: FIND WORKING ACCOUNT (multi-account fallback)
# =============================================================================
calendar = None
working_account = None
auth_fallback_used = False

for account in ACCOUNTS_TO_TRY:
    try:
        cal = get_service(
            'calendar', 'v3',
            ['https://www.googleapis.com/auth/calendar.readonly'],
            account=account
        )
        cal.calendarList().list(maxResults=1).execute()
        calendar = cal
        working_account = account
        break
    except Exception as e:
        err_str = str(e)
        # Both invalid_grant (403) and 400 Bad Request from oauth2.googleapis.com
        # signal dead credentials. Move to next account.
        if 'invalid_grant' in err_str or '400' in err_str:
            print(f"Account {account}: dead token ({err_str[:80]})")
        else:
            print(f"Account {account}: unexpected error: {err_str[:80]}")
        continue

if calendar is None:
    print("DEGRADED: All OAuth tokens invalid. Cannot generate briefing.")
    sys.exit(1)

if working_account != ACCOUNTS_TO_TRY[0]:
    auth_fallback_used = True

print(f"Using account: {working_account}" + (" (FALLBACK)" if auth_fallback_used else ""))

# Replace the hardcoded pair with everything this account can actually read.
# Must happen BEFORE the event query, and the event query must use the
# discovered set — asserting coverage after querying would report the gap
# without closing it.
CALENDAR_IDS, discovery_ok = _discover_calendars(calendar)
print(f"Calendar scope: {len(CALENDAR_IDS)} calendar(s)"
      + ("" if discovery_ok else "  (discovery incomplete)"))
for cid in CALENDAR_IDS:
    print(f"  - {_CALENDAR_LABELS.get(cid, cid)}")

# =============================================================================
# HELPERS
# =============================================================================
def to_min(hhmm):
    """Convert 'HH:MM' to minutes since midnight."""
    return int(hhmm[:2]) * 60 + int(hhmm[3:])

def span_minutes(start_hhmm, end_hhmm):
    """Return (start_min, end_min) for a timed event. Treat end <= start as
    crossing midnight (e.g. 19:30-00:00 -> end = 1440) so overlaps and busy
    spans compute correctly. Naive parsing of '00:00' as minute 0 hides real
    conflicts between a late event and an after-midnight event."""
    s = to_min(start_hhmm)
    e = to_min(end_hhmm)
    if e <= s:
        e += 1440
    return s, e

def fromisoformat_safe(s):
    """Parse ISO datetime string handling Z suffix and timezone offsets."""
    if s.endswith('Z'):
        s = s.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(s)
    except Exception:
        if 'T' in s and ('+' in s[10:] or s[10:].count('-') > 0):
            idx = s.rfind('+') if '+' in s[10:] else s.rfind('-', 10)
            base = s[:idx]
            tz = s[idx:]
            sign = 1 if tz[0] == '+' else -1
            hours = int(tz[1:3])
            minutes = int(tz[4:6])
            offset = timedelta(hours=sign * hours, minutes=sign * minutes)
            base_dt = datetime.fromisoformat(base)
            return base_dt.replace(tzinfo=timezone(offset))
        return datetime.fromisoformat(s)

# =============================================================================
# QUERY CALENDARS
# =============================================================================
all_events = []
calendar_errors = {}

for cal_id in CALENDAR_IDS:
    try:
        result = calendar.events().list(
            calendarId=cal_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime',
            showDeleted=False,
            maxResults=250
        ).execute()
        events = result.get('items', [])
        for ev in events:
            ev['_source_calendar'] = cal_id
        all_events.extend(events)
        print(f"  {cal_id}: {len(events)} events")
    except Exception as e:
        calendar_errors[cal_id] = str(e)
        print(f"  {cal_id}: ERROR {e}")

work_busy_blocks = []
if WORK_CALENDAR_ID:
    try:
        result = calendar.events().list(
            calendarId=WORK_CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime',
            showDeleted=False,
            maxResults=250
        ).execute()
        for ev in result.get('items', []):
            if 'dateTime' in ev['start']:
                work_busy_blocks.append({
                    'start': ev['start']['dateTime'],
                    'end': ev['end']['dateTime']
                })
    except Exception as e:
        calendar_errors['work'] = str(e)

# =============================================================================
# DEDUPLICATION (case-insensitive summary + start time)
# =============================================================================
seen = {}
deduped_events = []

for ev in all_events:
    key = (
        ev.get('summary', '').strip().lower(),
        ev.get('start', {}).get('dateTime', ev.get('start', {}).get('date', ''))
    )
    if key in seen:
        continue
    seen[key] = ev
    deduped_events.append(ev)

all_events = deduped_events

# =============================================================================
# PARSE EVENTS
# =============================================================================
parsed_events = []

for ev in all_events:
    start_data = ev.get('start', {})
    end_data = ev.get('end', {})

    all_day = 'date' in start_data
    is_timed = 'dateTime' in start_data

    if is_timed:
        start_dt = fromisoformat_safe(start_data['dateTime'])
        end_dt = fromisoformat_safe(end_data['dateTime'])
        start_local = start_dt.astimezone(LOCAL_TZ)
        end_local = end_dt.astimezone(LOCAL_TZ)
        start_hhmm = start_local.strftime('%H:%M')
        end_hhmm = end_local.strftime('%H:%M')
        sort_key = f"{start_local.hour:02d}{start_local.minute:02d}"
    else:
        start_hhmm = "All day"
        end_hhmm = "All day"
        sort_key = "0000"

    # Calendar identity must come from the REAL calendar, not from whether the
    # id happens to contain the substring 'family'. The old test labeled the CC
    # and TheTopaz calendars 'personal' too, so the same-calendar conflict
    # branch compared equal labels for events on genuinely different calendars
    # and manufactured false conflicts.
    src = ev.get('_source_calendar', '')
    cal_label = _CALENDAR_LABELS.get(src) or ('Family' if 'family' in src
                                              else ('Personal' if src == OPERATOR_EMAIL else src))

    zero_duration = is_timed and (start_hhmm == end_hhmm)

    parsed_events.append({
        'summary': ev.get('summary', '(untitled)'),
        'description': ev.get('description', ''),
        'start': start_hhmm,
        'end': end_hhmm,
        'sort_key': sort_key,
        'location': ev.get('location'),
        'calendar': cal_label,
        'htmlLink': ev.get('htmlLink', ''),
        'all_day': all_day,
        'is_timed': is_timed,
        'zero_duration': zero_duration,
        'attendees': ev.get('attendees', []),
        'organizer': ev.get('organizer', {}).get('email', ''),
        '_source_calendar': ev.get('_source_calendar', ''),
        'start_data': start_data,
        'end_data': end_data,
    })

parsed_events.sort(key=lambda e: (0 if e['all_day'] else 1, e['sort_key']))

# =============================================================================
# CONFLICT DETECTION — zero-duration events excluded BEFORE span_minutes().
# span_minutes() has a midnight-crossing guard that expands start == end into a
# 24h busy span, manufacturing a false conflict against every later event.
# See references/zero_duration_briefing.md.
#
# CALENDAR SCOPE: per the SKILL.md hard boundary, overlap between DIFFERENT
# people's calendars is NOT a conflict by default — the operator shares a
# household, so a family-calendar event at the same time as a personal one
# means two people are each busy somewhere. Only (a) two events overlapping on
# the SAME calendar, or (b) the operator being expected at both, is a conflict.
# This loop used to count every overlap regardless of calendar, which reported
# Shannon's mammogram as Jared's double-booking. Observed on 2026-09-29 and
# again 2026-09-30 (three consecutive runs flagged it in evidence instead of
# fixing it); a reference naming the boundary is worth zero until the code
# implements it. Cross-calendar overlaps are still recorded, as busy context.
# =============================================================================
timed_events = [e for e in parsed_events if e['is_timed']]
zero_duration_events = [e for e in timed_events if e.get('zero_duration')]
durational_events = [e for e in timed_events if not e.get('zero_duration')]
conflicts_detected = 0
cross_calendar_overlaps = 0
event_conflict_notes = {}
event_busy_context = {}


def _operator_expected_at(ev):
    """True when Jared is on the hook for this event.

    An event organized on the shared family calendar is normally a housemate's
    commitment. It becomes the operator's when he is an attendee answering
    anything but 'declined', or when he organized it. Google marks the
    calendar owner's own copy with attendees[].self=True.
    """
    if ev.get('organizer') == OPERATOR_EMAIL:
        return True
    for a in ev.get('attendees', []) or []:
        if a.get('self') and a.get('responseStatus') != 'declined':
            return True
        if a.get('email') == OPERATOR_EMAIL and a.get('responseStatus') != 'declined':
            return True
    return False


for i in range(len(durational_events)):
    for j in range(i + 1, len(durational_events)):
        a = durational_events[i]
        b = durational_events[j]
        a_s, a_e = span_minutes(a['start'], a['end'])
        b_s, b_e = span_minutes(b['start'], b['end'])

        overlap_start = max(a_s, b_s)
        overlap_end = min(a_e, b_e)
        overlap_min = overlap_end - overlap_start

        if overlap_min <= 0:
            continue

        same_calendar = a.get('_source_calendar') == b.get('_source_calendar')
        both_expected = _operator_expected_at(a) and _operator_expected_at(b)
        note = f'Overlaps with "{b["summary"]}" ({overlap_min} min)'

        if same_calendar or both_expected:
            conflicts_detected += 1
            event_conflict_notes.setdefault(id(a), []).append(note)
            event_conflict_notes.setdefault(id(b), []).append(
                f'Overlaps with "{a["summary"]}" ({overlap_min} min)')
        else:
            cross_calendar_overlaps += 1
            # Label each side with the OTHER event's actual calendar. Hardcoding
            # "family"/"your" here assumes a is always the family event, which
            # inverted the labels the moment the personal event sorted first —
            # and it silently collapsed every non-family calendar into one bucket
            # once discovery brought CC / TheTopaz into scope.
            def _cal_name(c):
                return _CALENDAR_LABELS.get(c) or ('the family calendar' if 'family' in c
                                                    else 'your calendar')
            event_busy_context.setdefault(id(a), []).append(
                f'Same time on {_cal_name(b.get("_source_calendar", ""))}: '
                f'"{b["summary"]}" ({overlap_min} min)')
            event_busy_context.setdefault(id(b), []).append(
                f'Same time on {_cal_name(a.get("_source_calendar", ""))}: '
                f'"{a["summary"]}" ({overlap_min} min)')

# =============================================================================
# PREPARATION SIGNALS
# =============================================================================
PREP_TITLE_KEYWORDS = [
    'review', 'prep', 'preparation', 'presentation', 'briefing', 'interview',
    'pitch', 'demo', 'proposal', 'debrief', 'kickoff', 'onboarding',
    'performance', 'evaluation', 'assessment', 'report', 'workshop', 'panel', 'keynote'
]

# references/preparation_signals.md -> "Do NOT Flag as Prep-Required":
# solo personal activity with no attendees needs no prep.
PREP_SOLO_EXEMPT_KEYWORDS = [
    'gym', 'workout', 'errand', 'groceries', 'personal', 'reading',
    'focus time', 'deep work', 'meditation', 'journaling', 'solo lunch'
]

# How far back to look for "has this location appeared before?".
PREP_LOCATION_HISTORY_DAYS = 30


def _norm_loc(loc):
    """Normalize a location string to a venue key so cosmetic differences
    (missing zip, ', USA' suffix, house-number padding) don't read as a new
    venue. Key on street + city — the first two comma-separated segments.

    Split on newlines as well as commas. Google multi-line locations carry the
    venue name on line 1 and the street on line 2 (`One Medical Group\\n1285
    4th Street, San Francisco, CA 94158`), so a comma-only split leaves an
    embedded newline inside the key. History entries that omit the venue name
    then key on `1285 4th street san francisco` while today's event keys on
    `one medical group\\n1285 4th street san francisco` — the two can never
    match. Collapsing the whitespace at least makes the key stable.

    Note: this hardens the key; it does NOT make an out-of-window venue
    familiar. One Medical (1285 4th St) last appeared 2026-07-20, outside the
    30-day history window, so flagging it as a new venue is the specified
    behaviour, not a false positive. A wider window is a policy change, not a
    bug fix.
    """
    if not loc:
        return ''
    segs = [s.strip() for s in re.split(r'[,\n]', loc) if s.strip()]
    keep = segs[:2] if len(segs) >= 2 else segs
    return ' '.join(keep).lower()


def _build_location_history(service, calendar_ids, local_tz, today_str):
    """Venues seen in the PRECEDING `PREP_LOCATION_HISTORY_DAYS`, strictly
    before today, so an event's own occurrence can't mark its venue as
    familiar. Returns (set_of_venue_keys, set_of_repeated_titles).

    A bounded extra query per calendar (~1s for both) — the new-location
    rule is otherwise undecidable. Failure is non-fatal: an empty history
    degrades to "every located event looks new", which is loud but safe.
    """
    venues, titles = set(), {}
    for cal_id in calendar_ids:
        try:
            # fromisoformat() on a bare date yields a NAIVE datetime, whose
            # utcoffset() is None — that silently emptied this history before.
            # Attach the target timezone explicitly.
            today_midnight = datetime.fromisoformat(today_str).replace(tzinfo=local_tz)
            start = today_midnight - timedelta(days=PREP_LOCATION_HISTORY_DAYS)
            end = today_midnight
            tmin = f"{start.strftime('%Y-%m-%d')}T00:00:00{_fmt_off(start.utcoffset())}"
            tmax = f"{end.strftime('%Y-%m-%d')}T00:00:00{_fmt_off(end.utcoffset())}"
            items = service.events().list(
                calendarId=cal_id, timeMin=tmin, timeMax=tmax,
                singleEvents=True, orderBy='startTime', showDeleted=False,
                maxResults=2500,
            ).execute().get('items', [])
        except Exception as e:
            print(f"  location-history {cal_id}: ERROR {str(e)[:60]}")
            continue
        for ev in items:
            key = _norm_loc(ev.get('location'))
            if key:
                venues.add(key)
            title = (ev.get('summary') or '').strip().lower()
            if title:
                titles[title] = titles.get(title, 0) + 1
    return venues, {t for t, n in titles.items() if n >= 3}


def _fmt_off(off):
    total = int(off.total_seconds())
    sign = '+' if total >= 0 else '-'
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def check_prep_signals(event, known_venues, recurring_titles):
    """Returns (bool, reason_str) for whether event needs prep.

    Implements references/preparation_signals.md, including its "do NOT flag"
    clauses. A location alone is NOT a prep signal — it qualifies only when the
    venue is new in the last 30 days, or a travel block was inserted before
    the event.
    """
    title = event['summary'].strip()
    title_lower = title.lower()
    attendees = event.get('attendees', [])

    # --- Do NOT flag: recurring, repeated, no external attendees ---
    external = any(
        '@' in a.get('email', '') and a.get('email', '').split('@')[1] not in
        ('gmail.com', 'googlemail.com')
        for a in attendees
    )
    if title_lower in recurring_titles and not external:
        return False, ""

    # --- Do NOT flag: solo personal activity ---
    if not external and any(kw in title_lower for kw in PREP_SOLO_EXEMPT_KEYWORDS):
        return False, ""

    # --- Do flag: strong signals ---
    for kw in PREP_TITLE_KEYWORDS:
        if kw in title_lower:
            return True, f"'{kw}' in title"

    if len(attendees) >= 3:
        return True, f"{len(attendees)} attendees"
    if external:
        return True, "External attendee"

    # --- Location signals (narrow, per the reference) ---
    if event.get('travel_before'):
        return True, "Travel block inserted before this event"
    loc_key = _norm_loc(event.get('location'))
    if loc_key and loc_key not in known_venues:
        return True, f"New venue (not on either calendar in {PREP_LOCATION_HISTORY_DAYS} days)"

    return False, ""

# =============================================================================
# FREE HOURS
# =============================================================================
def calc_free_hours(events, work_start="09:00", work_end="18:00"):
    ws = int(work_start[:2]) * 60 + int(work_start[3:])
    we = int(work_end[:2]) * 60 + int(work_end[3:])

    busy = []
    for ev in events:
        if not ev['is_timed']:
            continue
        if ev.get('zero_duration'):
            continue
        s, e = span_minutes(ev['start'], ev['end'])
        busy.append((max(s, ws), min(e, we)))
    busy = [b for b in busy if b[1] > b[0]]

    if not busy:
        return (we - ws) / 60

    busy.sort()
    merged = []
    for s, e in busy:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    total_busy = sum(max(0, e - s) for s, e in merged)
    return max(0, (we - ws - total_busy) / 60)

free_hours = calc_free_hours(parsed_events, WORKING_HOURS["start"], WORKING_HOURS["end"])
zero_duration_count = len(zero_duration_events)

# Venue + repeat-title history backing the prep rules' "new location" test.
known_venues, recurring_titles = _build_location_history(
    calendar, CALENDAR_IDS, LOCAL_TZ, today_str
)
print(f"  history: {len(known_venues)} known venues, "
      f"{len(recurring_titles)} repeated titles")

# =============================================================================
# BUILD OUTPUT
# =============================================================================
output_events = []
prep_count = 0
timed_starts = [e['start'] for e in parsed_events if e['is_timed']]
first_event_time = timed_starts[0] if timed_starts else ""
last_event_time = timed_events[-1]['end'] if timed_events else ""

for ev in parsed_events:
    is_conflict = id(ev) in event_conflict_notes
    conflict_note = "; ".join(event_conflict_notes[id(ev)]) if is_conflict else None
    prep_needed, prep_reason = check_prep_signals(ev, known_venues, recurring_titles)
    if prep_needed:
        prep_count += 1

    output_events.append({
        'title': ev['summary'],
        'start': ev['start'],
        'end': ev['end'],
        'location': ev.get('location'),
        'calendar': ev.get('calendar', 'personal'),
        'htmlLink': ev.get('htmlLink', ''),
        'all_day': ev['all_day'],
        'conflict': is_conflict,
        'conflict_note': conflict_note,
        'busy_context': "; ".join(event_busy_context[id(ev)]) if id(ev) in event_busy_context else None,
        'zero_duration': ev.get('zero_duration', False),
        'prep_required': prep_needed,
        'prep_note': prep_reason if prep_needed else None,
        'travel_before': False,
        'travel_minutes': None
    })

# =============================================================================
# SUMMARY NOTE
# =============================================================================
today_display = now.strftime('%A, %B %d, %Y')
total_events = len(parsed_events)

if total_events == 0:
    summary_note = f"Today is {today_display}. No events scheduled."
elif total_events == 1:
    only = parsed_events[0]
    summary_note = f"Today is {today_display}. One event: \"{only['summary']}\""
    if only['is_timed']:
        summary_note += f" at {only['start']}"
    summary_note += "."
else:
    time_range = ""
    if timed_events and first_event_time:
        time_range = f" from {first_event_time}"
        if last_event_time:
            time_range += f" to {last_event_time}"

    prep_str = ""
    if prep_count:
        prep_str = f". {prep_count} item{'s' if prep_count > 1 else ''} need preparation"

    zero_dur_str = ""
    if zero_duration_count:
        zero_dur_str = (f". {zero_duration_count} zero-duration event{'s' if zero_duration_count > 1 else ''} "
                        f"excluded from conflict and free-hours math")

    conflict_str = ""
    if conflicts_detected:
        conflict_str = f". {conflicts_detected} conflict{'s' if conflicts_detected > 1 else ''} detected"

    summary_note = (
        f"Today is {today_display}. {total_events} events scheduled"
        f"{time_range}, ~{free_hours:.1f} free working hours"
        f"{prep_str}{zero_dur_str}{conflict_str}."
    )

# =============================================================================
# OUTPUT
# =============================================================================
payload = {
    'brief_type': 'morning',
    'target_date': today_str,
    'summary_note': summary_note,
    'day_overview': {
        'total_events': total_events,
        'first_event': first_event_time,
        'last_event': last_event_time,
        'free_hours': round(free_hours, 1),
        'prep_items_count': prep_count
    },
    'events': output_events,
    'work_busy_blocks': [],
    'conflicts_detected': conflicts_detected,
    'cross_calendar_overlaps': cross_calendar_overlaps,
    'zero_duration_warnings': zero_duration_count,
    'prep_items_count': prep_count,
    'calendars_queried': CALENDAR_IDS,
    'calendar_discovery_complete': discovery_ok,
    'uncovered_calendars': [],
    'calendar_errors': calendar_errors,
    'auth_account': working_account,
    'auth_fallback_used': auth_fallback_used,
    'generated_at': now.isoformat()
}

if _DRY_RUN:
    print("(dry-run) /tmp/sands_morning_briefing.json NOT written")
else:
    with open('/tmp/sands_morning_briefing.json', 'w') as f:
        json.dump(payload, f, indent=2)

print(f"\n{'='*55}")
print(f"MORNING BRIEFING — {today_display}")
print(f"{'='*55}")
print(f"Events: {total_events} | Conflicts: {conflicts_detected} | Prep: {prep_count} | Zero-dur: {zero_duration_count}")
print(f"Free hours: {free_hours:.1f}")
print(f"Auth: {working_account}" + (" (fallback)" if auth_fallback_used else ""))
if calendar_errors:
    print(f"Calendar errors: {list(calendar_errors.keys())}")
print(f"\n{summary_note}")
print(f"\nJSON: /tmp/sands_morning_briefing.json")
