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

## 1. Unicode-safe JSONL appending (emoji in event titles)

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

## 2. `config.json primary_calendar_ids` DRIFTS from the briefing calendar list

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
- When you need the real calendar set for a run, trust the template's `CALENDAR_IDS`, not `config.json primary_calendar_ids`.
- Keep them in sync: if you add/remove a calendar, update BOTH the template `CALENDAR_IDS` AND `config.json primary_calendar_ids`. Note this in the edit.
- The canonical Family calendar ID is `<family-calendar-id>@group.calendar.google.com` (see `references/known-calendar-ids.md`).
- Per `direct_calendar_access.md`, the `<agent-email>` account can read BOTH the <operator> and Family calendars (sharing grant), so it serves as full fallback when the <operator> token is dead.
