
## Storage Layout

```
{agent_root}/commons/data/ocas-sands/
  config.json
  decisions.jsonl
  events.jsonl
  evidence.jsonl
  intents.jsonl
{agent_root}/commons/journals/ocas-sands/
  YYYY-MM-DD/{run_id}.json
```


## Default Configuration

```yaml
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
```

