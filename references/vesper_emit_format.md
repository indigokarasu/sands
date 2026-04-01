# Vesper Emit Format for Sands

Used by: `sands.brief`

---

## Delivery Path

Write file to:
`~/openclaw/data/ocas-vesper/intake/{proposal_id}.json`

Format: InsightProposal schema (spec-ocas-shared-schemas.md).

---

## Top-Level Schema

```json
{
  "proposal_id": "prop_{hash}",
  "proposal_type": "routine_prediction",
  "description": "[SANDS BRIEF: EVENING | MORNING] {YYYY-MM-DD}",
  "confidence_score": 1.0,
  "supporting_entities": [],
  "supporting_relationships": [],
  "predicted_outcome": null,
  "suggested_follow_up": "{schedule payload — JSON-encoded string; see suggested_follow_up Payload below}",
  "target_skill": null,
  "created_at": "{ISO 8601}"
}
```

---

## `suggested_follow_up` Payload

The `suggested_follow_up` field carries the full schedule payload as a JSON-encoded string.
Vesper must JSON-parse this field to obtain the structured schedule data.
The InsightProposal schema defines this field as `string|null`; encoding the payload as a
string satisfies the type contract while allowing Vesper to carry structured schedule data
through the standard intake path.

```json
{
  "brief_type": "evening | morning",
  "target_date": "YYYY-MM-DD",
  "summary_note": "2-3 sentence narrative characterizing the day.",
  "events": [
    {
      "title": "string",
      "start": "HH:MM",
      "end": "HH:MM",
      "location": "string | null",
      "calendar": "personal | family",
      "conflict": false,
      "conflict_note": "string | null",
      "prep_required": false,
      "prep_note": "string | null",
      "travel_before": false,
      "travel_minutes": null
    }
  ],
  "work_busy_blocks": [
    { "start": "HH:MM", "end": "HH:MM" }
  ],
  "conflicts_detected": 0,
  "prep_items_count": 0
}
```

---

## Evening Brief Rules

- Include all events for the next day
- `summary_note`: 2-3 sentences characterizing the day, flag anything unusual
- Set `conflict: true` and populate `conflict_note` for any conflicts found
- Set `prep_required: true` for events matching preparation signals
- Include `work_busy_blocks` as unavailability overlay (no titles)

## Morning Brief Rules

- Include only events where `prep_required: true`
- `prep_note` should be action-oriented: "Review the agenda", "Confirm reservation"
- `summary_note` should be brief: "You have 2 items that need attention today."
- Skip events with no prep signals entirely
