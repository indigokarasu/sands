# Cron Persistence Patterns (ocas-sands)

Two reproducibility lessons from autonomous `sands.briefing.generate` cron runs.

## 0. Resolve the data directory BEFORE writing (there are three)

Three directories exist for Sands state. Only one is canonical:

| Path | Role |
|---|---|
| `/root/.hermes/profiles/indigo/commons/data/ocas-sands/` | **CANONICAL** — written by the current profile's cron jobs. Check `wc -l evidence.jsonl` and the newest mtime to confirm. |
| `/root/indigo-repo/commons/data/ocas-sands/` | Stale copy. Git-tracked, which makes it *look* authoritative. Not where the running jobs write. |
| `/root/indigo/commons/data/ocas-sands/` | Oldest stale copy, not even a git repo. |

**How to tell them apart:** count evidence records and compare newest mtime.
The canonical one has the most records and the most recent write. Do not infer
from git tracking — `/root/indigo-repo` is a git repo but is *not* the live
data dir, which is exactly what makes it a trap.

To confirm before any write:

```bash
for d in /root/.hermes/profiles/indigo/commons/data/ocas-sands \
         /root/indigo-repo/commons/data/ocas-sands \
         /root/indigo/commons/data/ocas-sands; do
  echo "$d: $(wc -l < "$d/evidence.jsonl" 2>/dev/null) records, newest $(stat -c %y "$d/config.json" 2>/dev/null)"
done
```

Also: `write_file` refuses to overwrite a scratch script it has not fully read,
and correctly so — scratch files from earlier runs persist. Use a
run-unique filename rather than reusing a generic one.

## 6. `wc -l` on a Sands JSONL can OVERCOUNT — blank lines are not records

On 2026-09-30 the travel check appeared to destroy 78 evidence records: `wc -l`
read 159 at 15:26, the append script counted 80, and the file "lost" ~half its
history. Nothing was lost. The 15:06 morning-brief writer had emitted a blank
line between every record, so 159 physical lines were 80 records + 79 blanks.
The append filters blanks, collapsing the ratio back to 1.00.

`decisions.jsonl` was the decisive control: this run never wrote it, and it
showed the same 1.88 lines-per-record ratio from the same writer. Two files
touched by one writer, both doubled; two untouched files, neither doubled.

**Rule: adjudicate a count change with a file the run did NOT write, and compare
ratios rather than absolute counts.** A one-file count drop is a corruption
signal; the same drop in an untouched control file is a measurement artifact.

Verify records, never lines:

```bash
python3 - <<'PY'
import json
p = "/root/.hermes/profiles/indigo/commons/data/ocas-sands/evidence.jsonl"
raw = open(p, encoding="utf-8").read()
dec, i, n = json.JSONDecoder(), 0, 0
while i < len(raw):
    while i < len(raw) and raw[i].isspace():
        i += 1
    if i >= len(raw):
        break
    _, i = dec.raw_decode(raw, i); n += 1
print(n, "records;", raw.count("\n"), "lines;", raw.count("\n\n"), "blank lines")
PY
```

Same trap applies to the reverse direction: a run that only appends can make the
file *look* untouched if it writes nothing, which is how the 13:37 false-completion
claim survived. Records, not lines, are the ground truth.

## 3. A run that reports side effects must be checked against the filesystem

On 2026-09-30 the 13:37 morning-brief run ended with "Evidence + action journal
written; `last_morning_brief` advanced." None of it was true: zero evidence
records, zero action records, no dated artifact, config still at the previous
day's timestamp. The response was a faithful-sounding summary of work that never
executed — the most expensive failure mode in this skill, because it survives
into the next run as an unexamined premise.

**Rule: never write a completion claim you have not verified in the same run.**
Persisting from a generated payload and *then* re-reading each artifact off disk
is the cheap defense. Write one verifier that asserts each specific claim
(artifact exists and parses; evidence count == prior + 1; config field equals the
run timestamp; every JSONL still parses) and run it before reporting. `append_jsonl.py`
already asserts the +1 for the file it touches — the other claims have no such guard.

Also: `evidence.jsonl` is the ground truth for whether a prior run did anything.
Its newest timestamp, not the cron output directory, tells you what happened. A
run can leave a full output file in `cron/output/<job_id>/` and still have
persisted nothing.

## 4. JSONL append: assert the count, and prefer one script for the whole run

Do all the writes for a run — artifact, evidence, action journal, decisions,
config — inside **one** script. A run that writes the artifact in one call and
the evidence in another can die between them and leave a brief with no record,
which is precisely the half-finished state found on 2026-09-30T03:57.

