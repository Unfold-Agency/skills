#!/usr/bin/env python3
"""
validate_spec.py -- enforce validator rules S-001..S-012 across docs/specs/

Validates the whole spec set at once (the overview + every feature), because
the interesting rules are cross-document: the feature index must agree with the
feature files (S-008), prefixes must be unique across features (S-007), and
no-vanishing diffs the UNION of ids against a git baseline (S-005).

Usage:
  python validate_spec.py [docs/specs] [--baseline-ref origin/main | --no-baseline]
                          [--budget-reqs 12] [--budget-words 1200]

Exit codes: 0 = pass (S-012 budget warnings do not fail), 1 = violations,
            2 = file/parse/usage error.

THE KEYSTONE (S-006): meta.fingerprint is recomputed over CONTRACT content only
(the IN/OUT contract in assets/spec-data-schema.yaml) and the run FAILS CLOSED
on any mismatch. A change of meaning (an acceptance criterion, a description, a
governed_by link) flips the fingerprint and blocks the run until the Skill
re-derives and re-stamps; an advisory change (priority, notes) does neither.

NO-VANISHING (S-005) is checked against a named git ref (default origin/main)
and FAILS CLOSED when the baseline cannot be trusted -- no git repo, a shallow
clone, or an unresolvable ref. Pass --no-baseline only for the greenfield
kickoff, before main carries the docs.
"""
import argparse
import copy
import hashlib
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

# ── ID grammars (S-002) ──────────────────────────────────────────────
GOAL_ID_RE = re.compile(r"^G-\d{3,}$")
REQ_ID_RE = re.compile(r"^(FR|IR|NFR|CR)-([A-Z]{2,5})-\d{3,}$")
ADR_ID_RE = re.compile(r"^ADR-\d{4}$")
PREFIX_RE = re.compile(r"^[A-Z]{2,5}$")
STATUS_ENUM = ("active", "superseded", "deferred")
DOC_STATUS_ENUM = ("draft", "review", "approved")

# ── Fingerprint IN/OUT contract (S-006) ──────────────────────────────
# Keys dropped before hashing. Changing any of these never flips the
# fingerprint; everything else is contract content and does.
OUT_KEYS = {
    "priority", "architecture_hints", "related_files", "notes",
    "fingerprint", "feature_version", "generated_at", "project_version",
    "appetite",
}


def _strip_out(obj):
    if isinstance(obj, dict):
        return {k: _strip_out(v) for k, v in obj.items() if k not in OUT_KEYS}
    if isinstance(obj, list):
        return [_strip_out(x) for x in obj]
    return obj


