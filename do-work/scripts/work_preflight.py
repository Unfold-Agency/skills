#!/usr/bin/env python3
"""Preflight gate for do-work. Read-only: it CHECKS and REPORTS; it never
writes GitHub state or touches code. The skill reads the verdict and acts
(ensures labels, selects the next issue, or stops).

do-work builds the project from the GitHub issues that make-issues created from
the docs/product/ spec set. Its gate is the build-lane facts: the spec set is
present, a backlog exists, and you must not build issues make-issues has flagged
stale. do-work TRUSTS make-issues for drift detection -- it does not recompute
spec fingerprints (that is make-issues' fail-closed gate); it reads the version
stamps make-spec already wrote.

Checks, in order of dependency (a gating failure aborts before the next):
  1. auth     -- `gh auth status` succeeds
  2. gh_version -- gh >= 2.94.0 (native dependency/type flags)
  3. specs    -- docs/product/ has an overview.md and >=1 features/*.md
                 (else run /make-spec, then /make-issues)
  4. repo     -- inside a git work tree AND a resolvable owner/name remote
  5. backlog  -- make-issues-managed issues exist (else run /make-issues first)

Then non-gating ADVISORIES (reported, never abort):
  - drift     -- open managed issues carrying needs-rebase / spec-drift /
                 orphaned / escalated / stale-against-dependency are NOT buildable
  - sync_owed -- an open issue's stamped source_version lags its feature's live
                 feature_version in the overview index; a /make-issues sync is owed
  - labels    -- the do-work lifecycle labels (status:doing, escalated,
                 needs-human-review) the skill creates if missing

  python scripts/work_preflight.py --spec-dir docs/product
  python scripts/work_preflight.py --spec-dir docs/product --repo owner/name --json

Exit codes: 0 = gate passes, 1 = a gating check failed, 2 = the spec set can't be
read. Advisories never change the exit code.
"""
import argparse
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
# Lifecycle labels do-work owns and creates if missing. status:doing is the
# in-progress signal make-issues reconciliation reads as "started";
# needs-human-review tags the follow-ups --dangerously opens.
MAKE_WORK_LABELS = ["status:doing", "escalated", "needs-human-review"]
# Labels that make a managed issue NOT buildable. make-issues sets the spec-drift
# ones; escalated is do-work's hand-back; stale-against-dependency is the seam flag.
NOT_BUILDABLE_FLAGS = ["needs-rebase", "spec-drift", "orphaned", "escalated",
                       "stale-against-dependency"]
# The make-issues meta block embedded in each managed issue body. do-work reads
# `feature` + `source_version` from it (the make-spec content version the issue
# was born from) to decide whether a /make-issues sync is owed.
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


# A spec doc is a single .md whose contract lives in YAML frontmatter (make-spec
# emits one file per document; no separate data file). Dispatch on extension.
FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def _load_yaml(path):
    """Load a spec doc as a mapping. A .md spec carries its contract in YAML
    frontmatter; any other file is loaded directly. Returns (doc, None) or
    (None, err)."""
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


