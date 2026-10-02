#!/usr/bin/env python3
import os
OPERATOR_EMAIL = os.environ.get("OCAS_OPERATOR_EMAIL", "operator@example.com")
"""
Sands Evening Briefing (cron-compatible generator)

Mirrors templates/sands_briefing_morning.py but adapted for EVENING mode:
- Target date = TOMORROW (not today)
- brief_type = 'evening'
- proposal_type = 'routine_prediction' (NO prep-signal checking for future dates)
- Zero-duration events (start == end) are EXCLUDED from conflict detection and
  free-hours math, and surfaced as warnings. See references/zero_duration_briefing.md.

This is a pure generator: it queries calendars, computes the brief, writes
/tmp/sands_evening_briefing.json, prints a summary, and emits the Vesper
InsightProposal payload on stdout after the '---BRIEFING_PAYLOAD_JSON---' marker.

The calling skill run is responsible for Sands run-completion persistence
(evidence.jsonl, action.jsonl, dated brief JSON, config.json last_evening_brief).
See references/zero_duration_briefing.md for the full persistence recipe used
in the 2026-07-23 cron run.

Usage:
    python3 templates/sands_briefing_evening.py

Flags:
    --help, -h   Print this help and exit 0 WITHOUT querying any calendar.
    --dry-run     Query calendars and print the summary, but do NOT write
                  /tmp/sands_evening_briefing.json or the payload marker.

Environment:
    OCAS_OPERATOR_EMAIL, OCAS_AGENT_EMAIL   accounts to try, in order
    OCAS_FAMILY_CALENDAR_ID                  family calendar id
    HERMES_HOME                              defaults to ~/.hermes

Output:
    - /tmp/sands_evening_briefing.json — full Vesper InsightProposal payload
    - stdout: summary, then ---BRIEFING_PAYLOAD_JSON--- + JSON

Exit codes:
    0  briefing generated, or --help printed
    1  all accounts failed auth (degraded; no payload, no JSON written)
    2  usage error
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

_HELP_ARGS = {"--help", "-h"}
_DRY_RUN = "--dry-run" in sys.argv[1:]
# Guard BEFORE any import with side effects or network/auth work, so probing
# --help can never trigger a live calendar query or write the brief JSON.
if set(sys.argv[1:]) & _HELP_ARGS:
    print((__doc__ or "").strip() or "Usage: python3 sands_briefing_evening.py")
    sys.exit(0)
if _DRY_RUN:
    sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a != "--dry-run"]

sys.path.insert(0, os.path.expanduser(os.environ.get("HERMES_HOME", "~/.hermes")) + "/scripts")

# Interpreter-agnostic dependency shim (2026-09-29): google-api-python-client and
# google-auth are installed under the SYSTEM interpreter's dist-packages
# (/usr/local/lib/python3.14/dist-packages), not the `python3` first on PATH.
# Cron runs hit ModuleNotFoundError: No module named 'google' there. Rather than
# hardcode a python path in every cron command, append the well-known
# dist-packages dirs that actually contain googleapiclient/ before importing.
import glob as _glob
for _cand in _glob.glob("/usr/local/lib/python3.*/dist-packages") + _glob.glob(
    "/usr/lib/python3*/dist-packages"
):
    if _cand not in sys.path:
        sys.path.append(_cand)

from google_auth_mcp import get_service

# =============================================================================
# CONFIGURATION — mirror config.json primary_calendar_ids
# =============================================================================
def _require_env(name):
    """Return the env value or exit with a clear error.

    This template previously defaulted to 'operator@example.com' and a
    redacted '<family-calendar-id>' placeholder. Both reach the API and 404
    with an error that reads like a transient fault instead of a config bug.
    The evening brief of 2026-09-30T04:19 hit exactly that path.
    """
    val = os.environ.get(name, "").strip()
    if not val or "<" in val or ">" in val or "example.com" in val:
        sys.exit(f"ABORT: {name} is unset or still a placeholder: {val!r}. "
                 f"Set it to a real calendar id before generating a briefing.")
    return val


# Fallback scope only; the EFFECTIVE set is DISCOVERED from calendarList()
# after auth. Same coverage fix as the morning template (2026-10-01): a
# hardcoded 2-calendar list dropped 2 of 3 timed events from the brief.
CALENDAR_IDS = [
    _require_env("OCAS_OPERATOR_EMAIL"),
    _require_env("OCAS_FAMILY_CALENDAR_ID"),
]
WORK_CALENDAR_ID = ""
ACCOUNTS_TO_TRY = [a for a in [os.environ.get("OCAS_OPERATOR_EMAIL", "").strip(),
                               os.environ.get("OCAS_AGENT_EMAIL", "").strip()] if a]
WORKING_HOURS = {"start": "09:00", "end": "18:00"}

_HOLIDAY_CALENDAR_IDS = {"en.usa#holiday@group.v.calendar.google.com"}
_CALENDAR_LABELS = {}


def _discover_calendars(service):
    """Return (ids, ok). Falls back to the configured pair if discovery fails."""
    explicit = os.environ.get("OCAS_CALENDAR_IDS", "").strip()
    if explicit:
        ids = [c.strip() for c in explicit.split(",") if c.strip()]
        for cid in ids:
            _CALENDAR_LABELS.setdefault(
                cid, "Family" if "family" in cid
                else ("Personal" if cid == CALENDAR_IDS[0] else cid))
        return ids, True
    exclude = {e.strip() for e in os.environ.get("OCAS_CALENDAR_EXCLUDE", "").split(",") if e.strip()}
    exclude |= _HOLIDAY_CALENDAR_IDS
    work = os.environ.get("OCAS_WORK_CALENDAR_ID", "").strip() or WORK_CALENDAR_ID
    if work:
        exclude.add(work)  # SKILL.md: work calendar is overlay-only, never a primary
    try:
        items = service.calendarList().list(maxResults=250).execute().get("items", [])
    except Exception as e:
        print(f"  calendarList discovery FAILED ({str(e)[:60]}); using configured pair only")
        return list(CALENDAR_IDS), False
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
        return list(CALENDAR_IDS), False
    return ids, True

# =============================================================================
# DATE SETUP — evening brief targets TOMORROW. Offset derived per TARGET date
# via zoneinfo, never hardcoded (see the DST gotcha in SKILL.md).
# =============================================================================
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo(os.environ.get("OCAS_TIMEZONE", "America/Los_Angeles"))
now = datetime.now(LOCAL_TZ)
today_str = now.strftime('%Y-%m-%d')
tomorrow = now + timedelta(days=1)
tomorrow_str = tomorrow.strftime('%Y-%m-%d')
tomorrow_display = tomorrow.strftime('%A, %B %d, %Y')


def _offset_for(date_str: str) -> str:
    """RFC3339 UTC offset for midnight of date_str in the target timezone."""
    off = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=LOCAL_TZ).utcoffset()
    secs = int(off.total_seconds() if off else 0)
    sign = '+' if secs >= 0 else '-'
    secs = abs(secs)
    return f"{sign}{secs // 3600:02d}:{(secs % 3600) // 60:02d}"


day_after_tomorrow = tomorrow + timedelta(days=1)
time_min = f"{tomorrow_str}T00:00:00{_offset_for(tomorrow_str)}"
time_max = f"{day_after_tomorrow.strftime('%Y-%m-%d')}T00:00:00{_offset_for(day_after_tomorrow.strftime('%Y-%m-%d'))}"

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

CALENDAR_IDS, discovery_ok = _discover_calendars(calendar)
print(f"Calendar scope: {len(CALENDAR_IDS)} calendar(s)"
      + ("" if discovery_ok else "  (discovery incomplete)"))
for cid in CALENDAR_IDS:
    print(f"  - {_CALENDAR_LABELS.get(cid, cid)}")

# =============================================================================
# HELPERS
# =============================================================================
def to_min(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:])

def span_minutes(start_hhmm, end_hhmm):
    """(start_min, end_min). Treat end <= start as crossing midnight (e.g.
    19:30->00:00 -> end = 1440). NOTE: only call on DURATIONAL events; a
    zero-duration '12:45'->'12:45' would wrongly expand to a 24h span here."""
    s = to_min(start_hhmm)
    e = to_min(end_hhmm)
    if e <= s:
        e += 1440
    return s, e

def fromisoformat_safe(s):
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
# Recorded in the payload so a truncated brief is self-evident to a consumer
# instead of looking complete.
coverage_note = (f"{len(CALENDAR_IDS)} calendars queried"
                 + ("" if discovery_ok else " (discovery incomplete)"))

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

    src = ev.get('_source_calendar', '')
    # Label from the real calendar. A 'family' substring test collapsed every
    # non-family calendar into 'personal', so same-calendar conflict detection
    # compared equal labels for events on different calendars.
    cal_label = _CALENDAR_LABELS.get(src) or (
        'Family' if 'family' in src else ('Personal' if src == CALENDAR_IDS[0] else src))
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
# CONFLICT DETECTION (intra-day overlaps) — EXCLUDE zero-duration events
# =============================================================================
timed_events = [e for e in parsed_events if e['is_timed']]
zero_duration_events = [e for e in parsed_events if e.get('zero_duration')]
durational_events = [e for e in timed_events if not e.get('zero_duration')]
conflicts_detected = 0
cross_calendar_overlaps = 0
event_conflict_notes = {}
event_busy_context = {}

# Same SKILL.md hard boundary the morning template adopted on 2026-09-30:
# overlap between DIFFERENT people's calendars is not a conflict by default.
# The operator shares a household; a family-calendar event at the same time as
# a personal one means two people are each busy somewhere. Only count a
# conflict for same-calendar overlap, or when the operator is expected at both.
OPERATOR_EMAIL_EVE = os.environ.get("OCAS_OPERATOR_EMAIL", "").strip()


def _operator_expected_at_eve(ev):
    if ev.get('organizer') == OPERATOR_EMAIL_EVE:
        return True
    for at in ev.get('attendees', []) or []:
        if at.get('self') and at.get('responseStatus') != 'declined':
            return True
        if at.get('email') == OPERATOR_EMAIL_EVE and at.get('responseStatus') != 'declined':
            return True
    return False


def _eve_cal_name(c):
    return _CALENDAR_LABELS.get(c) or ('the family calendar' if 'family' in c else 'your calendar')


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
        both_expected = _operator_expected_at_eve(a) and _operator_expected_at_eve(b)
        if same_calendar or both_expected:
            conflicts_detected += 1
            event_conflict_notes.setdefault(id(a), []).append(
                f'Overlaps with "{b["summary"]}" ({overlap_min} min)')
            event_conflict_notes.setdefault(id(b), []).append(
                f'Overlaps with "{a["summary"]}" ({overlap_min} min)')
        else:
            cross_calendar_overlaps += 1
            event_busy_context.setdefault(id(a), []).append(
                f'Same time on {_eve_cal_name(b.get("_source_calendar", ""))}: '
                f'"{b["summary"]}" ({overlap_min} min)')
            event_busy_context.setdefault(id(b), []).append(
                f'Same time on {_eve_cal_name(a.get("_source_calendar", ""))}: '
                f'"{a["summary"]}" ({overlap_min} min)')

# =============================================================================
# FREE HOURS (within working hours; skip zero-duration events)
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

# =============================================================================
# BUILD OUTPUT (evening: prep_required always False — no prep signals for future dates)
# =============================================================================
output_events = []
timed_starts = [e['start'] for e in parsed_events if e['is_timed']]
first_event_time = timed_starts[0] if timed_starts else ""
last_event_time = durational_events[-1]['end'] if durational_events else ""
personal_count = sum(1 for e in parsed_events if e['calendar'] == 'personal')
family_count = sum(1 for e in parsed_events if e['calendar'] == 'family')

for ev in parsed_events:
    is_conflict = id(ev) in event_conflict_notes
    conflict_note = "; ".join(event_conflict_notes[id(ev)]) if is_conflict else None
    output_events.append({
        'title': ev['summary'],
        'start': ev['start'],
        'end': ev['end'],
        'location': ev.get('location'),
        'calendar': ev.get('calendar', 'personal'),
        'htmlLink': ev.get('htmlLink', ''),
        'all_day': ev['all_day'],
        'zero_duration': ev.get('zero_duration', False),
        'conflict': is_conflict,
        'conflict_note': conflict_note,
        'busy_context': "; ".join(event_busy_context[id(ev)]) if id(ev) in event_busy_context else None,
        'prep_required': False,
        'prep_note': None,
        'travel_before': False,
        'travel_minutes': None
    })

total_events = len(parsed_events)
zero_duration_count = len(zero_duration_events)

if total_events == 0:
    summary_note = f"Tomorrow ({tomorrow_display}) has no events scheduled."
elif total_events == 1:
    only = parsed_events[0]
    summary_note = f"Tomorrow ({tomorrow_display}) has one event: \"{only['summary']}\""
    if only['is_timed']:
        summary_note += f" at {only['start']}"
    summary_note += "."
else:
    time_range = ""
    if durational_events and first_event_time:
        time_range = f" from {first_event_time}"
        if last_event_time:
            time_range += f" to {last_event_time}"
    conflict_str = ""
    if conflicts_detected:
        conflict_str = f". {conflicts_detected} conflict{'s' if conflicts_detected > 1 else ''} detected"
    zero_dur_str = ""
    if zero_duration_count:
        zero_dur_str = (f". {zero_duration_count} zero-duration event{'s' if zero_duration_count > 1 else ''} "
                        f"(data-quality warning — no end time set)")
    summary_note = (
        f"Tomorrow ({tomorrow_display}) has {total_events} events"
        f"{time_range}, ~{free_hours:.1f} free working hours{conflict_str}{zero_dur_str}."
    )

payload = {
    'brief_type': 'evening',
    'target_date': tomorrow_str,
    'summary_note': summary_note,
    'day_overview': {
        'total_events': total_events,
        'personal_events': personal_count,
        'family_events': family_count,
        'first_event': first_event_time,
        'last_event': last_event_time,
        'free_hours': round(free_hours, 1),
        'prep_items_count': 0,
        'zero_duration_warnings': zero_duration_count
    },
    'events': output_events,
    'work_busy_blocks': [],
    'conflicts_detected': conflicts_detected,
    'cross_calendar_overlaps': cross_calendar_overlaps,
    'calendars_queried': CALENDAR_IDS,
    'calendar_discovery_complete': discovery_ok,
    'coverage_note': coverage_note,
    'prep_items_count': 0
}

briefing_payload = {
    "proposal_id": f"prop_sands_evening_{tomorrow_str.replace('-', '')}",
    "proposal_type": "routine_prediction",
    "description": f"[SANDS BRIEF: EVENING] {tomorrow_str}",
    "confidence_score": 1.0,
    "supporting_entities": [],
    "supporting_relationships": [],
    "predicted_outcome": None,
    "suggested_follow_up": json.dumps(payload),
    "target_skill": None,
    "created_at": now.strftime('%Y-%m-%dT%H:%M:%S%z')
}

if _DRY_RUN:
    print("(dry-run) /tmp/sands_evening_briefing.json NOT written")
else:
    with open('/tmp/sands_evening_briefing.json', 'w') as f:
        json.dump(payload, f, indent=2)

print(f"\n{'='*55}")
print(f"EVENING BRIEFING — {tomorrow_display}")
print(f"{'='*55}")
print(f"Events: {total_events} (personal {personal_count}, family {family_count}) | "
      f"Conflicts: {conflicts_detected} | Prep: 0 | Zero-dur: {zero_duration_count}")
print(f"Free hours: {free_hours:.1f}")
print(f"Auth: {working_account}" + (" (fallback)" if auth_fallback_used else ""))
if calendar_errors:
    print(f"Calendar errors: {list(calendar_errors.keys())}")
print(f"\n{summary_note}")
print(f"\nJSON: /tmp/sands_evening_briefing.json")
print("---BRIEFING_PAYLOAD_JSON---")
print(json.dumps(briefing_payload))
