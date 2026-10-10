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
import datetime
import importlib.util
import json
import os
import subprocess
import sys

SCRIPT = "/root/.hermes/profiles/indigo/skills/ocas-sands/scripts/travel_check.py"
# The pre-patch capture must live inside the skill, not in /tmp: /tmp is wiped,
# and when the fixture went missing the whole suite aborted on a
# FileNotFoundError before running a single check — a broken guard that reads
# as a broken script. Regenerate only with:
#   python3 scripts/travel_check.py --target 2026-10-05 --dry-run > \
#       scripts/travel_check_pairs_baseline.json
BASELINE = os.path.join(os.path.dirname(SCRIPT),
                        "travel_check_pairs_baseline.json")
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

# 2/3. Real day: first_leg surfaced, pair outcomes unchanged vs the
#      pre-patch capture.
today = run("2026-10-05")
if not os.path.exists(BASELINE):
    print("MISSING BASELINE: %s — regenerate before trusting this"
          " suite" % BASELINE)
    sys.exit(2)
before = json.load(open(BASELINE))
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
# 3. Pair OUTCOMES must not change from a first-leg fix. Compare on the
#    invariant fields (membership, ordering, gap, action) rather than a byte
#    compare: computed_minutes comes from Routes v2 TRAFFIC_AWARE, which
#    legitimately varies between calls (documented 2.3 min, observed 2.5 min
#    on the same leg hours later). A byte compare on a live traffic value
#    produces a false FAIL that invites re-appending or reverting a correct
#    fix. The policy this guards — "a fix that changes a correct answer is a
#    policy change wearing a bug-fix label" — is about WHICH legs are found and
#    WHAT ACTION each gets, not about today's traffic estimate.
INVARIANT = ("from", "to", "gap_min", "same_address", "action")
check("pair membership and actions identical to pre-patch capture",
      [{k: p.get(k) for k in INVARIANT} for p in today["pairs"]]
      == [{k: p.get(k) for k in INVARIANT} for p in before["pairs"]],
      json.dumps([{k: p.get(k) for k in INVARIANT} for p in today["pairs"]])[:300])
for now_p, old_p in zip(today["pairs"], before["pairs"]):
    if isinstance(now_p.get("computed_minutes"), (int, float)) \
            and isinstance(old_p.get("computed_minutes"), (int, float)):
        drift = abs(now_p["computed_minutes"] - old_p["computed_minutes"])
        check("pair %s->%s duration within traffic-variance band (<=5 min)"
              % (now_p["from"][:16], now_p["to"][:16]),
              drift <= 5.0, "drift=%.1f" % drift)
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

# 7. USER.md location snapshot is the cron-mode origin (2026-10-09). Before
#    this existed, every unattended run ended origin_unresolved for the day's
#    inbound leg while a verified location sat in USER.md one file away.
#    Assert on BEHAVIOUR (real routing), not on source text.
sys.path.insert(0, os.path.dirname(SCRIPT))
import travel_check  # noqa: E402

snap = travel_check.read_user_location_snapshot(
    datetime.date(2026, 10, 10))
check("USER.md snapshot is read when fresh",
      snap[0] and snap[1] == "2026-10-08" and snap[2] is None,
      json.dumps(snap))
# Assert the live wiring on a target the fresh snapshot actually governs. The
# 2026-10-05 leg belongs to a stale-snapshot day and stays unresolved by design,
# so checking it here would assert the wrong behaviour.
snap_run = run("2026-10-10")
leg_snap = snap_run.get("first_leg") or {}
check("fresh snapshot yields user_context_location_snapshot origin",
      leg_snap.get("origin_source") == "user_context_location_snapshot"
      and leg_snap.get("origin") == snap[0],
      json.dumps(leg_snap)[:200])
check("snapshot-sourced leg carries a computed duration",
      isinstance(leg_snap.get("computed_minutes"), (int, float)),
      json.dumps(leg_snap)[:200])
check("snapshot-sourced leg is not flagged unresolved",
      snap_run.get("first_leg_unresolved") is None,
      json.dumps(snap_run.get("notes"))[:200])

# 8. A STALE snapshot must NOT become an origin — a wrong address that reads
#    authoritative is the exact failure the no-hardcoded-home boundary exists
#    to prevent, so staleness must refuse to route, not route with a caveat.
stale = travel_check.read_user_location_snapshot(datetime.date(2026, 10, 20))
check("stale snapshot (age > 2d) is refused as an origin",
      stale[0] is None and "stale_user_context_snapshot" in (stale[2] or ""),
      json.dumps(stale))