def check_specs(spec_dir):
    """Gating: the docs/product set must be present -- an overview.md and at least
    one features/*.md. A missing/unreadable overview is fatal (exit 2); no features
    means there is nothing to build issues from. Pure file checks -- do-work does
    NOT recompute fingerprints (it trusts make-issues' gate)."""
    overview = os.path.join(spec_dir, "overview.md")
    if not os.path.isfile(overview):
        legacy = os.path.join(os.path.dirname(os.path.normpath(spec_dir)), "specs")
        hint = (f" -- legacy layout detected at {legacy}/: migrate with "
                f"'git mv {legacy} {os.path.normpath(spec_dir)}' "
                f"(or pass --spec-dir {legacy})") if os.path.isdir(legacy) else ""
        return {"name": "specs", "ok": False, "fatal": True,
                "detail": f"no {overview} -- run /make-spec to author the spec set "
                          f"({spec_dir}/), then /make-issues{hint}"}
    _, err = _load_yaml(overview)
    if err:
        return {"name": "specs", "ok": False, "fatal": True, "detail": err}
    import glob
    features = glob.glob(os.path.join(spec_dir, "features", "*.md"))
    if not features:
        return {"name": "specs", "ok": False,
                "detail": f"{overview} present but no features/*.md -- "
                          "run /make-spec to add features"}
    return {"name": "specs", "ok": True, "feature_count": len(features),
            "detail": f"overview + {len(features)} feature(s) under {spec_dir}"}


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
    """Parse the YAML inside an issue body's make-issues:meta markers. {} when the
    block is missing or malformed."""
    m = _META_RE.search(body or "")
    if not m:
        return {}
    inner = re.sub(r"```[a-zA-Z]*", "", m.group(1)).replace("```", "")
    try:
        data = yaml.safe_load(inner)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def overview_feature_versions(spec_dir):
    """{slug: feature_version} from the overview feature_index -- the LIVE content
    versions make-spec stamped. do-work reads these (it does not recompute them) to
    tell whether an issue's stamped source_version has fallen behind."""
    doc, err = _load_yaml(os.path.join(spec_dir, "overview.md"))
    if err or not isinstance(doc, dict):
        return {}
    out = {}
    for row in doc.get("feature_index") or []:
        if isinstance(row, dict) and row.get("slug"):
            out[str(row["slug"])] = str(row.get("feature_version") or "")
    return out


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


def scan_advisories(issues, spec_dir, have_labels):
    """Non-gating advisories: drifted (not-buildable) open issues; a possibly-owed
    sync (an open issue's stamped source_version != its feature's live
    feature_version); and missing do-work labels."""
    live = overview_feature_versions(spec_dir)
    flagged, stale_syncs = [], []
    for i in issues:
        if i.get("state") != "OPEN":
            continue
        names = _label_names(i)
        hit = sorted(names & set(NOT_BUILDABLE_FLAGS))
        if hit:
            flagged.append({"number": i.get("number"), "flags": hit})
        meta = _issue_meta(i.get("body", ""))
        feature = str(meta.get("feature") or "")
        stamped = str(meta.get("source_version") or "")
        current = live.get(feature)
        if feature and stamped and current and stamped != current:
            stale_syncs.append({"number": i.get("number"), "feature": feature,
                                "stamped": stamped, "live": current})
    missing_labels = [n for n in MAKE_WORK_LABELS if n not in (have_labels or set())]
    return {"flagged": flagged, "stale_syncs": stale_syncs,
            "sync_owed": bool(stale_syncs), "missing_labels": missing_labels}


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
    ap.add_argument("--spec-dir", default="docs/product",
                    help="the spec directory (default: docs/product)")
    ap.add_argument("--repo", help="owner/name; skip gh repo auto-detect")
    ap.add_argument("--json", action="store_true", help="emit the verdict as JSON")
    args = ap.parse_args()

    checks = []
    auth = check_auth()
    checks.append(auth)
    checks.append(check_gh_version())
    specs = check_specs(args.spec_dir)
    checks.append(specs)
    if specs.get("fatal"):                # the spec set itself is missing/unreadable
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
            advisories = scan_advisories(issues, args.spec_dir, _have_labels(repo))

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
        for s in advisories["stale_syncs"]:
            print(f"  warn   sync may be owed: #{s['number']} stamped "
                  f"{s['feature']} v{s['stamped']} but live is v{s['live']}; "
                  "run /make-issues")
        if advisories["missing_labels"]:
            print("  note   missing do-work labels (skill must create): "
                  + ", ".join(advisories["missing_labels"]))
    print()
    print("PASS -- preflight gate clear" if all(c["ok"] for c in checks)
          else "FAIL -- do not proceed; resolve the failed check(s) above")


if __name__ == "__main__":
    main()
