#!/usr/bin/env python3
"""
validate_arch.py -- enforce validator rules A-001..A-009 across docs/product/

Validates the architecture layer in its SINGLE-FILE form: architecture.md
(frontmatter = the machine contract: meta, context, components, integrations,
diagrams) plus decisions/ADR-NNNN-*.md (each ADR's frontmatter = its machine
record), and cross-checks the ADRs against the make-spec feature files
(no-orphan). There is no derived arch-data.yaml -- the bytes a human signs are
the bytes validated here. Reuses the make-spec discipline: a fail-closed
fingerprint gate on architecture.md (A-007) and an origin/main baseline that
enforces the ADR log's append-only regime (A-008) and per-file immutability
once accepted (A-009).

Usage:
  python validate_arch.py [docs/product] [--baseline-ref origin/main | --no-baseline]

Exit codes: 0 = pass (warnings do not fail), 1 = violations, 2 = file/parse
error (including a legacy arch-data.yaml layout awaiting migration).
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

ADR_ID_RE = re.compile(r"^ADR-\d{4}$")
ADR_STATUS = ("proposed", "accepted", "superseded", "deprecated")
DOC_STATUS = ("draft", "review", "approved")
CONFIDENCE = ("known", "assumption")
DIAGRAM_KINDS = ("context", "container", "sequence", "erd")
ADR_REQUIRED_KEYS = ("id", "title", "status", "scope", "confidence")
# The one allowed edit to an accepted ADR: the supersede transition (A-009).
ADR_TRANSITION_KEYS = {"status", "superseded_by"}

# Fingerprint IN/OUT contract (A-007) -- advisory/derived keys dropped before
# hashing architecture.md's frontmatter. ADR files carry no fingerprint: their
# regime is append-only, enforced against the git baseline (A-008/A-009).
OUT_KEYS = {"fingerprint", "generated_at", "arch_version", "last_updated", "notes"}


def _strip_out(obj):
    if isinstance(obj, dict):
        return {k: _strip_out(v) for k, v in obj.items() if k not in OUT_KEYS}
    if isinstance(obj, list):
        return [_strip_out(x) for x in obj]
    return obj


def compute_fingerprint(doc):
    stripped = _strip_out(copy.deepcopy(doc))
    normalized = yaml.safe_dump(stripped, sort_keys=True, default_flow_style=False,
                                allow_unicode=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ── single-file loading: frontmatter is the signed contract ───────────
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def split_frontmatter(text):
    """(frontmatter_text, body) for a leading --- ... --- block, else (None, text).
    A leading UTF-8 BOM is tolerated."""
    if text.startswith("﻿"):
        text = text[1:]
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def parse_md(text):
    """(doc, body) from a single-file document. doc is {} when there is no
    frontmatter or it is not a mapping -- malformed files fail closed through
    the integrity rules rather than crashing."""
    fm, body = split_frontmatter(text)
    if fm is None:
        return {}, body
    doc = yaml.safe_load(fm)
    return (doc if isinstance(doc, dict) else {}), body


def load_md(path):
    with open(path, encoding="utf-8") as f:
        return parse_md(f.read())


def adr_files(spec_dir):
    """[(adr_id_from_filename, filename)] for decisions/ADR-*.md, sorted."""
    dec_dir = os.path.join(spec_dir, "decisions")
    out = []
    if not os.path.isdir(dec_dir):
        return out
    for name in sorted(os.listdir(dec_dir)):
        mo = re.match(r"^(ADR-\d{4})", name)
        if mo and name.endswith(".md"):
            out.append((mo.group(1), name))
    return out


def feature_governed_by(spec_dir):
    """Union of every ADR id referenced by a feature requirement's governed_by,
    across docs/product/features/*.md (read from the frontmatter)."""
    refs = set()
    fdir = os.path.join(spec_dir, "features")
    if not os.path.isdir(fdir):
        return refs
    for name in os.listdir(fdir):
        if not name.endswith(".md"):
            continue
        try:
            doc, _ = load_md(os.path.join(fdir, name))
        except yaml.YAMLError:
            continue
        for r in doc.get("requirements") or []:
            if isinstance(r, dict):
                for adr in r.get("governed_by") or []:
                    refs.add(str(adr))
    return refs


# ── git baseline (A-008 append-only, A-009 immutable-once-accepted) ──
def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def baseline_adrs(spec_dir, ref, fail):
    """{adr_id: (filename, text)} for every decisions/ADR-*.md at the baseline
    ref, or None when the baseline cannot be trusted (the caller has already
    recorded the fail-closed A-008 violation). An empty dict = greenfield."""
    cwd = os.path.abspath(spec_dir)
    inside = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        fail("A-008", "not a git repository -- cannot establish an append-only "
                      "baseline (use --no-baseline only for the greenfield kickoff)")
        return None
    shallow = _git(["rev-parse", "--is-shallow-repository"], cwd)
    if shallow.returncode != 0 or shallow.stdout.strip() == "true":
        fail("A-008", "shallow or unverifiable repository -- run 'git fetch "
                      "--unshallow' (refusing to pass on partial history)")
        return None
    if _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd).returncode != 0:
        fail("A-008", f"cannot resolve baseline ref '{ref}' -- fetch it or pass "
                      "--no-baseline for the greenfield kickoff")
        return None
    # List the decisions dir at the baseline. An empty listing means the log did
    # not exist there (greenfield) -- nothing prior, nothing to lose; a nonzero
    # rc means the tree itself is unusable (fail closed).
    listing = _git(["ls-tree", "-r", "--name-only", ref, "--", "decisions"], cwd)
    if listing.returncode != 0:
        fail("A-008", f"cannot list the baseline tree at '{ref}' (git ls-tree "
                      f"failed: {listing.stderr.strip()}) -- baseline unusable, "
                      "refusing to pass")
        return None
    out = {}
    for path in listing.stdout.splitlines():
        name = os.path.basename(path)
        mo = re.match(r"^(ADR-\d{4})", name)
        if not (mo and name.endswith(".md")):
            continue
        show = _git(["show", f"{ref}:./{path}"], cwd)
        if show.returncode != 0:
            fail("A-008", f"cannot read '{path}' at '{ref}' (git show failed: "
                          f"{show.stderr.strip()}) -- baseline incomplete, "
                          "refusing to pass")
            return None
        out[mo.group(1)] = (name, show.stdout)
    return out


def _transition_view(doc):
    """The ADR frontmatter with the allowed supersede-transition fields removed
    -- what must stay byte-stable once a decision is accepted (A-009)."""
    return {k: v for k, v in (doc or {}).items() if k not in ADR_TRANSITION_KEYS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_dir", nargs="?", default="docs/product")
    ap.add_argument("--baseline-ref", default="origin/main")
    ap.add_argument("--no-baseline", action="store_true")
    args = ap.parse_args()

    spec_dir = args.spec_dir
    arch_md_path = os.path.join(spec_dir, "architecture.md")
    legacy_yaml = os.path.join(spec_dir, "arch-data.yaml")

    if not os.path.isfile(arch_md_path):
        hint = (" -- legacy arch-data.yaml found: run "
                "scripts/migrate_arch_data.py to adopt the single-file layout"
                if os.path.isfile(legacy_yaml) else "")
        print(f"ERROR: no architecture.md under {spec_dir}{hint}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(arch_md_path, encoding="utf-8") as f:
            arch_text = f.read()
        arch, arch_body = parse_md(arch_text)
    except Exception as e:
        print(f"ERROR: cannot parse {arch_md_path}: {e}", file=sys.stderr)
        sys.exit(2)

    meta = arch.get("meta") if isinstance(arch.get("meta"), dict) else {}
    if str(meta.get("doc_type") or "") != "spec-arch":
        hint = (" -- legacy arch-data.yaml layout detected: run "
                "scripts/migrate_arch_data.py to move the contract into "
                "architecture.md's frontmatter"
                if os.path.isfile(legacy_yaml) else
                " -- architecture.md needs the schema v2.0 frontmatter "
                "(see assets/arch-schema.yaml)")
        print(f"ERROR: {arch_md_path} has no spec-arch frontmatter{hint}",
              file=sys.stderr)
        sys.exit(2)

    errors, warns = [], []
    fail = lambda rule, msg: errors.append(f"[{rule}] {msg}")
    warn = lambda rule, msg: warns.append(f"[{rule}] {msg}")

    if os.path.isfile(legacy_yaml):
        warn("A-001", f"{legacy_yaml} still exists alongside the v2.0 frontmatter "
                      "-- it is no longer read; delete it (migrate_arch_data.py "
                      "does) so it cannot drift")

    # ---- A-001: well-formed ---------------------------------------------
    for key in ("status", "fingerprint"):
        if key not in meta:
            fail("A-001", f"architecture.md meta missing '{key}'")
    for key in ("components", "integrations", "diagrams"):
        if key not in arch:
            fail("A-001", f"architecture.md frontmatter missing top-level '{key}'")
    if str(meta.get("status") or "draft") not in DOC_STATUS:
        fail("A-001", f"status '{meta.get('status')}' not in {DOC_STATUS}")

    # ---- load the ADR log (each file's frontmatter is its record) -------
    adr_ids = {}       # id -> frontmatter doc
    adr_bodies = {}    # id -> body text
    adr_names = {}     # id -> filename
    for fid, name in adr_files(spec_dir):
        path = os.path.join(spec_dir, "decisions", name)
        try:
            doc, body = load_md(path)
        except Exception as e:
            fail("A-001", f"decisions/{name}: cannot parse ({e})")
            continue
        if not doc:
            fail("A-001", f"decisions/{name}: no ADR frontmatter (see "
                          "assets/adr-template.md; migrate_arch_data.py injects "
                          "it from a legacy arch-data.yaml)")
            continue
        for key in ADR_REQUIRED_KEYS:
            if key not in doc:
                fail("A-001", f"decisions/{name}: frontmatter missing '{key}'")
        did = str(doc.get("id") or "")
        # ---- A-002: id format, filename agreement, uniqueness ----------
        if not ADR_ID_RE.match(did):
            fail("A-002", f"decisions/{name}: malformed id '{did}' "
                          "(want ^ADR-\\d{4}$)")
            continue
        if did != fid:
            fail("A-002", f"decisions/{name}: frontmatter id '{did}' != filename "
                          f"id '{fid}'")
        if did in adr_ids:
            fail("A-002", f"duplicate ADR id '{did}' (decisions/{name} and "
                          f"decisions/{adr_names[did]})")
            continue
        adr_ids[did] = doc
        adr_bodies[did] = body
        adr_names[did] = name

    # ---- A-003: supersede discipline -------------------------------------
    for did, d in adr_ids.items():
        st = str(d.get("status") or "")
        if st and st not in ADR_STATUS:
            fail("A-003", f"{did} status '{st}' not in {ADR_STATUS}")
        if st in ("superseded", "deprecated"):
            sb = str(d.get("superseded_by") or "")
            if not sb:
                fail("A-003", f"{did} is {st} but has no superseded_by")
            elif sb == did:
                fail("A-003", f"{did} cannot supersede itself")
            elif sb not in adr_ids:
                fail("A-003", f"{did}.superseded_by '{sb}' is not a known ADR")
            elif str(adr_ids[sb].get("status") or "") == "proposed":
                fail("A-003", f"{did}.superseded_by '{sb}' is still 'proposed' -- "
                              "supersede only by an accepted (or already-superseded) "
                              "decision")
    # Supersession cycles of any length (1-cycles are caught above): walk each
    # superseded/deprecated ADR's superseded_by chain; revisiting a node = a cycle
    # with no live head, which silently breaks the <=2-hops-to-current guarantee.
    for did, d in adr_ids.items():
        if str(d.get("status") or "") not in ("superseded", "deprecated"):
            continue
        seen, cur = set(), did
        while cur in adr_ids:
            if cur in seen:
                fail("A-003", f"supersession cycle through {did} "
                              f"(the superseded_by chain revisits {cur})")
                break
            seen.add(cur)
            nxt = str(adr_ids[cur].get("superseded_by") or "")
            if not nxt:
                break
            cur = nxt

    # ---- A-005: typed confidence -----------------------------------------
    for coll in ("components", "integrations"):
        for item in arch.get(coll) or []:
            if not isinstance(item, dict):
                continue
            c = item.get("confidence")
            if c not in CONFIDENCE:
                who = item.get("id") or item.get("name") or f"a {coll[:-1]}"
                fail("A-005", f"{who} confidence '{c}' not in {CONFIDENCE}")
    for did, d in adr_ids.items():
        if d.get("confidence") not in CONFIDENCE:
            fail("A-005", f"{did} confidence '{d.get('confidence')}' not in "
                          f"{CONFIDENCE}")

    # ---- A-004: no-orphan (cross-check vs features) -----------------------
    feat_refs = feature_governed_by(spec_dir)
    for did, d in adr_ids.items():
        if str(d.get("status")) != "accepted":
            continue
        if did not in feat_refs:
            if str(d.get("scope")) == "project":
                warn("A-004", f"{did} (project-scoped) is accepted but not "
                              "referenced by any feature")
            else:
                fail("A-004", f"{did} (feature-scoped) is accepted but no feature "
                              "requirement's governed_by references it (orphan)")
    for ref in feat_refs:
        if ref not in adr_ids:
            fail("A-004", f"a feature references governed_by '{ref}' but there is "
                          f"no decisions/{ref}-*.md")
        elif str(adr_ids[ref].get("status") or "") == "superseded":
            sb = str(adr_ids[ref].get("superseded_by") or "?")
            fail("A-004", f"a feature is governed_by '{ref}' which is superseded -- "
                          f"repoint governed_by at {sb}")

    # ---- A-006: mermaid diagrams present in the body ----------------------
    low = arch_body.lower()
    if "```mermaid" not in low:
        fail("A-006", "architecture.md body has no ```mermaid block")
    # Match each listed kind against the BODIES of the mermaid fences only,
    # not the surrounding prose -- else a '## System context' heading would
    # satisfy the 'context' kind with no real diagram present.
    blocks = "\n".join(re.findall(r"```mermaid(.*?)```", low, re.DOTALL))
    kinds = [k for k in (arch.get("diagrams") or []) if k in DIAGRAM_KINDS]
    if "context" not in kinds:
        fail("A-006", "diagrams must include the 'context' diagram")
    SIGNATURE = {"context": "c4context", "container": "c4container",
                 "erd": "erdiagram", "sequence": "sequencediagram"}
    for kind in kinds:
        if SIGNATURE[kind] not in blocks:
            fail("A-006", f"diagrams lists '{kind}' but architecture.md has no "
                          f"matching mermaid {SIGNATURE[kind]} block")

    # ---- A-007: fingerprint integrity (FAIL CLOSED) -----------------------
    stored = str(meta.get("fingerprint") or "")
    if not stored:
        fail("A-007", "architecture.md meta.fingerprint is blank")
    elif stored != compute_fingerprint(arch):
        fail("A-007", "architecture.md fingerprint mismatch -- the frontmatter "
                      "changed since it was stamped (re-run "
                      "scripts/stamp_fingerprint.py)")

    # ---- A-008 / A-009: the baseline gates (FAIL CLOSED) ------------------
    if not args.no_baseline:
        prior = baseline_adrs(spec_dir, args.baseline_ref, fail)
        if prior is not None:
            # A-008 -- append-only: nothing at the baseline may vanish.
            for v in sorted(set(prior) - set(adr_ids)):
                fail("A-008", f"ADR '{v}' existed at {args.baseline_ref} and is now "
                              "missing -- ADRs are append-only (supersede, never delete)")
            # A-009 -- immutable once accepted: an ADR accepted at the baseline
            # may differ ONLY in the supersede transition (status ->
            # superseded/deprecated + superseded_by). A baseline file with no
            # frontmatter is the pre-v2.0 era: exempt, so the one-time migration
            # (which injects frontmatter) can land.
            for did, (name, base_text) in sorted(prior.items()):
                if did not in adr_ids:
                    continue  # already an A-008 failure
                try:
                    base_doc, base_body = parse_md(base_text)
                except yaml.YAMLError:
                    continue
                if not base_doc or str(base_doc.get("status") or "") != "accepted":
                    continue
                cur_doc, cur_body = adr_ids[did], adr_bodies[did]
                cur_status = str(cur_doc.get("status") or "")
                if cur_status == "proposed":
                    fail("A-009", f"{did} was accepted at {args.baseline_ref} and "
                                  "cannot return to 'proposed'")
                fm_changed = (
                    yaml.safe_dump(_transition_view(cur_doc), sort_keys=True)
                    != yaml.safe_dump(_transition_view(base_doc), sort_keys=True))
                body_changed = (cur_body or "").strip() != (base_body or "").strip()
                if fm_changed or body_changed:
                    what = " and ".join(w for w, c in
                                        (("frontmatter", fm_changed),
                                         ("prose", body_changed)) if c)
                    fail("A-009", f"{did} was accepted at {args.baseline_ref} but "
                                  f"its {what} changed -- an accepted ADR is "
                                  "immutable except the supersede transition "
                                  "(status + superseded_by); write a superseding "
                                  "ADR instead of editing")

    # ---- report ------------------------------------------------------------
    for w in warns:
        print(f"  warn {w}")
    if errors:
        print(f"\nFAIL -- {len(errors)} violation(s) in {spec_dir}\n")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    n_assume = sum(1 for it in (arch.get("components") or [])
                   + (arch.get("integrations") or [])
                   + list(adr_ids.values())
                   if isinstance(it, dict) and it.get("confidence") == "assumption")
    print(f"PASS -- {spec_dir} arch (status {meta.get('status') or '?'}, "
          f"{len(adr_ids)} ADR(s), {n_assume} assumption-backed choice(s))"
          + (f" -- {len(warns)} warning(s)" if warns else ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