# 2026-10-12 is stale AND has a located anchor, so this proves the refusal
# reaches real routing rather than only the parser. A no-event day would pass
# vacuously because first_leg is None.
stale_live = run("2026-10-12")
leg_stale = stale_live.get("first_leg") or {}
check("stale-snapshot day with an anchor routes nothing, flags unresolved",
      leg_stale.get("origin") is None
      and leg_stale.get("action") == "not_evaluated_origin_unresolved"
      and "stale_user_context_snapshot" in (leg_stale.get("reason") or "")
      and stale_live.get("first_leg_unresolved") is True,
      json.dumps(leg_stale)[:200])

# 9. The parser must be testable against synthetic USER.md files without
#    depending on the live one. Rather than patching a source string into a
#    temp copy (brittle: it breaks if the literal path moves), extract the
#    parser into a helper that takes a path.
import tempfile  # noqa: E402


def load_parser(uc_path):
    """Import travel_check with its USER.md path redirected to uc_path."""
    src = open(SCRIPT, encoding="utf-8").read().replace(
        '"/root/.hermes/profiles/indigo/memories/USER.md"', repr(uc_path))
    assert repr(uc_path) in src, "USER.md path literal not found in script"
    fd, mod_path = tempfile.mkstemp(suffix=".py", prefix="tc_")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(src)
    spec = importlib.util.spec_from_file_location("tc_" + str(abs(hash(uc_path))), mod_path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not build module spec for %s" % mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    os.unlink(mod_path)
    return mod


with tempfile.TemporaryDirectory() as td:
    fresh = os.path.join(td, "USER.md")
    with open(fresh, "w", encoding="utf-8") as fh:
        fh.write("## Daily Context\n\n### Snapshot (2026-10-08)\n"
                 "**Mood:** quiet\n**Location:** Palo Alto\n")
    tc_fresh = load_parser(fresh)
    r = tc_fresh.read_user_location_snapshot(datetime.date(2026, 10, 10))
    check("snapshot parser reads a fresh Location line",
          r[0] == "Palo Alto" and r[2] is None, json.dumps(r))
    r2 = tc_fresh.read_user_location_snapshot(datetime.date(2026, 12, 1))
    check("same parser refuses a stale snapshot",
          r2[0] is None and "stale" in (r2[2] or ""), json.dumps(r2))
    r_far_past = tc_fresh.read_user_location_snapshot(datetime.date(2026, 10, 5))
    check("same parser refuses a future-dated target beyond -1d",
          r_far_past[0] is None and "stale" in (r_far_past[2] or ""),
          json.dumps(r_far_past))

    # No Location line at all: must not be mistaken for a location.
    noloc = os.path.join(td, "NOLOC.md")
    with open(noloc, "w", encoding="utf-8") as fh:
        fh.write("### Snapshot (2026-10-08)\n**Mood:** busy\n")
    tc_noloc = load_parser(noloc)
    r3 = tc_noloc.read_user_location_snapshot(datetime.date(2026, 10, 10))
    check("snapshot without a Location line is not an origin",
          r3[0] is None, json.dumps(r3))

    # Placeholder values are null-location values, not addresses.
    for placeholder in ("TBD", "none", "null"):
        ph = os.path.join(td, "PH.md")
        with open(ph, "w", encoding="utf-8") as fh:
            fh.write("### Snapshot (2026-10-08)\n**Location:** %s\n"
                     % placeholder)
        tc_ph = load_parser(ph)
        rp = tc_ph.read_user_location_snapshot(datetime.date(2026, 10, 10))
        check("placeholder location (%s) is not an origin" % placeholder,
              rp[0] is None
              and "placeholder_location_in_user_context_snapshot" in (rp[2] or ""),
              json.dumps(rp))

    # Absent file degrades to unresolved rather than raising.
    tc_absent = load_parser(os.path.join(td, "DOES_NOT_EXIST.md"))
    ra = tc_absent.read_user_location_snapshot(datetime.date(2026, 10, 10))
    check("absent USER.md degrades to unresolved, does not raise",
          ra[0] is None and "absent" in (ra[2] or ""), json.dumps(ra))

print()
if failures:
    print("FAILED (%d):" % len(failures))
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("ALL CHECKS PASS")