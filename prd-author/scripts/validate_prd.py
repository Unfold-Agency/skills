#!/usr/bin/env python3
"""
validate_prd.py — enforce validator rules V-001..V-016 against prd-data.yaml

Usage:
  python validate_prd.py <prd-data.yaml> [--prd-md <PRD.md>] [--prev <previous-prd-data.yaml>]

Exit codes: 0 = pass, 1 = violations found, 2 = file/parse error.

Rules (see assets/prd-data-schema.yaml for prose):
  Integrity:    V-001 version sync, V-002 ID format, V-003 no duplicate IDs,
                V-004 no dangling references, V-005 no vanished IDs vs --prev
  Completeness: V-006 FR failure paths, V-007 measurable objectives,
                V-008 sources or KU coverage, V-009 source handles resolve,
                V-010 FR feature_area in scope
  Status gates: V-011 approved blocks on open conflicts,
                V-012 approved blocks on open escalations,
                V-013 major changes need approvals,
                V-014 escalation decisions need a validator,
                V-015 escalation-triggered changes reference a decided ESC,
                V-016 blank baselines need a KU reference
"""
import argparse
import re
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

ID_RE = re.compile(r"^(BO|UO|FR|CR|IR|NFR|CON|AS|KU|DEP|RSK|ER|ESC)-\d{3,}$")

# (collection path, id field) for every ID-bearing list in the schema
ID_COLLECTIONS = [
    ("objectives.business", "id"),
    ("objectives.user", "id"),
    ("requirements.functional", "id"),
    ("requirements.content", "id"),
    ("requirements.integration", "id"),
    ("requirements.nonfunctional", "id"),
    ("requirements.environmental", "id"),
    ("constraints", "id"),
    ("dependencies", "id"),
    ("assumptions", "id"),
    ("risks", "id"),
    ("known_unknowns", "id"),
    ("escalations", "id"),
]

# Fields that hold references to other IDs: (collection, field)
REF_FIELDS = [
    ("requirements.functional", "supports"),
    ("requirements.functional", "depends_on"),
    ("requirements.functional", "open_items"),
    ("requirements.environmental", "supports"),
    ("requirements.nonfunctional", "derived_from"),
    ("dependencies", "blocks"),
    ("known_unknowns", "blocks"),
    ("escalations", "affected_ids"),
    ("change_log", "changed_ids"),
]

# Collections whose active items need sources (V-008)
SOURCED_COLLECTIONS = [
    "objectives.business", "objectives.user",
    "requirements.functional", "requirements.content",
    "requirements.integration", "requirements.environmental",
    "constraints", "assumptions",
]