def compute_fingerprint(doc):
    """sha256 over the data file with the OUT fields removed everywhere.
    The Skill's stamp step uses this identical normalization, so the two
    never disagree. meta.feature_version is the first 12 hex of this digest."""
    stripped = _strip_out(copy.deepcopy(doc))
    normalized = yaml.safe_dump(stripped, sort_keys=True, default_flow_style=False,
                                allow_unicode=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ── EARS grammar (S-010/S-011) ───────────────────────────────────────
# Five templates, enumerated in references/ears-grammar.md. Every acceptance
# criterion must classify as exactly one; the response verb "shall" is required.
SHALL_RE = re.compile(r"\bshall\b")  # matched as a WORD, so 'marshall'/'shallow' do not count


def ears_kind(text):
    """Return one of event|state|optional|unwanted|ubiquitous, or None if the
    sentence is not valid EARS."""
    t = " ".join(str(text or "").split())
    low = t.lower()
    m_shall = SHALL_RE.search(low)
    if not m_shall:
        return None
    if low.startswith("when "):
        return "event"
    if low.startswith("while "):
        return "state"
    if low.startswith("where "):
        return "optional"
    if low.startswith("if "):
        m_then = re.search(r"\bthen\b", low)
        if m_then and m_then.start() < m_shall.start():
            return "unwanted"
        return None  # IF without a THEN-before-shall is malformed
    # No leading EARS keyword + a "shall" response = ubiquitous.
    return "ubiquitous"


# ── loading ──────────────────────────────────────────────────────────
def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def feature_files(spec_dir):
    """Return [(slug, md_path, data_path)] for every features/<slug>-data.yaml."""
    fdir = os.path.join(spec_dir, "features")
    out = []
    if not os.path.isdir(fdir):
        return out
    for name in sorted(os.listdir(fdir)):
        if name.endswith("-data.yaml"):
            slug = name[: -len("-data.yaml")]
            out.append((slug, os.path.join(fdir, f"{slug}.md"),
                        os.path.join(fdir, name)))
    return out


def feature_ids(doc):
    return [r.get("id") for r in (doc.get("requirements") or [])
            if isinstance(r, dict) and r.get("id")]


def overview_ids(doc):
    return [g.get("id") for g in (doc.get("goals") or [])
            if isinstance(g, dict) and g.get("id")]


def ids_from_any(doc):
    """Union of ID-bearing items in either shape -- for the no-vanishing diff."""
    if not isinstance(doc, dict):
        return set()
    return set(filter(None, feature_ids(doc))) | set(filter(None, overview_ids(doc)))


# ── git baseline for no-vanishing (S-005), fail-closed ───────────────
def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def baseline_ids(spec_dir, ref, fail):
    """Collect the UNION of ids across every *-data.yaml under spec_dir at the
    baseline ref. Returns a set, or None if the baseline cannot be trusted
    (the caller has already recorded the fail-closed S-005 violation)."""
    cwd = os.path.abspath(spec_dir)
    inside = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        fail("S-005", "not a git repository -- cannot establish a no-vanishing "
                      "baseline (use --no-baseline only for the greenfield kickoff)")
        return None
    shallow = _git(["rev-parse", "--is-shallow-repository"], cwd)
    if shallow.returncode != 0 or shallow.stdout.strip() == "true":
        fail("S-005", "shallow or unverifiable repository -- the baseline may be "
                      "truncated; run 'git fetch --unshallow' (refusing to pass on "
                      "partial history)")
        return None
    resolved = _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd)
    if resolved.returncode != 0:
        fail("S-005", f"cannot resolve baseline ref '{ref}' -- fetch it or pass "
                      "--no-baseline for the greenfield kickoff")
        return None
    # List the spec dir's tree at the baseline. Run from spec_dir with pathspec
    # '.' (git pathspecs are cwd-relative); from a subdir, ls-tree prints
    # CWD-relative paths, so `git show` must use the `:./` form (also
    # cwd-relative) to match. If the dir does not exist at the baseline
    # (greenfield against a resolvable main), the listing is empty -- nothing
    # prior, nothing can vanish.
    listing = _git(["ls-tree", "-r", "--name-only", ref, "--", "."], cwd)
    if listing.returncode != 0:
        fail("S-005", f"cannot list the spec tree at '{ref}' (git ls-tree failed: "
                      f"{listing.stderr.strip()}) -- baseline unusable, refusing to pass")
        return None
    ids = set()
    for path in listing.stdout.splitlines():
        if not path.endswith("-data.yaml"):
            continue
        show = _git(["show", f"{ref}:./{path}"], cwd)
        if show.returncode != 0:
            fail("S-005", f"cannot read '{path}' at '{ref}' (git show failed: "
                          f"{show.stderr.strip()}) -- baseline incomplete, refusing to pass")
            return None
        try:
            ids |= ids_from_any(yaml.safe_load(show.stdout) or {})
        except yaml.YAMLError:
            continue  # an unparseable historical file can't witness an id
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_dir", nargs="?", default="docs/specs",
                    help="the spec directory (default docs/specs)")
    ap.add_argument("--baseline-ref", default="origin/main",
                    help="git ref for the no-vanishing baseline (default origin/main)")
    ap.add_argument("--no-baseline", action="store_true",
                    help="skip S-005 -- only for the greenfield kickoff")
    ap.add_argument("--budget-reqs", type=int, default=12,
                    help="lean budget: warn above this many reqs per feature")
    ap.add_argument("--budget-words", type=int, default=1200,
                    help="lean budget: warn above this many words per feature md")
    args = ap.parse_args()

    spec_dir = args.spec_dir
    overview_path = os.path.join(spec_dir, "overview-data.yaml")
    if not os.path.isfile(overview_path):
        print(f"ERROR: no overview-data.yaml under {spec_dir}", file=sys.stderr)
        sys.exit(2)

    errors, warns = [], []

    def fail(rule, msg):
        errors.append(f"[{rule}] {msg}")

    def warn(rule, msg):
        warns.append(f"[{rule}] {msg}")

    # ---- load everything ------------------------------------------------
    try:
        overview = load_yaml(overview_path)
    except Exception as e:
        print(f"ERROR: cannot parse {overview_path}: {e}", file=sys.stderr)
        sys.exit(2)
    feats = []  # (slug, md_path, data_path, doc)
    for slug, md_path, data_path in feature_files(spec_dir):
        try:
            feats.append((slug, md_path, data_path, load_yaml(data_path)))
        except Exception as e:
            fail("S-001", f"cannot parse {data_path}: {e}")

    # ---- S-001: well-formed --------------------------------------------
    o_meta = overview.get("meta") or {}
    if not isinstance(overview.get("meta"), dict):
        fail("S-001", "overview-data.yaml: meta block missing or not a mapping")
    for key in ("project_version", "mode", "status", "fingerprint"):
        if key not in o_meta:
            fail("S-001", f"overview-data.yaml: meta missing '{key}'")
    if "feature_index" not in overview:
        fail("S-001", "overview-data.yaml: missing 'feature_index'")
    for slug, _md, dpath, doc in feats:
        m = doc.get("meta") or {}
        if not isinstance(doc.get("meta"), dict):
            fail("S-001", f"{dpath}: meta block missing or not a mapping")
        for key in ("slug", "prefix", "status", "fingerprint"):
            if key not in m:
                fail("S-001", f"{dpath}: meta missing '{key}'")
        if "requirements" not in doc:
            fail("S-001", f"{dpath}: missing 'requirements'")

    # ---- S-006: fingerprint integrity (FAIL CLOSED -- the keystone) ------
    def check_fingerprint(label, doc):
        m = doc.get("meta") or {}
        stored = str(m.get("fingerprint") or "")
        if not stored:
            fail("S-006", f"{label}: meta.fingerprint is blank")
            return
        actual = compute_fingerprint(doc)
        if stored != actual:
            fail("S-006", f"{label}: fingerprint mismatch -- the data file drifted "
                          "from its markdown or was hand-edited (re-derive and re-stamp)")

    check_fingerprint("overview-data.yaml", overview)
    for slug, _md, dpath, doc in feats:
        check_fingerprint(dpath, doc)

    # ---- S-002 / S-003 / S-007: ids, uniqueness, namespacing -----------
    all_ids = {}          # id -> location, for global uniqueness + ref resolution
    prefixes = {}         # prefix -> slug, for uniqueness across features

    def register(iid, where):
        if iid in all_ids:
            fail("S-003", f"duplicate ID '{iid}' in {where} and {all_ids[iid]}")
        else:
            all_ids[iid] = where

    for g in overview.get("goals") or []:
        if not isinstance(g, dict):
            continue
        gid = g.get("id")
        if not gid:
            fail("S-002", "overview goal is missing 'id'")
            continue
        if not GOAL_ID_RE.match(str(gid)):
            fail("S-002", f"malformed goal id '{gid}' (want ^G-\\d{{3,}}$)")
        register(gid, "overview")

    for slug, _md, dpath, doc in feats:
        m = doc.get("meta") or {}
        prefix = str(m.get("prefix") or "")
        if not PREFIX_RE.match(prefix):
            fail("S-007", f"{dpath}: prefix '{prefix}' must match ^[A-Z]{{2,5}}$")
        elif prefix in prefixes:
            fail("S-003", f"{dpath}: prefix '{prefix}' already used by feature "
                          f"'{prefixes[prefix]}'")
        else:
            prefixes[prefix] = slug
        if m.get("slug") and m.get("slug") != slug:
            fail("S-008", f"{dpath}: meta.slug '{m.get('slug')}' != file slug '{slug}'")
        for r in doc.get("requirements") or []:
            if not isinstance(r, dict):
                continue
            rid = r.get("id")
            if not rid:
                fail("S-002", f"{dpath}: a requirement is missing 'id'")
                continue
            mo = REQ_ID_RE.match(str(rid))
            if not mo:
                fail("S-002", f"{dpath}: malformed requirement id '{rid}' "
                              "(want ^(FR|IR|NFR|CR)-[A-Z]{2,5}-\\d{3,}$)")
            elif prefix and mo.group(2) != prefix:
                fail("S-007", f"{dpath}: id '{rid}' namespace '{mo.group(2)}' "
                              f"!= feature prefix '{prefix}'")
            register(rid, dpath)

    known_ids = set(all_ids)

    # ---- decisions dir for governed_by resolution (S-004) --------------
    dec_dir = os.path.join(spec_dir, "decisions")
    adr_files = set()
    if os.path.isdir(dec_dir):
        for name in os.listdir(dec_dir):
            mo = re.match(r"^(ADR-\d{4})", name)
            if mo and name.endswith(".md"):
                adr_files.add(mo.group(1))

    # ---- S-004 / S-010 / S-011: per-requirement references + EARS ------
    for slug, _md, dpath, doc in feats:
        for r in doc.get("requirements") or []:
            if not isinstance(r, dict) or r.get("status") not in (None, "active"):
                continue  # superseded/deferred reqs are kept but not enforced
            rid = r.get("id") or "?"
            for dep in r.get("depends_on") or []:
                if not REQ_ID_RE.match(str(dep)):
                    fail("S-004", f"{dpath}: {rid}.depends_on '{dep}' is not a "
                                  "requirement id")
                elif dep not in known_ids:
                    fail("S-004", f"{dpath}: {rid}.depends_on references missing "
                                  f"id '{dep}'")
            for adr in r.get("governed_by") or []:
                if not ADR_ID_RE.match(str(adr)):
                    fail("S-004", f"{dpath}: {rid}.governed_by '{adr}' is not an "
                                  "ADR id (want ^ADR-\\d{4}$)")
                elif adr_files and adr not in adr_files:
                    fail("S-004", f"{dpath}: {rid}.governed_by '{adr}' has no file "
                                  "under docs/specs/decisions/")
            acs = r.get("acceptance_criteria") or []
            if not acs:
                fail("S-010", f"{dpath}: {rid} has no acceptance criteria")
                continue
            kinds = []
            for ac in acs:
                k = ears_kind(ac)
                if k is None:
                    fail("S-010", f"{dpath}: {rid} criterion is not valid EARS "
                                  f"(needs a 'shall' response): {str(ac)[:70]!r}")
                kinds.append(k)
            if str(rid).startswith("FR-") and "unwanted" not in kinds:
                fail("S-011", f"{dpath}: {rid} (functional) has no unwanted-behavior "
                              "criterion (IF ... THEN the system shall ...) -- the "
                              "failure/edge path")

    # ---- S-009: goals measurable ---------------------------------------
    for g in overview.get("goals") or []:
        if not isinstance(g, dict) or g.get("status") not in (None, "active"):
            continue
        if not str(g.get("metric") or "").strip() or \
                not str(g.get("measurement_method") or "").strip():
            fail("S-009", f"goal {g.get('id')} needs both a metric and a "
                          "measurement_method")

    # ---- S-013-ish: status enums (folded into S-001 integrity) ---------
    if str(o_meta.get("status") or "draft") not in DOC_STATUS_ENUM:
        fail("S-001", f"overview status '{o_meta.get('status')}' not in "
                      f"{DOC_STATUS_ENUM}")
    for g in overview.get("goals") or []:
        if isinstance(g, dict) and g.get("status") and g["status"] not in STATUS_ENUM:
            fail("S-001", f"goal {g.get('id')} status '{g['status']}' not in {STATUS_ENUM}")

    # ---- S-008: index sync ---------------------------------------------
    index = {}
    for row in overview.get("feature_index") or []:
        if not isinstance(row, dict):
            continue
        rslug = row.get("slug")
        if not rslug:
            fail("S-008", "a feature_index row is missing 'slug'")
            continue
        index[rslug] = row
        if row.get("status") and row["status"] not in STATUS_ENUM:
            fail("S-001", f"feature_index '{rslug}' status '{row['status']}' "
                          f"not in {STATUS_ENUM}")
    feat_slugs = {slug for slug, *_ in feats}
    for slug in feat_slugs:
        if slug not in index:
            fail("S-008", f"feature '{slug}' has no row in the overview feature_index")
    for rslug in index:
        if rslug not in feat_slugs:
            fail("S-008", f"feature_index lists '{rslug}' but features/{rslug}.md "
                          "(data file) does not exist")
    for slug, _md, dpath, doc in feats:
        row = index.get(slug)
        if not row:
            continue
        actual_v = str((doc.get("meta") or {}).get("feature_version") or "")
        recorded_v = str(row.get("feature_version") or "")
        if actual_v != recorded_v:
            fail("S-008", f"feature '{slug}': index feature_version "
                          f"'{recorded_v}' != actual '{actual_v}' (re-run make-spec)")
        if row.get("prefix") != (doc.get("meta") or {}).get("prefix"):
            fail("S-008", f"feature '{slug}': index prefix '{row.get('prefix')}' "
                          f"!= feature prefix '{(doc.get('meta') or {}).get('prefix')}'")

    # ---- S-005: no vanished ids vs baseline (FAIL CLOSED) --------------
    if not args.no_baseline:
        prior = baseline_ids(spec_dir, args.baseline_ref, fail)
        if prior is not None:
            for v in sorted(prior - known_ids):
                fail("S-005", f"ID '{v}' existed at {args.baseline_ref} and is now "
                              "missing (supersede or defer; never delete)")

    # ---- S-012: lean budget (WARNING) ----------------------------------
    for slug, md_path, _dpath, doc in feats:
        active = [r for r in (doc.get("requirements") or [])
                  if isinstance(r, dict) and r.get("status") in (None, "active")]
        if len(active) > args.budget_reqs:
            warn("S-012", f"feature '{slug}' has {len(active)} active requirements "
                          f"(> {args.budget_reqs}) -- consider splitting it")
        if os.path.isfile(md_path):
            try:
                with open(md_path) as f:
                    words = len(f.read().split())
                if words > args.budget_words:
                    warn("S-012", f"feature '{slug}' markdown is {words} words "
                                  f"(> {args.budget_words}) -- trim for reviewability")
            except OSError:
                pass

    # ---- report ---------------------------------------------------------
    for w in warns:
        print(f"  warn {w}")
    if errors:
        print(f"\nFAIL -- {len(errors)} violation(s) in {spec_dir}\n")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    print(f"PASS -- {spec_dir} (overview v{o_meta.get('project_version') or '?'}, "
          f"{len(feats)} feature(s), {len(known_ids)} IDs, "
          f"status {o_meta.get('status') or '?'})"
          + (f" -- {len(warns)} budget warning(s)" if warns else ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
