#!/usr/bin/env python3
"""sands.logistics.travel — cron-safe travel check for tomorrow's events.

Replaces the ad-hoc scratch scripts. Carries the three corrections found
2026-09-29:

  1. DATA_DIR is the canonical profile path, not /root/indigo-repo
     (see references/cron_persistence.md section 0).
  2. Routes v2 computeRoutes is called WITH the required X-Goog-FieldMask
     header. Omitting it returns 400 "FieldMask is a required parameter",
     which is easy to misread as "API disabled" (references/gotchas.md).
  3. Pairs are built from LOCATED ANCHORS, not raw start-order adjacency, so
     a cross-city leg is not hidden behind an event with no location.

Never creates a truncated block: if gap < travel_time + buffer, it surfaces
the pair instead (travel_time_logic.md Step 6). No manual fallbacks, no
guessed distances.

Usage:  python3 scripts/travel_check.py [--target YYYY-MM-DD] [--dry-run]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DATA_DIR = os.environ.get(
    "SANDS_DATA_DIR", "/root/.hermes/profiles/indigo/commons/data/ocas-sands"
)
SECRETS = "/root/.hermes/secrets/plaid.env"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.duration,routes.distanceMeters"
TRAVEL_MARKERS = (
    "travel", "\U0001f697", "\U0001f687", "\U0001f6b6", "\U0001f6b2",
    "drive", "commute", "leaving for", "depart for", "ride to",
)
MODE_MAP = {
    "driving": "DRIVE",
    "walking": "WALK",
    "bicycling": "BICYCLE",
    "transit": "TRANSIT",
}


def load_config():
    with open(os.path.join(DATA_DIR, "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


def places_key():
    """The config field is often empty even when a usable key exists in secrets."""
    if not os.path.exists(SECRETS):
        return None
    with open(SECRETS, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^\s*GOOGLE_PLACES_API_KEY\s*=\s*(.+?)\s*$", line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return None


def parse_dt(raw, tz):
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def get_calendar_service():
    sys.path.insert(0, "/root/.hermes/scripts")
    from google_auth import get_calendar_service  # noqa: PLC0415

    cfg = load_config()
    accounts = ["jared.zimmerman@gmail.com", "mx.indigo.karasu@gmail.com"]
    errors = []
    for acct in accounts:
        try:
            cal = get_calendar_service(acct)
            cal.calendarList().list(maxResults=1).execute()
            return cal, acct, errors
        except Exception as exc:  # noqa: BLE001
            errors.append("%s: %s %s" % (acct, type(exc).__name__, str(exc)[:120]))
    return None, None, errors


def fetch_events(cal, cfg, tz, target):
    tmin = datetime.combine(target, datetime.min.time(), tz)
    tmax = tmin + timedelta(days=1)
    events, errors = [], {}
    for cid in cfg["primary_calendar_ids"]:
        try:
            res = cal.events().list(
                calendarId=cid,
                timeMin=tmin.isoformat(),
                timeMax=tmax.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                showDeleted=False,
                maxResults=100,
            ).execute()
            items = res.get("items", [])
        except Exception as exc:  # noqa: BLE001
            errors[cid] = "%s %s" % (type(exc).__name__, str(exc)[:120])
            continue
        for ev in items:
            st = ev["start"]
            all_day = "date" in st
            if all_day:
                continue  # all-day never conflicts or needs travel (hard boundary)
            start = parse_dt(st["dateTime"], tz)
            end = parse_dt(ev["end"]["dateTime"], tz)
            summary = ev.get("summary", "(no title)")
            events.append(
                {
                    "id": ev["id"],
                    "calendar": cid,
                    "summary": summary,
                    "location": (ev.get("location") or "").strip(),
                    "start": start,
                    "end": end,
                    "is_travel": any(mk in summary.lower() for mk in TRAVEL_MARKERS),
                }
            )
    events.sort(key=lambda e: e["start"])
    return events, errors


def route_minutes(key, origin, dest, mode, depart_iso):
    """Returns (minutes, meters) or raises. Sends the required FieldMask."""
    body = {
        "origin": {"address": origin},
        "destination": {"address": dest},
        "travelMode": MODE_MAP.get(mode, "DRIVE"),
    }
    if body["travelMode"] == "DRIVE":
        body["routingPreference"] = "TRAFFIC_AWARE"
        body["departureTime"] = depart_iso
    import urllib.request  # noqa: PLC0415

    req = urllib.request.Request(ROUTES_URL, data=json.dumps(body).encode())
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Goog-Api-Key", key)
    req.add_header("X-Goog-FieldMask", FIELD_MASK)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    rt = data["routes"][0]
    return round(int(rt["duration"].rstrip("s")) / 60.0, 1), rt.get("distanceMeters")


def build_pairs(events):
    """Located-anchor pairing: each located event's end -> next located event.

    Avoids the miss where an unlocated event between two located ones hides a
    cross-city leg (references/gotchas.md, 2026-09-29).
    """
    located = [e for e in events if e["location"] and not e["is_travel"]]
    pairs = []
    for i in range(len(located) - 1):
        a, b = located[i], located[i + 1]
        gap = (b["start"] - a["end"]).total_seconds() / 60.0
        pairs.append({"from": a, "to": b, "gap_min": round(gap, 1)})
    return pairs


def main():
    ap = argparse.ArgumentParser(description="Sands travel check for tomorrow")
    ap.add_argument("--target", help="YYYY-MM-DD; default = tomorrow local")
    ap.add_argument("--dry-run", action="store_true", help="report only, persist nothing")
    args = ap.parse_args()

    cfg = load_config()
    tz = ZoneInfo(cfg.get("default_timezone", "America/Los_Angeles"))
    now = datetime.now(tz)
    target = (
        datetime.fromisoformat(args.target).date()
        if args.target
        else (now + timedelta(days=1)).date()
    )
    buffer_min = cfg.get("travel_buffer_minutes", 10)
    mode = cfg.get("default_travel_mode", "driving")

    result = {
        "run_at": now.isoformat(),
        "target_date": target.isoformat(),
        "buffer_minutes": buffer_min,
        "mode": mode,
        "events": [],
        "calendar_errors": {},
        "auth_errors": [],
        "pairs": [],
        "travel_blocks_created": 0,
        "side_effects": [],
        "degraded": None,
        "not_activity_reason": None,
    }

    cal, account, auth_errors = get_calendar_service()
    result["auth_errors"] = auth_errors
    if cal is None:
        result["degraded"] = "oauth_stale: no working account"
        result["not_activity_reason"] = "auth_failed"
        result["auth_status"] = "STALE_OAUTH"
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    result["account"] = account

    events, cal_errors = fetch_events(cal, cfg, tz, target)
    result["calendar_errors"] = cal_errors
    result["events"] = [
        {
            "summary": e["summary"],
            "location": e["location"],
            "start": e["start"].isoformat(),
            "end": e["end"].isoformat(),
        }
        for e in events
    ]
    if not events:
        result["not_activity_reason"] = "no_timed_events"
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    key = places_key()
    if not key:
        result["degraded"] = "no_google_places_key_found_in_secrets"
        result["not_activity_reason"] = "places_key_absent_observational_only"
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    for pair in build_pairs(events):
        a, b = pair["from"], pair["to"]
        entry = {
            "from": a["summary"],
            "to": b["summary"],
            "gap_min": pair["gap_min"],
        }
        try:
            mins, meters = route_minutes(key, a["location"], b["location"], mode, a["end"].isoformat())
        except Exception as exc:  # noqa: BLE001
            entry["error"] = "%s %s" % (type(exc).__name__, str(exc)[:160])
            result["pairs"].append(entry)
            continue
        need = round(mins + buffer_min, 1)
        entry["computed_minutes"] = mins
        entry["computed_meters"] = meters
        entry["travel_plus_buffer_min"] = need
        entry["same_address"] = mins == 0
        if entry["same_address"]:
            entry["action"] = "no_travel_needed_same_facility"
        elif pair["gap_min"] >= need:
            entry["action"] = "travel_block_would_fit"  # not auto-created in this run
        else:
            entry["action"] = "surface_conflict_no_block_created"
            entry["shortfall_min"] = round(need - pair["gap_min"], 1)
        result["pairs"].append(entry)

    if not any(p.get("action") == "travel_block_would_fit" for p in result["pairs"]):
        result["not_activity_reason"] = "no_gap_fits_computed_travel_time"
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
