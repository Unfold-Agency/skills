#!/usr/bin/env python3
"""Preflight gate for do-work. Read-only: it CHECKS and REPORTS; it never
writes GitHub state or touches code. The skill reads the verdict and acts
(ensures labels, selects the next issue, or stops).

do-work is RFEF Lane 6 -- it builds the project from the GitHub issues that
make-issues (Lane 4) created. So its gate is the make-issues lock chain plus two
build-lane facts: there must actually be a backlog, and you must not build issues
make-issues has already flagged stale.

Checks, in order of dependency (a gating failure aborts before the next):
  1. auth          -- `gh auth status` succeeds
  2. gh_version    -- gh >= 2.94.0 (the same native-flag floor make-issues uses;
                      do-work opens PRs and reads issue dependencies)
  3. version_lock  -- prd-data.meta.prd_version == tdd-data.meta.prd_version
                      (pure YAML; if the TDD is stale the whole backlog is built
                      against a moved PRD -- re-lock via /make-tdd first)
  4. repo          -- inside a git work tree AND a resolvable owner/name remote
  5. backlog       -- make-issues-managed issues exist (else run /make-issues first)

Then non-gating ADVISORIES (reported, never abort):
  - drift          -- open managed issues carrying needs-rebase/spec-drift/
                      orphaned/escalated are NOT buildable; resolve them first
  - sync_owed      -- the live TDD version is not represented in the open issues'
                      meta-block source_versions.tdd; a /make-issues sync may be owed
  - labels         -- the do-work lifecycle labels (status:doing, escalated)
                      the skill creates if missing

  python scripts/work_preflight.py --prd docs/prd-data.yaml --tdd docs/tdd-data.yaml
  python scripts/work_preflight.py   # --prd/--tdd default to docs/{prd,tdd}-data.yaml
  python scripts/work_preflight.py --prd ... --tdd ... --repo owner/name --json

Exit codes: 0 = gate passes, 1 = a gating check failed, 2 = the data files can't
be read. Advisories never change the exit code.
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

MIN_GH = (2, 94, 0)
# Lifecycle labels do-work owns and creates if missing (mirrors the make-issues
# pattern of self-ensuring its label scheme). status:doing is the in-progress
# signal make-issues reconciliation already reads as a "started" marker.
MAKE_WORK_LABELS = ["status:doing", "escalated"]
# Labels that make a managed issue NOT buildable. The first three are set by
# make-issues reconciliation (a drifted spec); `escalated` is set by do-work
# when it hands an issue back upstream.
NOT_BUILDABLE_FLAGS = ["needs-rebase", "spec-drift", "orphaned", "escalated"]
# The make-issues meta block embedded in each managed issue body. Its
# source_versions.tdd is the authoritative version stamp do-work reads to decide
# whether a /make-issues sync is owed -- there is no src: label anymore.
_META_RE = re.compile(
    r"<!--\s*make-issues:meta\s*-->(.*?)<!--\s*/make-issues:meta\s*-->", re.DOTALL)


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


def _load_meta(path):
    """Load a data file's `meta` mapping. Returns (meta_dict, None) on success
    (an empty dict if the file has no `meta`), or (None, err) if it can't be read."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        return None, f"cannot read {path}: {e}"
    if not isinstance(doc, dict):
        return None, f"{path} is not a YAML mapping"
    meta = doc.get("meta")
    return (meta if isinstance(meta, dict) else {}), None


def _meta_field(path, field):
    """Read one meta field from a data file. Returns ('', None) when the key is
    absent, (None, err) when the file itself can't be read."""
    meta, err = _load_meta(path)
    if err:
        return None, err
    return str(meta.get(field) or ""), None


def check_auth():
    rc, _, _ = _run(["gh", "auth", "status"])
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
                      else f"gh {have} < {want}; run `brew upgrade gh`"}


def check_version_lock(prd_path, tdd_path):
    """Pure-YAML gate -- the same condition make-issues enforces. Importable and
    testable without gh/network."""
    live, err1 = _meta_field(prd_path, "prd_version")
    locked, err2 = _meta_field(tdd_path, "prd_version")
    if err1 or err2:
        return {"name": "version_lock", "ok": False, "fatal": True,
                "detail": f"{err1 or err2} -- both data files (canonically "
                          "docs/prd-data.yaml and docs/tdd-data.yaml) "
                          "must be present to verify the lock"}
    ok = bool(live) and bool(locked) and live == locked
    if ok:
        detail = f"PRD v{live} == TDD lock v{locked}"
    elif not live or not locked:
        detail = f"missing prd_version (PRD '{live}', TDD lock '{locked}')"
    else:
        detail = (f"TDD is locked to PRD v{locked} but the live PRD is v{live}; "
                  "the PRD moved on -- re-run /make-tdd to re-derive and re-lock, "
                  "then /make-issues to sync, before building")
    return {"name": "version_lock", "ok": ok, "live_prd": live,
            "locked_prd": locked, "detail": detail}


