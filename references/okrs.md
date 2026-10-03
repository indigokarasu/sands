## OKRs

Universal OKRs from `spec-ocas-journal.md` apply to all runs. Skill-local OKRs are
declared in `references/schemas.md` and tracked over a 30-run window.

### Skill-local OKRs

| OKR | Metric | Direction | Target |
|---|---|---|---|
| `conflict_detection_accuracy` | fraction of real conflicts correctly identified and surfaced | maximize | 0.95 |
| `travel_time_api_success_rate` | fraction of `sands.logistics.travel` runs completing via Places/Routes API | maximize | 0.90 |
| `calendar_write_success_rate` | fraction of create/modify runs with no calendar API error | maximize | 0.98 |
| `schedule_adherence` | fraction of cron runs executing within 5 minutes of scheduled time | maximize | 0.95 |
| `data_integrity` | fraction of runs where evidence / decision / action records are consistent — no orphaned or missing entries | maximize | 0.99 |

### `data_integrity` failed on 2026-10-03 — measured at run time now

Auditing 23 morning briefs that day: 11 had an evidence record and a dated artifact
but **no action-journal record**, despite `sands.briefing.generate` being an Action
Journal command. The 13:19 run reported both journals written; only evidence was.

The metric could not catch this because nothing measured it per run — it took a later
audit to reconstruct, and the runs themselves reported success throughout.
`scripts/persist_brief.py` now performs all four writes and re-reads each off disk
(13 checks, non-zero exit on any failure), so an incomplete run fails itself instead
of waiting to be audited. See `references/cron_persistence.md` §8.

**Note on this file's history:** `references/okrs.md` previously contained an orphaned
`update.sh` body — the self-update recipe that belongs in `references/self-update-sands.md`
(which explicitly warns that no `scripts/update.sh` ships). SKILL.md routed OKR lookups
here, so a run asking "what are the OKRs" got a tarball command and nothing else. Same
class as every other defect in `references/zero_duration_briefing.md`: a reference that
does not contain what its name and its inbound links promise. Verify a reference's
content, not its presence.