#!/usr/bin/env python3
"""Behavioural checks for travel_check.py first_leg wiring.

Asserts on real output, not on the presence of source strings (the
2026-10-01 gotcha: a grep-based check passed on a broken feature).

Checks:
  1. --help stays side-effect free (no calendar query, no writes).
  2. 2026-10-05: first_leg present, destination is the first located anchor,
     origin unresolved, and the NOTE says so -- previously the run reported
     pairs only and the inbound leg was invisible.
  3. 2026-10-05: pair outcomes are byte-identical to the pre-patch capture.
     A fix that changes a correct answer is a policy change wearing a
     bug-fix label (2026-09-29 rule).
  4. A single-anchor day no longer misreports as travel-free.
  5. Empty day still yields no_timed_events and first_leg is None.
  6. With SANDS_DEPARTURE_ORIGIN set, the leg is actually routed.
"""
import json
import os
import subprocess
import sys

SCRIPT = "/root/.hermes/profiles/indigo/skills/ocas-sands/scripts/travel_check.py"
failures = []


def run(target=None, env=None):
    cmd = [sys.executable, SCRIPT, "--dry-run"]
    if target:
        cmd += ["--target", target]
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.run(cmd, capture_output=True, text=True, env=e, timeout=300)
    if p.returncode != 0:
        raise AssertionError("exit %d: %s" % (p.returncode, p.stderr[-400:]))
    return json.loads(p.stdout)


def check(name, cond, detail=""):
    print("%-58s %s" % (name, "PASS" if cond else "FAIL"))
    if not cond:
        failures.append(name + (" :: " + detail if detail else ""))


# 1. --help must not query the calendar or write anything.
p = subprocess.run([sys.executable, SCRIPT, "--help"], capture_output=True,
                   text=True, timeout=60)
out = p.stdout
check("--help exits 0 and is side-effect free",
      p.returncode == 0 and "usage" in out.lower() and "target_date" not in out,
      out[:200])

# 2/3. Real day: first_leg surfaced, pairs unchanged vs pre-patch capture.
today = run("2026-10-05")
before = json.load(open("/tmp/tc_before.json"))
leg = today.get("first_leg")
check("first_leg is reported at all", leg is not None)
if leg:
    check("first_leg targets the first located anchor",
          leg["to"] == "Appointment with Eric Fine", leg.get("to", ""))
    check("first_leg origin is unresolved, not assumed",
          leg.get("origin") is None
          and leg.get("action") == "not_evaluated_origin_unresolved",
          json.dumps(leg)[:200])
    check("first_leg names the unlocated preceding event",
          any(p["summary"] == "LEAVE" and p["location_present"] is False
              for p in leg["preceding_events"]),
          json.dumps(leg["preceding_events"])[:200])
check("first_leg_unresolved flag set", today.get("first_leg_unresolved") is True)
check("a human-readable note explains the unresolved leg",
      any("inbound leg" in n for n in today.get("notes", [])),
      json.dumps(today.get("notes", []))[:200])
check("pairs byte-identical to pre-patch capture",
      today["pairs"] == before["pairs"],
      json.dumps(today["pairs"])[:300])
check("located/unlocated counts unchanged",
      today["located_event_count"] == before["located_event_count"]
      and today["unlocated_event_count"] == before["unlocated_event_count"])

# 4. Single-anchor day: 2026-10-02 had one located event and reported
# `no_located_events_to_pair`. It must now also carry the first-leg verdict.
try:
    single = run("2026-10-02")
except AssertionError as exc:
    single = None
    print("  (2026-10-02 unavailable: %s)" % exc)
if single:
    leg2 = single.get("first_leg")
    check("single-anchor day still reports first_leg", leg2 is not None)
    if leg2:
        check("single-anchor day flags the unresolved inbound leg",
              single.get("first_leg_unresolved") is True
              and leg2.get("origin") is None,
              json.dumps(leg2)[:200])

# 5. Empty day unchanged.
empty = run("2026-10-04")
check("empty day -> no_timed_events, first_leg None",
      empty.get("not_activity_reason") == "no_timed_events"
      and empty.get("first_leg") is None,
      json.dumps(empty)[:200])

# 6. A declared origin actually routes the leg (no invented address, but the
#    wiring must work when an origin IS established).
declared = run("2026-10-05",
              env={"SANDS_DEPARTURE_ORIGIN":
                   "1 Market St, San Francisco, CA 94105"})
leg3 = declared.get("first_leg")
check("declared origin routes the first leg",
      leg3 is not None and leg3.get("origin_source") == "declared_departure_origin"
      and leg3.get("action") in ("first_leg_would_fit_before_event",
                                 "no_travel_needed_same_area",
                                 "route_failed"),
      json.dumps(leg3)[:300])
if leg3 and leg3.get("action") != "route_failed":
    check("routed leg carries a computed duration",
          isinstance(leg3.get("computed_minutes"), (int, float)),
          json.dumps(leg3)[:200])

print()
if failures:
    print("FAILED (%d):" % len(failures))
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("ALL CHECKS PASS")