def check_repo(repo_override):
    rc, _, _ = _run(["git", "rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        return {"name": "repo", "ok": False, "repo": None,
                "detail": "not inside a git work tree; do-work builds the repo "
                          "the issues live in"}
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


def _list_managed_issues(repo):
    """All make-issues-managed issues with the fields the gate needs. Returns
    (issues, ok)."""
    rc, out, _ = _run(["gh", "issue", "list", "--repo", repo, "--label",
                       "make-issues", "--state", "all", "--limit", "1000",
                       "--json", "number,state,labels,body"])
    if rc != 0:
        return [], False
    try:
        return json.loads(out or "[]"), True
    except json.JSONDecodeError:
        return [], False


def _label_names(issue):
    return {lab.get("name", "") for lab in issue.get("labels") or []}


def _issue_meta(body):
    """Parse the YAML inside an issue body's make-issues:meta markers. Returns {}
    when the block is missing or malformed. The meta block is the authoritative
    record for trace + source_versions (see make-issues)."""
    m = _META_RE.search(body or "")
    if not m:
        return {}
    inner = re.sub(r"```[a-zA-Z]*", "", m.group(1)).replace("```", "")
    try:
        data = yaml.safe_load(inner)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _issue_tdd_version(issue):
    """The source_versions.tdd stamped in the issue's meta block, or '' if absent."""
    sv = _issue_meta(issue.get("body", "")).get("source_versions") or {}
    return str(sv.get("tdd") or "").strip() if isinstance(sv, dict) else ""


def check_backlog(issues, listed_ok):
    """Gating: there must be a backlog to work. Zero managed issues -> stop and
    send the user to /make-issues. Issues but none open -> pass, nothing to do."""
    if not listed_ok:
        return {"name": "backlog", "ok": False, "detail": "could not list issues"}
    total = len(issues)
    open_n = sum(1 for i in issues if i.get("state") == "OPEN")
    if total == 0:
        return {"name": "backlog", "ok": False, "total": 0, "open": 0,
                "detail": "no make-issues-managed issues; run /make-issues first"}
    if open_n == 0:
        return {"name": "backlog", "ok": True, "total": total, "open": 0,
                "detail": f"{total} managed issue(s), none open -- backlog drained"}
    return {"name": "backlog", "ok": True, "total": total, "open": open_n,
            "detail": f"{open_n} open of {total} managed issue(s)"}


def scan_advisories(issues, tdd_path, have_labels):
    """Non-gating advisories: drifted (not-buildable) open issues, a possibly-owed
    sync, and missing do-work labels."""
    flagged = []
    tdd_versions_seen = set()
    for i in issues:
        if i.get("state") != "OPEN":
            continue
        names = _label_names(i)
        hit = sorted(names & set(NOT_BUILDABLE_FLAGS))
        if hit:
            flagged.append({"number": i.get("number"), "flags": hit})
        tdd_v = _issue_tdd_version(i)
        if tdd_v:
            tdd_versions_seen.add(tdd_v)

    live_tdd, _ = _meta_field(tdd_path, "tdd_version")
    sync_owed = (bool(live_tdd) and bool(tdd_versions_seen)
                 and live_tdd not in tdd_versions_seen)
    missing_labels = [n for n in MAKE_WORK_LABELS if n not in (have_labels or set())]
    return {"flagged": flagged, "live_tdd": live_tdd or None,
            "tdd_versions_seen": sorted(tdd_versions_seen), "sync_owed": sync_owed,
            "missing_labels": missing_labels}


def _have_labels(repo):
    rc, out, _ = _run(["gh", "label", "list", "--repo", repo, "--limit", "500",
                       "--json", "name"])
    if rc != 0:
        return None
    try:
        return {lab["name"] for lab in json.loads(out or "[]")}
    except json.JSONDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prd", default="docs/prd-data.yaml", help="prd-data.yaml (default: docs/prd-data.yaml)")
    ap.add_argument("--tdd", default="docs/tdd-data.yaml", help="tdd-data.yaml (default: docs/tdd-data.yaml)")
    ap.add_argument("--repo", help="owner/name; skip gh repo auto-detect")
    ap.add_argument("--json", action="store_true", help="emit the verdict as JSON")
    args = ap.parse_args()

    checks = []
    auth = check_auth()
    checks.append(auth)
    checks.append(check_gh_version())
    lock = check_version_lock(args.prd, args.tdd)
    checks.append(lock)
    if lock.get("fatal"):                 # the data files themselves are unreadable
        _report(checks, None, None, args.json)
        sys.exit(2)

    advisories = None
    repo = None
    if auth["ok"]:                        # avoid hanging gh calls when unauthenticated
        repo_chk = check_repo(args.repo)
        checks.append(repo_chk)
        if repo_chk["ok"]:
            repo = repo_chk["repo"]
            issues, listed_ok = _list_managed_issues(repo)
            checks.append(check_backlog(issues, listed_ok))
            advisories = scan_advisories(issues, args.tdd, _have_labels(repo))

    ok = all(c["ok"] for c in checks)
    _report(checks, repo, advisories, args.json)
    sys.exit(0 if ok else 1)


def _report(checks, repo, advisories, as_json):
    if as_json:
        verdict = {"ok": all(c["ok"] for c in checks), "repo": repo,
                   "advisories": advisories, "checks": checks}
        print(json.dumps(verdict, indent=2))
        return
    for c in checks:
        mark = "ok  " if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['name']}: {c['detail']}")
    if advisories:
        flagged = advisories["flagged"]
        if flagged:
            ids = ", ".join(f"#{f['number']} ({'/'.join(f['flags'])})" for f in flagged)
            print(f"  warn   not buildable (resolve first): {ids}")
        if advisories["sync_owed"]:
            print(f"  warn   sync may be owed: live TDD v{advisories['live_tdd']} "
                  f"not in issue stamps {advisories['tdd_versions_seen']}; run /make-issues")
        if advisories["missing_labels"]:
            print("  note   missing do-work labels (skill must create): "
                  + ", ".join(advisories["missing_labels"]))
    print()
    print("PASS -- preflight gate clear" if all(c["ok"] for c in checks)
          else "FAIL -- do not proceed; resolve the failed check(s) above")


if __name__ == "__main__":
    main()
