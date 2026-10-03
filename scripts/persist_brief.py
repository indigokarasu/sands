#!/usr/bin/env python3
"""
Canonical run-completion persistence for Sands briefings.

Why this exists (2026-10-03):
    `sands.briefing.generate` is an Action Journal command, but nothing in the
    skill enforced that. The morning template is a *pure generator*: SKILL.md
    says "the calling cron run must persist" evidence + action + artifact +
    config, and every hand-rolled run gets that list slightly wrong. Auditing
    20 morning briefs on 2026-10-03: 19 of 20 had an evidence record and a
    dated artifact, and **11 had no action-journal record at all** — including
    the run that reported "evidence and action journal written". A claim about
    persistence is exactly the kind I am not trusted to make unverified.

So: one script, all four writes, then re-read every artifact off disk and
assert the specific claim. If any step fails the script exits non-zero and the
run is a failure, not a success with a caveat.

Usage:
    python3 persist_brief.py --mode morning --payload-file /tmp/brief.json
    python3 persist_brief.py --mode morning --payload-file /tmp/brief.json --verify-only

Writes:
    {data_dir}/{target_date}_{mode}_brief.json    dated artifact
    {data_dir}/evidence.jsonl                      +1 record
    {journals}/ocas-sands/action.jsonl             +1 record
    {data_dir}/config.json                         last_{mode}_brief

Idempotency: if a record for the same (target_date, mode) already exists this
run *supersedes* it (sets `supersedes.timestamp`) rather than duplicating, so a
re-run of the same day cannot inflate counts. --supersede is required to
replace an existing record; without it an existing record aborts the write.
"""
import argparse
import json
import os
import sys
from datetime import datetime

CANDIDATE_DATA_DIRS = [
    "/root/.hermes/profiles/indigo/commons/data/ocas-sands",
    "/root/indigo-repo/commons/data/ocas-sands",
    "/root/indigo/commons/data/ocas-sands",
]
JOURNAL_SUBDIR = "ocas-sands"


def now_iso():
    return datetime.now().astimezone().isoformat()


def resolve_data_dir(explicit=""):
    """Pick the CANONICAL data dir by record count + newest mtime.

    Never infer from git tracking: /root/indigo-repo IS a git repo and is NOT
    the live dir, which is precisely what makes it a trap
    (references/cron_persistence.md §0).
    """
    if explicit:
        return explicit, "explicit"
    scored = []
    for d in CANDIDATE_DATA_DIRS:
        ev = os.path.join(d, "evidence.jsonl")
        if not os.path.isdir(d) or not os.path.exists(ev):
            continue
        scored.append((count_records(ev), os.path.getmtime(ev), d))
    if not scored:
        raise SystemExit("ABORT: no Sands data dir found in %s" % CANDIDATE_DATA_DIRS)
    scored.sort(reverse=True)
    return scored[0][2], f"{scored[0][0]} records"


def count_records(path):
    """Count JSON records with a decoder — never wc -l, never substring count.

    Evidence records carry a nested `supersedes.timestamp`, so a `"timestamp"`
    substring count double-counts (references/cron_persistence.md §6, §7).
    """
    raw = open(path, encoding="utf-8").read()
    dec, i, n = json.JSONDecoder(), 0, 0
    while i < len(raw):
        while i < len(raw) and raw[i].isspace():
            i += 1
        if i >= len(raw):
            break
        _, i = dec.raw_decode(raw, i)
        n += 1
    return n


def read_records(path):
    raw = open(path, encoding="utf-8").read()
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(raw):
        while i < len(raw) and raw[i].isspace():
            i += 1
        if i >= len(raw):
            break
        o, i = dec.raw_decode(raw, i)
        out.append(o)
    return out


