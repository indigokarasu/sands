#!/usr/bin/env python3
"""Regression checks for templates/sands_briefing_morning.py.

Guards three contracts that broke silently in the 2026-09-27 run:

1. `--help` exits 0 WITHOUT querying a calendar.
2. A placeholder / unset calendar id ABORTS at startup instead of reaching
   the API and returning a 404 that reads like a transient fault.
3. With real env, the template runs clean across both calendars.

Run: python3 scripts/briefing_morning_regression.py
Exit: 0 pass, 1 fail.
"""
import os
import json
import subprocess
import sys

TPL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "templates", "sands_briefing_morning.py")

env = dict(os.environ)
env.setdefault("OCAS_OPERATOR_EMAIL", "jared.zimmerman@gmail.com")
env.setdefault("OCAS_FAMILY_CALENDAR_ID", "family08350553536598846140@group.calendar.google.com")

failures = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{('  — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


# 1. --help is side-effect free
r = subprocess.run([sys.executable, TPL, "--help"], capture_output=True, text=True, env=env)
check("--help exits 0 without querying a calendar",
      r.returncode == 0 and "Using account" not in r.stdout, f"exit={r.returncode}")

# 2. placeholder env aborts before any network call
# NB: sys.exit(msg) writes to stderr, so check the combined streams.
bad = dict(env)
bad["OCAS_FAMILY_CALENDAR_ID"] = "<family-calendar-id>@group.calendar.google.com"
r2 = subprocess.run([sys.executable, TPL, "--dry-run"], capture_output=True, text=True, env=bad)
out2 = r2.stdout + r2.stderr
check("placeholder calendar id aborts instead of 404ing",
      r2.returncode != 0 and "ABORT" in out2 and "Using account" not in out2,
      f"exit={r2.returncode}")

# 2b. unset env aborts too (no silent default email)
unset = dict(env)
unset["OCAS_FAMILY_CALENDAR_ID"] = ""
r2b = subprocess.run([sys.executable, TPL, "--dry-run"], capture_output=True, text=True, env=unset)
out2b = r2b.stdout + r2b.stderr
check("unset calendar id aborts instead of using a default",
      r2b.returncode != 0 and "ABORT" in out2b, f"exit={r2b.returncode}")

# 3. real env runs clean
r3 = subprocess.run([sys.executable, TPL, "--dry-run"], capture_output=True, text=True, env=env)
check("real env produces a clean brief",
      r3.returncode == 0 and "ERROR" not in r3.stdout, f"exit={r3.returncode}")
if r3.returncode != 0:
    print((r3.stdout + r3.stderr)[-800:])

# 4. COVERAGE: the brief queries every calendar the token can read.
# A hardcoded two-calendar list silently dropped 2 of 3 timed events on
# 2026-10-01 while still emitting a clean-looking brief. Assert discovery
# runs AND that the scope exceeds the configured pair.
r4 = subprocess.run([sys.executable, TPL, "--dry-run"], capture_output=True, text=True, env=env)
scope_line = next((l for l in r4.stdout.splitlines() if l.startswith("Calendar scope:")), "")
n_scope = int(scope_line.split(":")[1].split()[0]) if scope_line else 0
check("calendar discovery runs and widens scope beyond the configured pair",
      r4.returncode == 0 and n_scope > 2 and "discovery incomplete" not in scope_line,
      f"scope={n_scope}")

# 5. Coverage is recorded in the payload, so a truncated brief is self-evident
#    to any consumer instead of looking complete.
r5 = subprocess.run([sys.executable, TPL], capture_output=True, text=True, env=env)
pay_ok = False
try:
    with open("/tmp/sands_morning_briefing.json") as f:
        pay = json.load(f)
    pay_ok = (pay.get("calendar_discovery_complete") is True
              and len(pay.get("calendars_queried", [])) > 2)
except Exception as e:
    print(f"  payload check: {e}")
check("payload records calendar_discovery_complete and full scope",
      r5.returncode == 0 and pay_ok)

# 6. Conflict scoping is per-calendar, not a 'family' substring test.
#    Asserted BEHAVIOURALLY: three events at the same time on three DIFFERENT
#    calendars are 3 cross-calendar overlaps, NOT 3 conflicts. The first version
#    of this check grepped the template source for the string
#    `_source_calendar') == b.get('_source_calendar')` and passed while the
#    feature was broken — parsed_events never carried the key, so both sides
#    were None and every cross-calendar pair compared equal.
#    (2026-10-01: 3 false conflicts in a live brief.)
src = open(TPL).read()
check("parsed_events carries _source_calendar into the conflict loop",
      "'_source_calendar': ev.get('_source_calendar'" in src)
r6 = subprocess.run([sys.executable, TPL, "--dry-run"], capture_output=True, text=True, env=env)
with open("/tmp/sands_morning_briefing.json") as f:
    pay = json.load(f)
conflict_calendars = {e["calendar"] for e in pay["events"] if e.get("conflict")}
check("same-time events on different calendars are not counted as conflicts",
      pay["conflicts_detected"] == 0 and pay["cross_calendar_overlaps"] > 0
      and len(conflict_calendars) <= 1,
      f"conflicts={pay['conflicts_detected']} "
      f"cross={pay['cross_calendar_overlaps']} "
      f"conflict_calendars={sorted(conflict_calendars) or '[]'}")

if failures:
    print(f"\n{len(failures)} check(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("\nAll checks passed.")
