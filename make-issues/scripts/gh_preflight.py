#!/usr/bin/env python3
"""Preflight gate for make-issues. Read-only: it CHECKS and REPORTS; it never
writes GitHub state. The skill reads the verdict and acts (creates labels,
picks the mode, or stops).

Checks, in order of dependency:
  1. auth          -- `gh auth status` succeeds
  2. gh_version    -- gh >= 2.94.0 (native dependency/type flags; below that the
                      blocked-by/blocking/type/parent features do not exist)
  3. version_lock  -- prd-data.meta.prd_version == tdd-data.meta.prd_version
                      (pure YAML; the gate that makes issues trustworthy -- a
                      stale TDD must be re-locked via /make-tdd first)
  4. repo          -- inside a git work tree AND a resolvable owner/name remote
  5. mode + labels -- existing make-issues-labelled issues -> generate|sync, and
                      which static labels are missing (the skill creates them)

  python scripts/gh_preflight.py --prd prd-data.yaml --tdd tdd-data.yaml
  python scripts/gh_preflight.py --prd ... --tdd ... --repo owner/name --json

Exit codes: 0 = gate passes, 1 = a check failed, 2 = the data files can't be read.
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
# Static labels make-issues always relies on (mirrors assets/labels.yaml).
# The dynamic trace:/src: labels are minted per run by the skill, not here.
STATIC_LABELS = ["make-issues", "afk", "hitl", "needs-rebase", "spec-drift", "orphaned"]


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


def _meta_version(path):
    """Read meta.prd_version from a data file. Returns ('', None) when the key is
    absent, (None, err) when the file itself can't be read."""
    meta, err = _load_meta(path)
    if err:
        return None, err
    return str(meta.get("prd_version") or ""), None


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


def check_version_lock(prd_path, tdd_path):
    """Pure-YAML gate. Importable and testable without gh/network."""
    live, err1 = _meta_version(prd_path)
    locked, err2 = _meta_version(tdd_path)
    if err1 or err2:
        return {"name": "version_lock", "ok": False, "fatal": True,
                "detail": f"{err1 or err2} -- both prd-data.yaml and tdd-data.yaml "
                          "must be in the working tree to verify the lock"}
    ok = bool(live) and bool(locked) and live == locked
    if ok:
        detail = f"PRD v{live} == TDD lock v{locked}"
    elif not live or not locked:
        detail = f"missing prd_version (PRD '{live}', TDD lock '{locked}')"
    else:
        detail = (f"TDD is locked to PRD v{locked} but the live PRD is v{live}; "
                  "the PRD moved on -- re-run /make-tdd to re-derive and re-lock")
    return {"name": "version_lock", "ok": ok, "live_prd": live,
            "locked_prd": locked, "detail": detail}


def check_approval(prd_path, tdd_path):
    """Advisory (non-gating): warn when the PRD or TDD is not yet `approved`.
    The version lock can pass while both docs are still drafts; issues built on a
    draft churn when it lands. This mirrors make-tdd's warn-don't-block posture --
    it never fails the gate; the skill surfaces it and asks the user to confirm."""
    # _load_meta returns None on a read error, and this advisory deliberately
    # discards that error, so prd_meta/tdd_meta may be None -- keep the `or {}`.
    prd_meta, _ = _load_meta(prd_path)
    tdd_meta, _ = _load_meta(tdd_path)
    prd_status = str((prd_meta or {}).get("prd_status") or "unknown")
    tdd_status = str((tdd_meta or {}).get("tdd_status") or "unknown")
    approved = prd_status == "approved" and tdd_status == "approved"
    if approved:
        detail = "PRD and TDD are both approved"
    else:
        detail = (f"PRD '{prd_status}', TDD '{tdd_status}' -- not both approved; "
                  "issues created now will churn when the docs are. Confirm with "
                  "the user before creating.")
    return {"prd_status": prd_status, "tdd_status": tdd_status,
            "approved": approved, "detail": detail}


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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prd", required=True, help="prd-data.yaml")
    ap.add_argument("--tdd", required=True, help="tdd-data.yaml")
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
        _report(checks, None, [], None, args.json)
        sys.exit(2)

    approval = check_approval(args.prd, args.tdd)   # advisory; never gates
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