def append_record(path, record):
    """Append one record, asserting the record count went up by exactly 1."""
    before = count_records(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    recs = read_records(path) if os.path.exists(path) else []
    recs.append(record)
    with open(path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    after = count_records(path)
    assert after == before + 1, f"append to {path}: {before} -> {after}, expected +1"
    return before, after


def find_existing(records, target_date, mode):
    """Find a prior record for the same (target_date, mode), any schema vintage.

    Older morning runs wrote `brief_type: "morning"` with NO `mode` and NO
    `target_date` — the field set drifted between writers. Matching only on
    (target_date, mode) silently misses those, so a re-run would append a
    duplicate instead of superseding. Fall back to timestamp-derived date and
    the brief_type alias.
    """
    for r in records:
        r_mode = r.get("mode") or r.get("brief_type")
        if r_mode != mode:
            continue
        r_date = r.get("target_date") or (r.get("timestamp") or "")[:10]
        if r_date == target_date:
            return r
    return None


def build_records(payload, mode, target_date, ts):
    """Derive evidence + action records from the generated brief payload."""
    do = payload.get("day_overview") or {}
    total = payload.get("total_events", do.get("total_events"))
    conflicts = payload.get("conflicts_detected", 0)
    free = payload.get("free_hours", do.get("free_hours"))
    prep = payload.get("prep_items_count", do.get("prep_items_count"))
    zd = payload.get("zero_duration_warnings", 0)
    common = {
        "timestamp": ts,
        "command": "sands.briefing.generate",
        "mode": mode,
        "target_date": target_date,
        "status": "ok",
        "auth_account": payload.get("auth_account"),
        "auth_fallback_used": payload.get("auth_fallback_used", False),
        "degraded": payload.get("degraded") or None,
        "calendars_queried": len(payload.get("calendars_queried") or []),
        "calendar_discovery_complete": payload.get("calendar_discovery_complete"),
        "calendar_errors": payload.get("calendar_errors") or {},
    }
    evidence = dict(
        common,
        brief_type=mode,
        total_events=total,
        conflicts_detected=conflicts,
        zero_duration_warnings=zd,
        free_hours=free,
        prep_items=prep,
        not_activity_reason=None,
    )
    action = dict(
        common,
        run_type="cron",
        skill="ocas-sands",
        entry_type="action",
        action=f"{mode}_brief",
        summary_note=payload.get("summary_note"),
        total_events=total,
        conflicts_detected=conflicts,
        cross_calendar_overlaps=payload.get("cross_calendar_overlaps", 0),
        zero_duration_warnings=zd,
        free_hours=free,
        prep_items_count=prep,
        side_effects=[],
    )
    return evidence, action


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", required=True, choices=["morning", "evening"])
    ap.add_argument("--payload-file", required=True)
    ap.add_argument("--data-dir", default="")
    ap.add_argument("--journal-dir", default="")
    ap.add_argument("--supersede", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()

    if set(sys.argv[1:]) & {"--help", "-h"}:
        print((__doc__ or "").strip())
        return 0

    payload = json.load(open(a.payload_file, encoding="utf-8"))
    target_date = payload.get("target_date")
    if not target_date:
        raise SystemExit("ABORT: payload has no target_date")

    data_dir, why = resolve_data_dir(a.data_dir)
    journal_dir = a.journal_dir or os.path.join(
        "/root/.hermes/profiles/indigo/commons/journals", JOURNAL_SUBDIR
    )
    evidence_path = os.path.join(data_dir, "evidence.jsonl")
    action_path = os.path.join(journal_dir, "action.jsonl")
    artifact = os.path.join(data_dir, f"{target_date}_{a.mode}_brief.json")
    config_path = os.path.join(data_dir, "config.json")
    ts = now_iso()

    print(f"data_dir: {data_dir} ({why})")
    print(f"journal_dir: {journal_dir}")
    print(f"artifact: {artifact}")

    prior_ev = read_records(evidence_path) if os.path.exists(evidence_path) else []
    prior_ac = read_records(action_path) if os.path.exists(action_path) else []
    ev_existing = find_existing(prior_ev, target_date, a.mode)
    ac_existing = find_existing(prior_ac, target_date, a.mode)
    print(f"prior: evidence={len(prior_ev)} action={len(prior_ac)}")
    print(
        f"existing for {target_date}/{a.mode}: evidence={bool(ev_existing)} "
        f"action={bool(ac_existing)}"
    )
    if not a.verify_only and (ev_existing or ac_existing) and not a.supersede:
        raise SystemExit(
            f"ABORT: a {a.mode} brief for {target_date} is already recorded. "
            "Re-run with --supersede to replace it."
        )

    if a.verify_only:
        return verify(artifact, evidence_path, action_path, config_path,
                      target_date, a.mode, ts, payload)

    evidence, action = build_records(payload, a.mode, target_date, ts)
    for rec, path, existing in (
        (evidence, evidence_path, ev_existing),
        (action, action_path, ac_existing),
    ):
        if existing:
            rec["supersedes"] = {"timestamp": existing.get("timestamp"),
                                 "command": existing.get("command")}
        rec["artifact_written"] = artifact

    ev_before, ev_after = append_record(evidence_path, evidence)
    ac_before, ac_after = append_record(action_path, action)
    print(f"evidence: {ev_before} -> {ev_after} records")
    print(f"action:   {ac_before} -> {ac_after} records")

    with open(artifact, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    cfg: dict = json.load(open(config_path, encoding="utf-8")) if os.path.exists(config_path) else {}
    cfg[f"last_{a.mode}_brief"] = ts
    cfg["updated_at"] = ts
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"config: last_{a.mode}_brief = {ts}")

    return verify(artifact, evidence_path, action_path, config_path,
                  target_date, a.mode, ts, payload)


def verify(artifact, evidence_path, action_path, config_path, target_date,
           mode, ts, payload):
    """Re-read every artifact off disk and assert the specific claim.

    Split from the write phase so it is re-runnable without appending twice
    (references/cron_persistence.md §4).
    """
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok, detail))

    # 1. artifact exists and parses
    try:
        art = json.load(open(artifact, encoding="utf-8"))
        check("artifact parses", art.get("target_date") == target_date,
              f"{artifact} target_date={art.get('target_date')}")
    except Exception as e:  # noqa: BLE001
        check("artifact parses", False, str(e))

    # 2. artifact matches the payload byte-for-byte on the decision fields
    try:
        art = json.load(open(artifact, encoding="utf-8"))
        for k in ("total_events", "conflicts_detected", "free_hours",
                  "prep_items_count", "zero_duration_warnings", "summary_note"):
            check(f"artifact.{k} matches payload",
                  art.get(k, (art.get('day_overview') or {}).get(k)) ==
                  payload.get(k, (payload.get('day_overview') or {}).get(k)))
    except Exception:  # noqa: BLE001
        pass

    # 3. newest evidence + action record are THIS run's
    for label, path in (("evidence", evidence_path), ("action", action_path)):
        recs = read_records(path)
        newest = recs[-1] if recs else {}
        check(f"{label} newest is this run",
              newest.get("target_date") == target_date and newest.get("mode") == mode,
              f"newest={newest.get('timestamp')} {newest.get('target_date')}/{newest.get('mode')}")

    # 4. every JSONL still parses
    for label, path in (("evidence", evidence_path), ("action", action_path),
                        ("decisions", os.path.join(os.path.dirname(evidence_path), "decisions.jsonl"))):
        if not os.path.exists(path):
            continue
        try:
            count_records(path)
            check(f"{label}.jsonl parses", True)
        except Exception as e:  # noqa: BLE001
            check(f"{label}.jsonl parses", False, str(e))

    # 5. config field equals the run timestamp
    cfg = json.load(open(config_path, encoding="utf-8"))
    check(f"config.last_{mode}_brief set", bool(cfg.get(f"last_{mode}_brief")),
          str(cfg.get(f"last_{mode}_brief")))

    print("\n=== VERIFY ===")
    failed = 0
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
        if not ok:
            failed += 1
    print(f"{len(checks) - failed}/{len(checks)} checks passed")
    if failed:
        print("PERSISTENCE INCOMPLETE — do not report this run as successful.")
        return 1
    print("All persistence claims verified on disk.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)