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

if failures:
    print(f"\n{len(failures)} check(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("\nAll checks passed.")
