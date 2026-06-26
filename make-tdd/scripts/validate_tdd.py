#!/usr/bin/env python3
"""
validate_tdd.py — enforce validator rules V-001..V-018 against tdd-data.yaml

Usage:
  python validate_tdd.py docs/tdd-data.yaml [--prd docs/prd-data.yaml]
                         [--tdd-md docs/TDD-<project>.md] [--prev docs/archive/tdd-data-v<old>.yaml]

Exit codes: 0 = pass, 1 = violations found, 2 = file/parse error.

Rules (see assets/tdd-data-schema.yaml for prose):
  Integrity:    V-001 schema well-formed, V-002 ID format + uniqueness,
                V-007 PRD references resolve (--prd), V-009 no vanished IDs
                (--prev), V-013 TDD-internal references resolve,
                V-017 PRD version lock (--prd)
  Completeness: V-003 PRD coverage (--prd), V-004 no orphan decisions,
                V-005 NFRs derive from a req/assumption, V-006 assumption/risk
                owner+status, V-008 diagrams present (--tdd-md),
                V-012 binding constraints have a source
  Status gates: V-010 approved blocks on open high risks / blocking assumptions,
                V-011 status enum, V-014 system_of_record valid,
                V-015 fingerprint matches, V-016 version sync (--tdd-md)
  Impl plan:    V-018 implementation_phases (when present): phase shape, every
                active capability in exactly one active phase, acyclic depends_on

Fingerprint normalization (V-015) — used by BOTH this validator and the Skill
when it writes the data file, so the two never disagree:
  deep-copy the doc, remove meta.fingerprint, yaml.safe_dump(sort_keys=True),
  sha256 the UTF-8 bytes. See compute_fingerprint().
"""
import argparse
import copy
import hashlib
import re
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

TDD_ID_RE = re.compile(r"^(ENT|WF|STM|INTG|ADR|BC|TNF|ASM|RISK|OQ)-\d{3,}$")
PRD_ID_RE = re.compile(r"^(BO|UO|FR|CR|IR|NFR|CON|AS|KU|DEP|RSK|ER|ESC)-\d{3,}$")
CAPABILITY_PREFIXES = ("ENT", "WF", "STM", "INTG", "TNF", "ADR")
STATUS_ENUM = ("draft", "review", "approved", "superseded")
SOR_ENUM = ("claude-project", "git")

# (collection path, id field) for every ID-bearing list in the TDD schema
ID_COLLECTIONS = [
    ("entities", "id"),
    ("state_machines", "id"),
    ("workflows", "id"),
    ("integrations", "id"),
    ("binding_constraints", "id"),
    ("nfrs", "id"),
    ("decisions", "id"),
    ("assumptions", "id"),
    ("risks", "id"),
    ("open_questions", "id"),
]

# Reference fields holding a list of IDs: (collection, field)
REF_FIELDS = [
    ("entities", "satisfies"),
    ("entities", "open_items"),
    ("state_machines", "satisfies"),
    ("workflows", "satisfies"),
    ("integrations", "satisfies"),
    ("integrations", "bounded_by"),
    ("nfrs", "derived_from"),
    ("decisions", "derived_from"),
    ("decisions", "bounded_by"),
    ("open_questions", "blocks"),
    ("change_log", "changed_ids"),
]

# Top-level keys required for a well-formed file (V-001)
REQUIRED_KEYS = [
    "meta", "source_index", "entities", "state_machines", "workflows",
    "integrations", "binding_constraints", "nfrs", "decisions",
    "assumptions", "risks", "open_questions", "traceability", "change_log",
]
REQUIRED_META = [
    "tdd_version", "tdd_status", "system_of_record", "fingerprint",
]