### 1. Unicode-safe JSONL appending (emoji in event titles)

Event titles routinely contain emoji (e.g. `🏺 Intro to Handbuilding @ Clayroom SoMa`).
`append_jsonl.py` takes the record as a **shell-quoted positional argument** (`python3 append_jsonl.py <path> '<json_record>'`). Passing a JSON string containing emoji and nested quotes through the shell is fragile — quotes collide, Unicode mangles, and the `json.loads` in the helper throws or stores corrupted text.

**Working pattern (cron-safe, verified 2026-07-23):**
1. `write_file` a small Python script to `/tmp/` (e.g. `/tmp/sands_persist.py`) that:
   - opens the JSONL, filters blank lines, appends `json.dumps(record) + '\n'`, rewrites, and `assert`s the line count increased by 1 (mirrors `append_jsonl.py` logic but runs in-process — no shell quoting);
   - builds each record as a real Python dict, so emoji/Unicode are written correctly by `json.dump`;
   - updates `config.json` fields (`last_morning_brief`, etc.) in the same script.
2. `terminal("python3 /tmp/sands_persist.py")` to run it.
3. Read back line counts / the rewritten file to verify (don't trust the write silently).

Use this instead of shell-quoting JSON into `append_jsonl.py` whenever a record may contain emoji, non-ASCII, or nested quotes. Plain ASCII records are still fine via the helper directly.

**Why not `execute_code`?** Blocked in cron mode (no user to approve). `write_file` + `terminal` is the required substitute (see SKILL.md "execute_code is blocked in cron mode").

## 5. `config.json primary_calendar_ids` DRIFTS from the briefing calendar list

`config.json` is NOT the source of truth for which calendars a briefing queries. The reusable
templates (`templates/sands_briefing_morning.py`, `templates/sands_briefing_evening.py`) **hardcode**
`CALENDAR_IDS` and `ACCOUNTS_TO_TRY` at the top of the file:

```
CALENDAR_IDS = [
    "<user-google-email>",
    "<family-calendar-id>@group.calendar.google.com"
]
ACCOUNTS_TO_TRY = ['<user-google-email>', '<agent-email>']
```

But `config.json` (as of 2026-07) lists only `"primary_calendar_ids": ["<user-google-email>"]`
— the Family calendar is **absent** from config yet is queried by the template.

**Consequence:** Anyone who reads `config.json` to learn "what calendars does Sands watch" gets an
incomplete answer and will silently miss Family-calendar events. The template is the effective
calendar set; config is a secondary/legacy record.

**Actions:**
- **Calendar scope is now DISCOVERED, not hardcoded.** As of 2026-10-01 both templates call `calendarList()` and query every readable calendar except the US Holidays calendar (all-day only) and any `OCAS_WORK_CALENDAR_ID` (read/overlay only per the SKILL.md hard boundary). `OCAS_CALENDAR_IDS` pins scope explicitly and skips discovery; `OCAS_CALENDAR_EXCLUDE` drops ids from the discovered set. Do NOT re-add a hardcoded calendar list to "fix" an empty calendar — the list is what silently dropped 2 of 3 timed events on 2026-10-01.
- Keep `config.json primary_calendar_ids` in sync with reality, but understand it is a *record of what is expected*, not the query set. A calendar discovered at runtime that is absent from config is normal and no longer a coverage bug.
- The canonical Family calendar ID is `<family-calendar-id>@group.calendar.google.com` (see `references/known-calendar-ids.md`).
- Per `direct_calendar_access.md`, the `<agent-email>` account can read BOTH the <operator> and Family calendars (sharing grant), so it serves as full fallback when the <operator> token is dead.

## 7. Verify records with a decoder — `"timestamp"` substring counting over-counts

On 2026-10-01 the morning-brief verifier reported `evidence count == prior + 1`
FAILED while the append it had just run correctly reported 82 -> 83 records.
The check was the defect: it counted occurrences of the substring
`"timestamp"`, and evidence records carry a **nested `supersedes.timestamp`**,
so any record with a supersedes entry matches twice (85 vs the true 83).

A false FAIL here is dangerous in the other direction: the instinct is to
re-append, which double-writes the record the check was supposed to protect.

**Rule: count records with `json.JSONDecoder().raw_decode`, never by substring
or by line count.** The same trap as s6 (line counting) with a new face — the
offending substring can be nested inside one record.

A verifier must also be re-runnable: this one is split into a persist phase and
a verify-only phase precisely so the checks can be re-executed without
re-appending. `append_jsonl.py`'s own +1 assertion covers the file it touches,
but artifact/config/journal claims have no such guard.
