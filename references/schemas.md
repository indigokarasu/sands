## Storage Layout

```
{agent_root}/commons/data/ocas-sands/
  config.json
  decisions.jsonl
  events.jsonl
  evidence.jsonl
  intents.jsonl
  journals/
    action.jsonl
    observation.jsonl
```

**Journal path correction (2026-10-03).** This section previously listed
`{agent_root}/commons/journals/ocas-sands/YYYY-MM-DD/{run_id}.json`, and
SKILL.md's Initialization checklist names
`{agent_root}/commons/journals/ocas-sands/{action,observation}.jsonl`. Neither
exists. The journals every Sands run actually writes live **inside DATA_DIR**
at `journals/action.jsonl` (46 records as of 2026-10-03) and
`journals/observation.jsonl`. The `journals/YYYY-MM-DD_*_brief.json` files
alongside them are per-brief artifacts, not the JSONL. `persist_brief.py` and
every travel check write to the DATA_DIR path. A run that follows the documented
path creates a second, empty journal set and reports persistence that nothing
reads — the file exists, the records do not.


## Default Configuration

```json
{
  "skill_id": "ocas-sands",
  "skill_version": "2.2.0",
  "config_version": "2",
  "created_at": "",
  "updated_at": "",
  "primary_calendar_ids": ["primary"],
  "work_calendar_id": "",
  "travel_buffer_minutes": 10,
  "default_travel_mode": "driving",
  "conflict_lookahead_days": 7,
  "default_timezone": "America/Los_Angeles",
  "working_hours": { "start": "09:00", "end": "18:00" },
  "retention": { "days": 90, "max_records": 10000 },
  "last_travel_check": "",
  "last_evening_brief": "",
  "last_morning_brief": "",
  "last_conflict_scan": ""
}
```

## Runtime Config Fields (added by cron jobs)

The following fields are added/updated by scheduled cron runs and are not part of the initial default config:

| Field | Updated by | Format |
|-------|------------|--------|
| `last_travel_check` | `sands.logistics.travel` (cron `sands:travel-check`) | RFC3339 timestamp |
| `last_evening_brief` | `sands.briefing.generate` (cron `sands:evening-brief`) | RFC3339 timestamp |
| `last_morning_brief` | `sands.briefing.generate` (cron `sands:morning-brief`) | RFC3339 timestamp |
| `last_conflict_scan` | `sands.schedule.conflicts` (cron `sands:conflict-scan`) | RFC3339 timestamp |

These fields enable gap detection per the recovery contract (spec-ocas-recovery.md).

## OKRs

skill_okrs:
  - name: conflict_detection_accuracy
    metric: fraction of actual conflicts correctly identified and surfaced
    direction: maximize
    target: 0.95
    evaluation_window: 30_runs
  - name: travel_time_api_success_rate
    metric: fraction of sands.logistics.travel runs completing via Google Places API
    direction: maximize
    target: 0.90
    evaluation_window: 30_runs
  - name: calendar_write_success_rate
    metric: fraction of create/modify runs with no calendar API error
    direction: maximize
    target: 0.98
    evaluation_window: 30_runs
  - name: schedule_adherence
    metric: fraction of cron-scheduled runs that execute within 5 minutes of their scheduled time
    direction: maximize
    target: 0.95
    evaluation_window: 30_runs
  - name: data_integrity
    metric: fraction of runs where evidence.jsonl and events.jsonl records are consistent (no orphaned or missing entries)
    direction: maximize
    target: 0.99
    evaluation_window: 30_runs