# PRD requirement collections + the priorities that must be covered (V-003)
PRD_REQ_COLLECTIONS = [
    "requirements.functional", "requirements.content",
    "requirements.integration", "requirements.nonfunctional",
    "requirements.environmental",
]
PRD_COVERED_PRIORITIES = ("must", "should")
# All ID-bearing PRD collections, for referential checks (V-007)
PRD_ID_COLLECTIONS = [
    "objectives.business", "objectives.user",
    "requirements.functional", "requirements.content",
    "requirements.integration", "requirements.nonfunctional",
    "requirements.environmental", "constraints", "dependencies",
    "assumptions", "risks", "known_unknowns", "escalations",
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


def collect_prd_ids(prd):
    ids = set()
    for path in PRD_ID_COLLECTIONS:
        for item in get_path(prd, path):
            if isinstance(item, dict) and item.get("id"):
                ids.add(item["id"])
    return ids


def collect_prd_required(prd):
    """PRD must/should requirement IDs that the TDD must account for."""
    req = set()
    for path in PRD_REQ_COLLECTIONS:
        for item in get_path(prd, path):
            if not isinstance(item, dict):
                continue
            if item.get("status", "active") != "active":
                continue
            if item.get("priority") in PRD_COVERED_PRIORITIES and item.get("id"):
                req.add(item["id"])
    return req


def compute_fingerprint(doc):
    """sha256 over the data file with meta.fingerprint removed. Identical
    normalization MUST be used by the Skill when it stamps the fingerprint."""
    d = copy.deepcopy(doc)
    if isinstance(d.get("meta"), dict):
        d["meta"].pop("fingerprint", None)
    normalized = yaml.safe_dump(d, sort_keys=True, default_flow_style=False,
                                allow_unicode=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def md_regions(md_text):
    """Map each ID-anchored heading (e.g. '#### STM-001 — ...') to the text
    from that heading up to the next heading. Used to confirm a diagram lives
    with its record."""
    regions, buf, cur = {}, [], None
    head = re.compile(r"^#{2,4}\s+([A-Z]+-\d{3,})\b")
    any_head = re.compile(r"^#{1,4}\s")
    for line in md_text.splitlines():
        m = head.match(line)
        if m or any_head.match(line):
            if cur is not None:
                regions[cur] = "\n".join(buf)
            buf, cur = [line], (m.group(1) if m else None)
        else:
            buf.append(line)
    if cur is not None:
        regions[cur] = "\n".join(buf)
    return regions


def md_frontmatter_version(md_text):
    m = re.search(r"^---\s*\n(.*?)\n---", md_text, re.S)
    if not m:
        return ""
    fm = yaml.safe_load(m.group(1)) or {}
    return str(fm.get("version") or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_file")
    ap.add_argument("--prd", help="prd-data.yaml (e.g. docs/prd-data.yaml), for V-003 coverage and V-007 references")
    ap.add_argument("--tdd-md", dest="tdd_md", help="TDD markdown (e.g. docs/TDD-<project>.md), for V-008 diagrams and V-016 version sync")
    ap.add_argument("--prev", help="prior tdd-data.yaml (e.g. docs/archive/tdd-data-v<old>.yaml), for V-009 vanished-ID check")
    args = ap.parse_args()

    try:
        with open(args.data_file) as f:
            doc = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"ERROR: cannot parse {args.data_file}: {e}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(doc, dict):
        print(f"ERROR: {args.data_file} is not a YAML mapping", file=sys.stderr)
        sys.exit(2)

    errors = []

    def fail(rule, msg):
        errors.append(f"[{rule}] {msg}")

    meta = doc.get("meta") or {}
    tdd_version = str(meta.get("tdd_version") or "")
    tdd_status = str(meta.get("tdd_status") or "")

    # ---- V-001: schema well-formed -------------------------------------
    for key in REQUIRED_KEYS:
        if key not in doc:
            fail("V-001", f"missing required top-level key '{key}'")
    if not isinstance(doc.get("meta"), dict):
        fail("V-001", "meta block missing or not a mapping")
    else:
        for key in REQUIRED_META:
            if key not in meta:
                fail("V-001", f"meta is missing required field '{key}'")

    # ---- V-002: ID format and uniqueness -------------------------------
    ids, dupes = collect_ids(doc)
    for path, field in ID_COLLECTIONS:
        for item in get_path(doc, path):
            if isinstance(item, dict) and not item.get(field):
                fail("V-002", f"item in {path} is missing required '{field}'")
    for iid in ids:
        if not TDD_ID_RE.match(str(iid)):
            fail("V-002", f"malformed ID '{iid}'")
    for iid, first, second in dupes:
        fail("V-002", f"duplicate ID '{iid}' in {first} and {second}")
    known = set(ids)

    # ---- load --prd once for V-003 / V-007 / V-017 ---------------------
    prd_ids, prd_required, prd_lock_version = set(), set(), ""
    if args.prd:
        try:
            with open(args.prd) as f:
                prd = yaml.safe_load(f) or {}
            prd_ids = collect_prd_ids(prd)
            prd_required = collect_prd_required(prd)
            prd_lock_version = str((prd.get("meta") or {}).get("prd_version") or "")
        except Exception as e:
            fail("V-007", f"could not read --prd data file: {e}")

    # ---- V-017: PRD version lock ---------------------------------------
    # The TDD is locked to the PRD version it was derived from. If the live
    # PRD (--prd) is a different version, the TDD is stale -- re-run make-tdd.
    if args.prd and prd_lock_version:
        tdd_prd_version = str(meta.get("prd_version") or "")
        if tdd_prd_version != prd_lock_version:
            fail("V-017", f"TDD is locked to PRD v{tdd_prd_version or '?'} but --prd "
                          f"is v{prd_lock_version}; the PRD has moved on -- re-run make-tdd")

    # ---- V-013 / V-007: reference resolution ---------------------------
    # TDD-prefixed refs must exist in this doc; PRD-prefixed refs must exist
    # in --prd (when supplied). bounded_by must specifically be a BC- id.
    def check_ref(owner, field, ref):
        ref = str(ref)
        if TDD_ID_RE.match(ref):
            if ref not in known:
                fail("V-013", f"{owner}.{field} references missing TDD ID '{ref}'")
        elif PRD_ID_RE.match(ref):
            if args.prd and ref not in prd_ids:
                fail("V-007", f"{owner}.{field} references PRD ID '{ref}' not in --prd")
        # else: free text / "none" / "" — ignored

    for path, field in REF_FIELDS:
        for item in get_path(doc, path):
            if not isinstance(item, dict):
                continue
            owner = item.get("id") or item.get("version") or path
            for ref in item.get(field) or []:
                check_ref(owner, field, ref)
                if field == "bounded_by" and not str(ref).startswith("BC-"):
                    fail("V-013", f"{owner}.bounded_by '{ref}' is not a BC- id")

    # state_machines.entity is a single ENT- reference
    for sm in get_path(doc, "state_machines"):
        if not isinstance(sm, dict):
            continue
        ent = sm.get("entity")
        if ent:
            if not str(ent).startswith("ENT-"):
                fail("V-013", f"{sm.get('id')}.entity '{ent}' is not an ENT- id")
            elif ent not in known:
                fail("V-013", f"{sm.get('id')}.entity references missing ENT- id '{ent}'")

    # binding_constraints.source.prd_constraint_id -> PRD (V-007)
    for bc in get_path(doc, "binding_constraints"):
        if not isinstance(bc, dict):
            continue
        cid = ((bc.get("source") or {}).get("prd_constraint_id") or "")
        if cid:
            check_ref(bc.get("id"), "source.prd_constraint_id", cid)

    # traceability references + satisfied_by must be capabilities (V-013/V-007)
    for row in get_path(doc, "traceability.mapped"):
        if not isinstance(row, dict):
            continue
        rid = row.get("requirement_id")
        if rid:
            check_ref("traceability", "requirement_id", rid)
        for cap in row.get("satisfied_by") or []:
            check_ref(f"traceability[{rid}]", "satisfied_by", cap)
            cap_str = str(cap)
            prefix = cap_str.split("-")[0] if "-" in cap_str else ""
            if prefix not in CAPABILITY_PREFIXES or not TDD_ID_RE.match(cap_str):
                fail("V-013", f"traceability[{rid}].satisfied_by '{cap}' is not a capability")
    unmapped = doc.get("traceability", {}).get("unmapped") or [] if isinstance(doc.get("traceability"), dict) else []
    for rid in unmapped:
        check_ref("traceability", "unmapped", rid)

    # ---- V-003: PRD coverage -------------------------------------------
    if args.prd:
        covered = set()
        for row in get_path(doc, "traceability.mapped"):
            if isinstance(row, dict) and (row.get("satisfied_by") or []):
                covered.add(row.get("requirement_id"))
        accounted = covered | set(unmapped)
        for rid in sorted(prd_required - accounted):
            fail("V-003", f"PRD requirement '{rid}' is neither mapped (with a "
                          f"satisfier) nor listed in traceability.unmapped")

    # ---- V-004: no orphan decisions ------------------------------------
    for d in get_path(doc, "decisions"):
        if not isinstance(d, dict) or d.get("status") != "active":
            continue
        if not [r for r in (d.get("derived_from") or []) if str(r).strip()]:
            fail("V-004", f"{d.get('id')} has no derived_from (orphan decision)")

    # ---- V-005: NFRs derive from a requirement or assumption -----------
    for n in get_path(doc, "nfrs"):
        if not isinstance(n, dict) or n.get("status") != "active":
            continue
        if not [r for r in (n.get("derived_from") or []) if str(r).strip()]:
            fail("V-005", f"{n.get('id')} has no derived_from")

    # ---- V-006: assumptions and risks have owner + status --------------
    for path in ("assumptions", "risks"):
        for item in get_path(doc, path):
            if not isinstance(item, dict):
                continue
            if not str(item.get("owner") or "").strip():
                fail("V-006", f"{item.get('id')} has no owner")
            if not str(item.get("status") or "").strip():
                fail("V-006", f"{item.get('id')} has no status")

    # ---- V-008: diagrams present (needs --tdd-md) ----------------------
    if args.tdd_md:
        try:
            with open(args.tdd_md) as f:
                md = f.read()
        except Exception as e:
            fail("V-008", f"could not read --tdd-md: {e}")
            md = None
        if md is not None:
            regions = md_regions(md)
            for path in ("state_machines", "workflows"):
                for r in get_path(doc, path):
                    if not isinstance(r, dict) or r.get("status") != "active":
                        continue
                    if r.get("needs_diagram") and "```mermaid" not in regions.get(r.get("id"), ""):
                        fail("V-008", f"{r.get('id')} needs a diagram but no mermaid "
                                      f"block was found under its heading in {args.tdd_md}")
            ent_needs = any(isinstance(e, dict) and e.get("status") == "active"
                            and e.get("needs_diagram") for e in get_path(doc, "entities"))
            if ent_needs and "erdiagram" not in md.lower():
                fail("V-008", "entities need a diagram but no erDiagram block was found")

    # ---- V-009: no vanished IDs vs previous version --------------------
    if args.prev:
        try:
            with open(args.prev) as f:
                prev = yaml.safe_load(f) or {}
            prev_ids, _ = collect_ids(prev)
            for v in sorted(set(prev_ids) - known):
                fail("V-009", f"ID '{v}' existed in previous version and is now "
                              f"missing (supersede or defer; never delete)")
        except Exception as e:
            fail("V-009", f"could not read previous data file: {e}")

    # ---- V-010: approval gate ------------------------------------------
    if tdd_status == "approved":
        for r in get_path(doc, "risks"):
            if isinstance(r, dict) and r.get("severity") == "high" and r.get("status") == "open":
                fail("V-010", f"status approved with open high-severity risk {r.get('id')}")
        for a in get_path(doc, "assumptions"):
            if isinstance(a, dict) and a.get("blocking") and a.get("status") == "open":
                fail("V-010", f"status approved with unresolved blocking assumption {a.get('id')}")

    # ---- V-011: status enum --------------------------------------------
    if tdd_status and tdd_status not in STATUS_ENUM:
        fail("V-011", f"tdd_status '{tdd_status}' is not one of {', '.join(STATUS_ENUM)}")

    # ---- V-012: binding constraints have a source ----------------------
    for bc in get_path(doc, "binding_constraints"):
        if not isinstance(bc, dict):
            continue
        src = bc.get("source") or {}
        if not src.get("type") or not (src.get("ref") or src.get("prd_constraint_id")):
            fail("V-012", f"{bc.get('id')} has no source (need type + a ref or prd_constraint_id)")

    # ---- V-014: system of record ---------------------------------------
    sor = str(meta.get("system_of_record") or "")
    if sor and sor not in SOR_ENUM:
        fail("V-014", f"system_of_record '{sor}' is not one of {', '.join(SOR_ENUM)}")
    if sor == "git":
        repo = meta.get("repo") or {}
        if not str(repo.get("path") or "").strip():
            fail("V-014", "system_of_record is git but meta.repo.path is blank")
        if not str(meta.get("promoted_at") or "").strip():
            fail("V-014", "system_of_record is git but meta.promoted_at is blank")

    # ---- V-015: fingerprint integrity ----------------------------------
    stored = str(meta.get("fingerprint") or "")
    if not stored:
        fail("V-015", "meta.fingerprint is blank")
    else:
        actual = compute_fingerprint(doc)
        if stored != actual:
            fail("V-015", "fingerprint mismatch — data file was edited or has drifted "
                          "(regenerate from the markdown)")

    # ---- V-016: version sync with markdown -----------------------------
    if args.tdd_md:
        try:
            with open(args.tdd_md) as f:
                md_version = md_frontmatter_version(f.read())
            if md_version != tdd_version:
                fail("V-016", f"tdd_version '{tdd_version}' != markdown version '{md_version}'")
        except Exception as e:
            fail("V-016", f"could not read markdown for version check: {e}")

    # ---- V-018: implementation plan (only when phases are present) ------
    # The plan is recommended, not required: an absent/empty collection is
    # valid. When present it must be a total, single-home cover of the active
    # capabilities with an acyclic phase order. Phase lives only here (not on a
    # capability record), so a phase move never touches a per-capability
    # fingerprint -- a re-sequence is sequencing, not a contract change.
    phases = doc.get("implementation_phases") or []
    if phases:
        active_caps = set()
        for path in ("entities", "state_machines", "workflows",
                     "integrations", "nfrs", "decisions"):
            for item in get_path(doc, path):
                if (isinstance(item, dict) and item.get("id")
                        and item.get("status", "active") == "active"):
                    active_caps.add(str(item["id"]))

        seen_numbers, phase_nums, assigned = {}, set(), {}
        for ph in phases:
            if not isinstance(ph, dict):
                fail("V-018", "an implementation_phases entry is not a mapping")
                continue
            num = ph.get("number")
            name = str(ph.get("name") or "").strip()
            status = str(ph.get("status") or "")
            if not isinstance(num, int) or isinstance(num, bool) or num < 1:
                fail("V-018", f"phase '{name or num}' needs an integer number >= 1")
            elif num in seen_numbers:
                fail("V-018", f"duplicate phase number {num}")
            else:
                seen_numbers[num] = name
                phase_nums.add(num)
            if not name:
                fail("V-018", f"phase {num} has no name")
            if status not in ("active", "superseded", "deferred"):
                fail("V-018", f"phase {num} status '{status}' is not "
                              "active | superseded | deferred")
            for cap in ph.get("capabilities") or []:
                cap = str(cap)
                if cap not in known:
                    fail("V-018", f"phase {num} lists '{cap}', not a TDD ID")
                elif cap not in active_caps:
                    fail("V-018", f"phase {num} lists '{cap}', not an active capability")
                if status == "active":
                    assigned.setdefault(cap, []).append(num)

        for cap in sorted(active_caps):
            homes = assigned.get(cap, [])
            if not homes:
                fail("V-018", f"active capability '{cap}' is not assigned to any "
                              "active phase")
            elif len(homes) > 1:
                fail("V-018", f"active capability '{cap}' is assigned to multiple "
                              f"phases {sorted(homes)} (assign it to exactly one)")

        graph = {}
        for ph in phases:
            if not isinstance(ph, dict):
                continue
            num = ph.get("number")
            deps = []
            for d in ph.get("depends_on") or []:
                if d not in phase_nums:
                    fail("V-018", f"phase {num} depends_on {d}, not a phase number")
                elif d == num:
                    fail("V-018", f"phase {num} depends on itself")
                else:
                    deps.append(d)
            graph[num] = deps

        WHITE, GREY, BLACK = 0, 1, 2
        color = {n: WHITE for n in graph}

        def visit(n, stack):
            color[n] = GREY
            for m in graph.get(n, []):
                if color.get(m) == GREY:
                    cyc = " -> ".join(str(x) for x in stack[stack.index(m):] + [m])
                    fail("V-018", f"phase dependency cycle: {cyc}")
                elif color.get(m) == WHITE:
                    visit(m, stack + [m])
            color[n] = BLACK

        for n in list(graph):
            if color.get(n) == WHITE:
                visit(n, [n])

    # ---- report ---------------------------------------------------------
    if errors:
        print(f"FAIL — {len(errors)} violation(s) in {args.data_file}\n")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    print(f"PASS — {args.data_file} "
          f"(version {tdd_version or '?'}, {len(known)} IDs, status {tdd_status or '?'})")
    sys.exit(0)


if __name__ == "__main__":
    main()
