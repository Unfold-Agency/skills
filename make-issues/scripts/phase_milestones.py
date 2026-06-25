#!/usr/bin/env python3
"""Map TDD implementation phases to GitHub milestones for make-issues.

A TDD's `implementation_phases` (authored in make-tdd) groups the active
capabilities into ordered, shippable phases. make-issues turns each phase into
ONE GitHub milestone -- title "Phase <number>: <name>" -- and assigns every
issue to the milestone for the phase its capability belongs to. do-work
--phase=<N> then drains a single phase.

Phase is sequencing, not contract. It lives ONLY in the TDD's
implementation_phases -- never on a capability record and never in the issue
meta block -- so a capability moving phases does NOT change its per-capability
fingerprint (item_fingerprint.py). The milestone is the operative store, like a
native dependency edge: derived from the TDD and re-asserted on every sync. The
leading "Phase <number>" of the title is the stable key both this skill and
do-work match on; the name is a human label that may change.

  python scripts/phase_milestones.py <tdd-data.yaml>                 # human-readable maps
  python scripts/phase_milestones.py <tdd-data.yaml> --json          # {cap_to_phase, phase_title, ...}
  python scripts/phase_milestones.py <tdd-data.yaml> --trace WF-001,INTG-001
  python scripts/phase_milestones.py <tdd-data.yaml> --ensure --repo owner/name

Exit codes: 0 = ok, 1 = bad args / unresolved, 2 = file/parse error,
            3 = a gh call failed (with --ensure).
"""
import argparse
import json
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

PHASE_TITLE_RE = re.compile(r"^Phase\s+(\d+)\b")


def milestone_title(number, name):
    """The stable milestone title. 'Phase <number>' is the key; the name labels it."""
    name = " ".join(str(name or "").split())
    return f"Phase {number}: {name}" if name else f"Phase {number}"


def parse_phase_ordinal(title):
    """The integer N from a 'Phase N: ...' milestone title, or None."""
    m = PHASE_TITLE_RE.match(str(title or "").strip())
    return int(m.group(1)) if m else None


def active_phases(doc):
    """Active implementation_phases, sorted by number. [] when there is no plan."""
    out = []
    for ph in doc.get("implementation_phases") or []:
        if (isinstance(ph, dict) and ph.get("status", "active") == "active"
                and isinstance(ph.get("number"), int)
                and not isinstance(ph.get("number"), bool)):
            out.append(ph)
    out.sort(key=lambda p: p["number"])
    return out


def build_maps(doc):
    """Return (cap_to_phase, phase_meta) from the active plan.
    cap_to_phase[cap_id] -> phase number (the latest phase listing it, if >1).
    phase_meta[number]   -> {"title", "name", "summary"}.
    """
    cap_to_phase, phase_meta = {}, {}
    for ph in active_phases(doc):
        num = ph["number"]
        name = ph.get("name") or ""
        phase_meta[num] = {
            "title": milestone_title(num, name),
            "name": name,
            "summary": " ".join(str(ph.get("summary") or "").split()),
        }
        for cap in ph.get("capabilities") or []:
            cap = str(cap)
            if cap not in cap_to_phase or num > cap_to_phase[cap]:
                cap_to_phase[cap] = num   # latest phase wins on a (bad) double-listing
    return cap_to_phase, phase_meta


def phase_for_trace(trace_tdd, cap_to_phase):
    """The phase an issue belongs to, from its trace_tdd capability IDs.

    Rule: the LATEST phase among its capabilities -- an issue cannot complete
    until its last-phase capability is in play. Returns (number, spanned,
    mapped_caps): number is None if no traced capability is in the plan; spanned
    is True when the traced caps fall in more than one phase (a slicing smell to
    report, not an error)."""
    nums = sorted({cap_to_phase[c] for c in (trace_tdd or []) if c in cap_to_phase})
    if not nums:
        return None, False, []
    mapped = [c for c in trace_tdd if c in cap_to_phase]
    return nums[-1], len(nums) > 1, mapped


# ── GitHub side (only used by --ensure) ──────────────────────────────────
def _run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"


def _list_milestones(repo):
    rc, out, err = _run(["gh", "api", "--paginate",
                         f"repos/{repo}/milestones?state=all&per_page=100"])
    if rc != 0:
        return None, err.strip() or "gh api failed"
    try:
        data = json.loads(out or "[]")
    except json.JSONDecodeError as e:
        return None, f"bad JSON from gh: {e}"
    return (data if isinstance(data, list) else []), None


