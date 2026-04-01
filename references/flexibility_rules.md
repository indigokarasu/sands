# Event Flexibility Classification Rules

Used by: `sands.conflicts`

Classify each event in a conflict pair as FIXED, FLEXIBLE, or AMBIGUOUS.

---

## FIXED — cannot be easily rescheduled

Apply FIXED when any of these are true:
- External attendees present (attendee email domain differs from user's)
- Title contains: call, meeting, interview, sync, standup, review (with others),
  appointment, doctor, dentist, flight, train, reservation, class, course,
  workshop, concert, show, game, lesson
- Event has a conference link (Google Meet, Zoom, Teams, Webex)
- Event is recurring (any recurrence pattern)
- Work calendar busy block

## FLEXIBLE — likely movable with low friction

Apply FLEXIBLE when all of these are true:
- No external attendees
- Title contains: gym, workout, run, walk, errand, personal, reading,
  focus time, deep work, solo lunch, groceries
- No conference link
- No fixed external venue with a reservation

## AMBIGUOUS — signals are mixed

Apply AMBIGUOUS when:
- Classification signals conflict (e.g., "gym class" — "class" suggests fixed,
  but could be a drop-in)
- Insufficient metadata to determine
- Title is generic ("meeting", "event") with no attendee data

Present AMBIGUOUS with an explanation of the uncertainty.

---

## Output Format Per Conflict

```
CONFLICT: [Event A] overlaps [Event B] by X minutes

  Event A: [title] — FIXED
  Reason: external attendees, conference link

  Event B: [title] — FLEXIBLE
  Reason: no attendees, personal activity keyword

  Suggested resolution: Move [Event B].
  Candidate times: [offer 2-3 alternatives if determinable]
```

Never suggest moving a FIXED event unless both events are FIXED, in which case
surface the conflict for the user to resolve manually.