def get_path(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or cur.get(part) is None:
            return []
        cur = cur[part]
    return cur if isinstance(cur, list) else []


def collect_ids(doc):
    ids, dupes = {}, []
    for path, field in ID_COLLECTIONS:
        for item in get_path(doc, path):
            if not isinstance(item, dict):
                continue
            iid = item.get(field)
            if not iid:
                continue
            if iid in ids:
                dupes.append((iid, ids[iid], path))
            else:
                ids[iid] = path
    return ids, dupes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_file")
    ap.add_argument("--prd-md", help="PRD markdown master, for V-001 version sync")
    ap.add_argument("--prev", help="prior prd-data.yaml, for V-005 vanished-ID check")
    args = ap.parse_args()

    try:
        with open(args.data_file) as f:
            doc = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"ERROR: cannot parse {args.data_file}: {e}", file=sys.stderr)
        sys.exit(2)

    errors = []
    warn = []

    def fail(rule, msg):
        errors.append(f"[{rule}] {msg}")

    meta = doc.get("meta") or {}
    prd_version = str(meta.get("prd_version") or "")
    prd_status = str(meta.get("prd_status") or "")

    # ---- V-001: version sync with markdown frontmatter -----------------
    if args.prd_md:
        try:
            with open(args.prd_md) as f:
                md = f.read()
            m = re.search(r"^---\s*\n(.*?)\n---", md, re.S)
            md_version = ""
            if m:
                fm = yaml.safe_load(m.group(1)) or {}
                md_version = str(fm.get("version") or "")
            if md_version != prd_version:
                fail("V-001", f"prd_version '{prd_version}' != markdown version '{md_version}'")
        except Exception as e:
            fail("V-001", f"could not read markdown for version check: {e}")
    elif not prd_version:
        fail("V-001", "meta.prd_version is blank")

    # ---- V-002 / V-003: ID format and duplicates -----------------------
    ids, dupes = collect_ids(doc)
    for iid in ids:
        if not ID_RE.match(str(iid)):
            fail("V-002", f"malformed ID '{iid}'")
    for iid, first, second in dupes:
        fail("V-003", f"duplicate ID '{iid}' in {first} and {second}")

    # ---- V-004: dangling references -------------------------------------
    known = set(ids)
    for path, field in REF_FIELDS:
        for item in get_path(doc, path):
            if not isinstance(item, dict):
                continue
            for ref in item.get(field) or []:
                if ref in ("default",) or not ID_RE.match(str(ref)):
                    continue  # non-ID values handled elsewhere
                if ref not in known:
                    owner = item.get("id") or item.get("version") or path
                    fail("V-004", f"{owner}.{field} references missing ID '{ref}'")

    # ---- V-005: no vanished IDs vs previous version --------------------
    if args.prev:
        try:
            with open(args.prev) as f:
                prev = yaml.safe_load(f) or {}
            prev_ids, _ = collect_ids(prev)
            vanished = sorted(set(prev_ids) - known)
            for v in vanished:
                fail("V-005", f"ID '{v}' existed in previous version and is now missing "
                              f"(supersede or defer; never delete)")
        except Exception as e:
            fail("V-005", f"could not read previous data file: {e}")

    # ---- V-006: FR acceptance criteria incl. failure/edge path ---------
    for fr in get_path(doc, "requirements.functional"):
        if not isinstance(fr, dict) or fr.get("status") != "active":
            continue
        acs = fr.get("acceptance_criteria") or []
        if not acs:
            fail("V-006", f"{fr.get('id')} has no acceptance criteria")
            continue
        if not any((ac or {}).get("path") in ("failure", "edge") for ac in acs):
            fail("V-006", f"{fr.get('id')} has no failure/edge-path criterion")

    # ---- V-007: objectives measurable -----------------------------------
    for path in ("objectives.business", "objectives.user"):
        for ob in get_path(doc, path):
            if not isinstance(ob, dict) or ob.get("status") != "active":
                continue
            scs = ob.get("success_criteria") or []
            if not scs or not all((sc or {}).get("measurement_method") for sc in scs):
                fail("V-007", f"{ob.get('id')} lacks a success criterion with a measurement_method")

    # ---- V-008 / V-009: sources present and handles resolve ------------
    handles = {s.get("handle") for s in get_path(doc, "source_index") if isinstance(s, dict)}
    ku_blocked = set()
    for ku in get_path(doc, "known_unknowns"):
        if isinstance(ku, dict) and ku.get("status") == "open":
            ku_blocked.update(ku.get("blocks") or [])
    for path in SOURCED_COLLECTIONS:
        for item in get_path(doc, path):
            if not isinstance(item, dict) or item.get("status") != "active":
                continue
            srcs = item.get("sources") or []
            if not srcs:
                if item.get("id") not in ku_blocked:
                    fail("V-008", f"{item.get('id')} has no sources and no open KU covering it")
                continue
            for s in srcs:
                h = (s or {}).get("handle")
                if h and h not in handles:
                    fail("V-009", f"{item.get('id')} cites unknown source handle '{h}'")

    # ---- V-010: FR feature areas exist in scope -------------------------
    areas = {s.get("feature_area") for s in get_path(doc, "scope.in_scope") if isinstance(s, dict)}
    for fr in get_path(doc, "requirements.functional"):
        if isinstance(fr, dict) and fr.get("status") == "active":
            if fr.get("feature_area") and fr["feature_area"] not in areas:
                fail("V-010", f"{fr.get('id')} feature_area '{fr['feature_area']}' not in scope.in_scope")

    # ---- V-011 / V-012: approval gates ----------------------------------
    if prd_status == "approved":
        for c in get_path(doc, "conflicts"):
            if isinstance(c, dict) and c.get("status") == "open":
                fail("V-011", f"status approved with open conflict #{c.get('number')}")
        for e in get_path(doc, "escalations"):
            if isinstance(e, dict) and e.get("status") in ("raised", "validated"):
                fail("V-012", f"status approved with undecided escalation {e.get('id')}")

    # ---- V-013: major change_log entries need approvals -----------------
    for cl in get_path(doc, "change_log"):
        if isinstance(cl, dict) and cl.get("change_class") == "major":
            if not cl.get("approvals"):
                fail("V-013", f"change_log v{cl.get('version')} is major but has no approvals")

    # ---- V-014 / V-015: escalation discipline ---------------------------
    esc_status = {}
    for e in get_path(doc, "escalations"):
        if not isinstance(e, dict):
            continue
        esc_status[e.get("id")] = e.get("status")
        if e.get("decision") and not e.get("validator"):
            fail("V-014", f"{e.get('id')} has a decision but no named validator")
    for cl in get_path(doc, "change_log"):
        if not isinstance(cl, dict):
            continue
        tb = cl.get("triggered_by") or {}
        if tb.get("type") == "escalation":
            ref = tb.get("ref")
            if esc_status.get(ref) not in ("decided", "closed"):
                fail("V-015", f"change_log v{cl.get('version')} triggered by escalation "
                              f"'{ref}' which is not decided/closed")

    # ---- V-016: blank baselines need a KU --------------------------------
    for ob in get_path(doc, "objectives.business"):
        if not isinstance(ob, dict) or ob.get("status") != "active":
            continue
        for sc in ob.get("success_criteria") or []:
            sc = sc or {}
            if "baseline" in sc and not sc.get("baseline"):
                ku = sc.get("baseline_ku")
                if not ku or ku not in known:
                    fail("V-016", f"{ob.get('id')} has a blank baseline without a valid baseline_ku")

    # ---- report ----------------------------------------------------------
    if errors:
        print(f"FAIL — {len(errors)} violation(s) in {args.data_file}\n")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    print(f"PASS — {args.data_file} "
          f"(version {prd_version or '?'}, {len(known)} IDs, status {prd_status or '?'})")
    for w in warn:
        print(f"  note: {w}")
    sys.exit(0)


if __name__ == "__main__":
    main()