def ensure_milestones(repo, phase_meta):
    """Idempotently create/patch one milestone per active phase, keyed on the
    leading 'Phase <number>' so a renamed phase patches its title in place rather
    than orphaning the old milestone (its issues stay attached). Returns
    ({"actions", "title_to_num"}, None) or (None, error)."""
    existing, err = _list_milestones(repo)
    if existing is None:
        return None, err
    by_num = {}
    for ms in existing:
        n = parse_phase_ordinal(ms.get("title"))
        if n is not None:
            by_num[n] = ms

    actions = {"created": [], "updated": [], "unchanged": []}
    title_to_num = {}
    for num in sorted(phase_meta):
        want_title = phase_meta[num]["title"]
        want_desc = phase_meta[num]["summary"]
        ms = by_num.get(num)
        if ms is None:
            rc, out, e = _run(["gh", "api", f"repos/{repo}/milestones", "-X", "POST",
                               "-f", f"title={want_title}", "-f", f"description={want_desc}"])
            if rc != 0:
                return None, f"create '{want_title}': {e.strip()}"
            actions["created"].append(want_title)
            try:
                title_to_num[want_title] = json.loads(out).get("number")
            except (json.JSONDecodeError, AttributeError):
                pass
        else:
            number = ms.get("number")
            title_to_num[want_title] = number
            if (ms.get("title") or "") != want_title or (ms.get("description") or "") != want_desc:
                rc, _, e = _run(["gh", "api", f"repos/{repo}/milestones/{number}",
                                 "-X", "PATCH", "-f", f"title={want_title}",
                                 "-f", f"description={want_desc}"])
                if rc != 0:
                    return None, f"update milestone {number}: {e.strip()}"
                actions["updated"].append(want_title)
            else:
                actions["unchanged"].append(want_title)
    return {"actions": actions, "title_to_num": title_to_num}, None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data_file", help="tdd-data.yaml")
    ap.add_argument("--json", action="store_true", help="emit the maps as JSON")
    ap.add_argument("--trace", help="comma-separated trace_tdd IDs; print that issue's phase")
    ap.add_argument("--ensure", action="store_true",
                    help="create/patch the GitHub milestones (needs --repo)")
    ap.add_argument("--repo", help="owner/name (required with --ensure)")
    args = ap.parse_args()

    try:
        with open(args.data_file, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        print(f"ERROR: cannot read {args.data_file}: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(doc, dict):
        print(f"ERROR: {args.data_file} is not a YAML mapping", file=sys.stderr)
        sys.exit(2)

    cap_to_phase, phase_meta = build_maps(doc)

    if args.trace is not None:
        trace = [t.strip() for t in args.trace.split(",") if t.strip()]
        num, spanned, mapped = phase_for_trace(trace, cap_to_phase)
        if args.json:
            print(json.dumps({"phase": num,
                              "milestone": phase_meta.get(num, {}).get("title"),
                              "spanned": spanned, "mapped_caps": mapped}, indent=2))
        elif num is None:
            print("no phase (no traced capability is in the plan)")
        else:
            extra = "  [spans multiple phases -- consider re-slicing]" if spanned else ""
            print(f"phase {num} -> \"{phase_meta[num]['title']}\"{extra}")
        sys.exit(0)

    if args.ensure:
        if not args.repo:
            print("ERROR: --ensure requires --repo owner/name", file=sys.stderr)
            sys.exit(1)
        if not phase_meta:
            print("No implementation_phases in the TDD; nothing to ensure.")
            sys.exit(0)
        res, err = ensure_milestones(args.repo, phase_meta)
        if res is None:
            print(f"ERROR: {err}", file=sys.stderr)
            sys.exit(3)
        a = res["actions"]
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Milestones for {args.repo}: {len(a['created'])} created, "
                  f"{len(a['updated'])} updated, {len(a['unchanged'])} unchanged")
            for t in a["created"]:
                print(f"  + {t}")
            for t in a["updated"]:
                print(f"  ~ {t}")
        sys.exit(0)

    if args.json:
        print(json.dumps({
            "cap_to_phase": cap_to_phase,
            "phase_title": {str(n): m["title"] for n, m in phase_meta.items()},
            "phases": [{"number": n, **phase_meta[n]} for n in sorted(phase_meta)],
        }, indent=2, sort_keys=True))
        sys.exit(0)

    if not phase_meta:
        print(f"No implementation_phases in {args.data_file} (the plan is optional).")
        sys.exit(0)
    for n in sorted(phase_meta):
        caps = sorted(c for c, p in cap_to_phase.items() if p == n)
        print(f"Phase {n}: {phase_meta[n]['name']}  ->  milestone \"{phase_meta[n]['title']}\"")
        print(f"  capabilities: {', '.join(caps) or '(none)'}")
    sys.exit(0)


if __name__ == "__main__":
    main()
