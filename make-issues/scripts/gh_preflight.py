#!/usr/bin/env python3
"""Preflight gate for make-issues. Read-only: it CHECKS and REPORTS; it never
writes GitHub state. The skill reads the verdict and acts (creates labels,
picks the mode, or stops).

Checks, in order of dependency:
  1. auth          -- `gh auth status` succeeds
  2. gh_version    -- gh >= 2.94.0 (native dependency/type flags; below that the
                      blocked-by/blocking/type/parent features do not exist)
  3. spec_integrity -- the FAIL-CLOSED fingerprint gate. Every spec's stored
                      meta.fingerprint must equal a recompute over its CONTRACT
                      content (overview.md, every features/*.md -- read from the
                      frontmatter -- and arch-data.yaml if present). A single
                      mismatch means the specs are mid-edit -- issues built now
                      would be wrong -- so the gate FAILS and the skill must not
                      proceed. Pure parsing; importable and testable without
                      gh/network.
  4. repo          -- inside a git work tree AND a resolvable owner/name remote
  5. mode + labels -- existing make-issues-labelled issues -> generate|sync, and
                      which static labels are missing (the skill creates them)

  python scripts/gh_preflight.py --spec-dir docs/specs
  python scripts/gh_preflight.py                         # --spec-dir defaults to docs/specs
  python scripts/gh_preflight.py --spec-dir ... --repo owner/name --json

Exit codes: 0 = gate passes, 1 = a check failed, 2 = the spec files can't be read.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(2)

MIN_GH = (2, 94, 0)
# Static labels make-issues always relies on (mirrors assets/labels.yaml).
# This is the whole scheme -- no per-run dynamic labels. Traceability and source
# versions live in the issue body (the ## Traceability table and the meta block),
# so there are no trace: or src: labels.
STATIC_LABELS = ["make-issues", "afk", "hitl", "needs-rebase", "spec-drift",
                 "orphaned", "refactor", "refactor-tracking"]

# ── The C1 fingerprint discipline, applied at the FILE level ─────────────────
# A spec file's stored meta.fingerprint is computed over its CONTRACT content.
# This gate RE-COMPUTES it and must produce a hash BYTE-IDENTICAL to the upstream
# validator that stamped the file, or it would reject legitimately-stamped specs:
#   - overview.md / features/*.md (frontmatter) -> make-spec/scripts/validate_spec.py
#   - arch-data.yaml                            -> make-arch/scripts/validate_arch.py
# To stay identical we copy their exact discipline: drop the OUT keys FLAT
# (wherever they appear -- they live in `meta` AND, for the overview, in
# feature_index rows), do NO text normalization (the upstream dumps strings
# verbatim), then yaml.safe_dump(sort_keys=True, default_flow_style=False,
# allow_unicode=True) -> sha256. The two skills use DIFFERENT OUT sets, so the
# gate picks the set per file. The golden cross-fixtures in
# scripts/tests/specs/upstream/ (stamped by the real upstream skills) lock this
# interop; if these sets ever drift from the validators, that test fails.
#
# OUT keys never affect the fingerprint; everything else is IN. At the FILE level
# requirement `status` is IN (make-spec hashes it); the PER-ITEM hash in
# item_fingerprint.py separately excludes status -- a narrower scope for the
# reconcile decision tree. Keep these two scopes distinct.
SPEC_OUT_KEYS = {"priority", "architecture_hints", "related_files", "notes",
                 "fingerprint", "feature_version", "generated_at",
                 "project_version", "appetite"}      # == make-spec OUT_KEYS
ARCH_OUT_KEYS = {"fingerprint", "generated_at", "arch_version", "notes"}  # == make-arch OUT_KEYS

# Spec docs are single .md files; their contract lives in YAML frontmatter. The
# arch file (arch-data.yaml) is a plain YAML file -- dispatch on the extension.
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def _run(cmd, timeout=30):
    """Run a command, returning (returncode, stdout, stderr). Never raises on a
    nonzero exit; returns (124, '', 'timeout') if it hangs."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"


def _strip_out(value, out_keys):
    """Drop every OUT key wherever it appears -- FLAT, exactly like the upstream
    validators (make-spec/make-arch). No text normalization: the upstream dumps
    strings verbatim, so we must too, or the recompute would diverge. Returns an
    OUT-free copy; the original is untouched."""
    if isinstance(value, dict):
        return {k: _strip_out(v, out_keys) for k, v in value.items()
                if k not in out_keys}
    if isinstance(value, list):
        return [_strip_out(v, out_keys) for v in value]
    return value


def compute_fingerprint(doc, out_keys=SPEC_OUT_KEYS):
    """Recompute a spec file's fingerprint EXACTLY as the upstream validator that
    stamped it does. Pass SPEC_OUT_KEYS for an overview/feature file, ARCH_OUT_KEYS
    for arch-data.yaml -- they differ only in the OUT set. Byte-for-byte identical
    to make-spec/make-arch's compute_fingerprint (verified by the golden
    cross-fixtures), so the gate accepts any spec the upstream skills stamped."""
    stripped = _strip_out(doc, out_keys)
    normalized = yaml.safe_dump(stripped, sort_keys=True,
                                default_flow_style=False, allow_unicode=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _load_doc(path):
    """Load a spec doc as a mapping. A .md spec carries its contract in YAML
    frontmatter; a .yaml file (arch-data.yaml) is loaded directly -- dispatch on
    extension. Returns (doc, None) or (None, err)."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return None, f"cannot read {path}: {e}"
    try:
        if path.endswith(".md"):
            m = FRONTMATTER_RE.match(text)
            doc = yaml.safe_load(m.group(1)) if m else None
        else:
            doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return None, f"cannot read {path}: {e}"
    if not isinstance(doc, dict):
        return None, f"{path} has no spec content"
    return doc, None


def spec_files(spec_dir):
    """The spec docs to integrity-check: overview, every feature, and arch if
    present. Returns a list of (label, path). overview is required; arch is
    optional. Specs are single .md files (contract in frontmatter); arch-data.yaml
    is plain YAML."""
    files = []
    overview = os.path.join(spec_dir, "overview.md")
    files.append(("overview", overview))
    for fpath in sorted(glob.glob(os.path.join(spec_dir, "features", "*.md"))):
        files.append((f"feature:{os.path.basename(fpath)}", fpath))
    arch = os.path.join(spec_dir, "arch-data.yaml")
    if os.path.isfile(arch):
        files.append(("arch", arch))
    return files


def check_spec_integrity(spec_dir):
    """FAIL-CLOSED fingerprint gate. For every spec data file, the stored
    meta.fingerprint must equal compute_fingerprint(doc). A missing stored
    fingerprint, an unreadable/missing required file, or any mismatch FAILS the
    gate (and a read error is fatal -> exit 2). Pure YAML; no gh/network.

    Returns a verdict dict with `ok`, optional `fatal`, per-file `files`, and a
    `detail` summary.
    """
    files = spec_files(spec_dir)
    results = []
    fatal = False
    overview_path = os.path.join(spec_dir, "overview.md")
    if not os.path.isfile(overview_path):
        return {"name": "spec_integrity", "ok": False, "fatal": True,
                "files": [], "detail":
                f"no overview.md under {spec_dir} -- specs must be in "
                "docs/specs/ (overview.md, features/*.md, "
                "arch-data.yaml)"}
    feature_count = 0
    for label, path in files:
        if label.startswith("feature:"):
            feature_count += 1
        doc, err = _load_doc(path)
        if err:
            fatal = True
            results.append({"file": label, "ok": False, "detail": err})
            continue
        meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
        stored = str(meta.get("fingerprint") or "")
        out_keys = ARCH_OUT_KEYS if label == "arch" else SPEC_OUT_KEYS
        recomputed = compute_fingerprint(doc, out_keys)
        if not stored:
            results.append({"file": label, "ok": False,
                            "detail": "no stored meta.fingerprint to verify"})
        elif stored == recomputed:
            results.append({"file": label, "ok": True,
                            "detail": "fingerprint matches recompute"})
        else:
            results.append({"file": label, "ok": False,
                            "detail": f"stored {stored[:12]} != recompute "
                                      f"{recomputed[:12]} -- spec edited without "
                                      "re-stamping (mid-edit)"})
    if feature_count == 0:
        results.append({"file": "features/", "ok": False,
                        "detail": "no features/*.md found -- nothing to "
                                  "turn into issues"})
    ok = all(r["ok"] for r in results) and not fatal
    if ok:
        detail = f"all {len(results)} spec file(s) fingerprint-clean"
    else:
        bad = [r["file"] for r in results if not r["ok"]]
        detail = ("spec integrity FAILED for: " + ", ".join(bad) +
                  " -- the specs are mid-edit; re-run /make-spec (or /make-arch) "
                  "to re-stamp before building issues")
    verdict = {"name": "spec_integrity", "ok": ok, "files": results,
               "detail": detail}
    if fatal:
        verdict["fatal"] = True
    return verdict


def check_auth():
    rc, _, err = _run(["gh", "auth", "status"])
    return {"name": "auth", "ok": rc == 0,
            "detail": "authenticated" if rc == 0 else "run `gh auth login`"}


def check_gh_version():
    rc, out, _ = _run(["gh", "--version"])
    m = re.search(r"gh version (\d+)\.(\d+)\.(\d+)", out or "")
    if rc != 0 or not m:
        return {"name": "gh_version", "ok": False, "version": None,
                "detail": "could not determine gh version"}
    ver = tuple(int(x) for x in m.groups())
    ok = ver >= MIN_GH
    want = ".".join(map(str, MIN_GH))
    have = ".".join(map(str, ver))
    return {"name": "gh_version", "ok": ok, "version": list(ver),
            "detail": f"gh {have}" if ok
                      else f"gh {have} < {want}; run `brew upgrade gh` "
                           "(native dependency flags need >= " + want + ")"}


def check_approval(spec_dir):
    """Advisory (non-gating): warn when the project is not yet `approved`.
    The fingerprint gate can pass while the overview is still draft; issues built
    on a draft churn when it lands. This mirrors make-spec's warn-don't-block
    posture -- it never fails the gate; the skill surfaces it and asks the user
    to confirm. Reads overview.md meta.status (and notes any feature whose
    status is not active)."""
    overview, _ = _load_doc(os.path.join(spec_dir, "overview.md"))
    status = str(((overview or {}).get("meta") or {}).get("status") or "unknown")
    approved = status == "approved"
    if approved:
        detail = "overview is approved"
    else:
        detail = (f"overview status '{status}' -- not approved; issues created "
                  "now will churn when the specs are. Confirm with the user "
                  "before creating.")
    return {"status": status, "approved": approved, "detail": detail}


def check_repo(repo_override):
    rc, _, _ = _run(["git", "rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        return {"name": "repo", "ok": False, "repo": None,
                "detail": "not inside a git work tree; make-issues writes GitHub "
                          "state for the repo the build lives in"}
    if repo_override:
        return {"name": "repo", "ok": True, "repo": repo_override,
                "detail": f"target {repo_override} (from --repo)"}
    rc, out, _ = _run(["gh", "repo", "view", "--json", "nameWithOwner",
                       "-q", ".nameWithOwner"])
    name = out.strip()
    if rc != 0 or not name:
        return {"name": "repo", "ok": False, "repo": None,
                "detail": "could not resolve owner/name; pass --repo owner/name"}
    return {"name": "repo", "ok": True, "repo": name,
            "detail": f"target {name} -- confirm before any write"}


def detect_mode_and_labels(repo):
    rc, out, _ = _run(["gh", "issue", "list", "--repo", repo, "--label",
                       "make-issues", "--state", "all", "--limit", "1000",
                       "--json", "number"])
    mode, count = None, None
    if rc == 0:
        try:
            count = len(json.loads(out or "[]"))
            mode = "sync" if count else "generate"
        except json.JSONDecodeError:
            pass
    rc2, out2, _ = _run(["gh", "label", "list", "--repo", repo, "--limit", "500",
                         "--json", "name"])
    missing = list(STATIC_LABELS)
    if rc2 == 0:
        try:
            have = {lab["name"] for lab in json.loads(out2 or "[]")}
            missing = [n for n in STATIC_LABELS if n not in have]
        except json.JSONDecodeError:
            pass
    return ({"name": "mode", "ok": mode is not None, "mode": mode,
             "managed_issue_count": count,
             "detail": f"{mode} ({count} managed issue(s))" if mode is not None
                       else "could not list issues"},
            missing)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec-dir", default="docs/specs",
                    help="the layered spec dir (default: docs/specs)")
    ap.add_argument("--repo", help="owner/name; skip gh repo auto-detect")
    ap.add_argument("--json", action="store_true", help="emit the verdict as JSON")
    args = ap.parse_args()

    checks = []
    auth = check_auth()
    checks.append(auth)
    checks.append(check_gh_version())
    integrity = check_spec_integrity(args.spec_dir)
    checks.append(integrity)
    if integrity.get("fatal"):            # the spec files themselves are unreadable
        _report(checks, None, [], None, args.json)
        sys.exit(2)

    approval = check_approval(args.spec_dir)        # advisory; never gates
    repo, missing = None, []
    if auth["ok"]:                        # avoid hanging gh calls when unauthenticated
        repo_chk = check_repo(args.repo)
        checks.append(repo_chk)
        if repo_chk["ok"]:
            repo = repo_chk["repo"]
            mode_chk, missing = detect_mode_and_labels(repo)
            checks.append(mode_chk)

    ok = all(c["ok"] for c in checks)
    _report(checks, repo, missing, approval, args.json)
    sys.exit(0 if ok else 1)


def _report(checks, repo, missing, approval, as_json):
    if as_json:
        verdict = {"ok": all(c["ok"] for c in checks), "repo": repo,
                   "missing_labels": missing, "approval": approval,
                   "checks": checks}
        print(json.dumps(verdict, indent=2))
        return
    for c in checks:
        mark = "ok  " if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['name']}: {c['detail']}")
        if c["name"] == "spec_integrity" and not c["ok"]:
            for fr in c.get("files", []):
                if not fr["ok"]:
                    print(f"           - {fr['file']}: {fr['detail']}")
    if missing:
        print(f"  note   missing static labels (skill must create): {', '.join(missing)}")
    if approval and not approval["approved"]:
        print(f"  warn   approval: {approval['detail']}")
    elif approval:
        print(f"  ok     approval: {approval['detail']}")
    print()
    print("PASS -- preflight gate clear" if all(c["ok"] for c in checks)
          else "FAIL -- do not proceed; resolve the failed check(s) above")


if __name__ == "__main__":
    main()
