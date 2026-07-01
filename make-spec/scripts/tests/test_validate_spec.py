#!/usr/bin/env python3
"""Self-contained test harness for validate_spec.py.

Sections:
  1. the valid fixture passes
  2. C1 keystone -- the fingerprint IN/OUT contract: a `priority` change (OUT)
     still passes un-restamped; a meaning change (IN) fails CLOSED with S-006
  3. one targeted mutation per rule trips EXACTLY that rule (re-stamped so only
     the intended rule fires -- the per-rule mutation pattern)
  4. the EARS classifier (ears_kind) accepts the five forms and rejects non-EARS
  5. the lean budget (S-012) warns without failing
  6. M2 no-vanishing -- origin/main baseline fails CLOSED on a non-repo, an
     unresolvable ref, and a shallow clone; passes greenfield; catches a real
     vanished id (uses throwaway local git repos, no network)

  python scripts/tests/test_validate_spec.py
Exit 0 = every case behaved as expected.
"""
import copy
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import yaml  # noqa: E402
from validate_spec import ears_kind, compute_fingerprint  # noqa: E402
import validate_spec as _vs  # noqa: E402  -- monkeypatched in the baseline unit tests

VALIDATOR = os.path.join(SCRIPTS, "validate_spec.py")
STAMP = os.path.join(SCRIPTS, "stamp_fingerprint.py")
FIXTURE = os.path.join(HERE, "specs")

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


def copy_fixture(dst):
    shutil.copytree(FIXTURE, dst)
    return dst


def run_validator(spec_dir, *extra):
    r = subprocess.run([sys.executable, VALIDATOR, spec_dir, *extra],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def stamp(spec_dir):
    subprocess.run([sys.executable, STAMP, spec_dir],
                   capture_output=True, text=True)


def codes(out):
    return {ln.strip().split("]")[0].lstrip("[")
            for ln in out.splitlines()
            if ln.strip().startswith("[S-")}


def edit_yaml(path, fn):
    """Edit the YAML frontmatter of a single-file spec in place, preserving body."""
    with open(path) as f:
        text = f.read()
    fm, body = _vs.split_frontmatter(text)
    doc = (yaml.safe_load(fm) if fm is not None else {}) or {}
    fn(doc)
    dumped = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    with open(path, "w") as f:
        f.write("---\n" + dumped + "---\n" + (body or ""))


def write_doc(path, doc, body="\n# fixture\n"):
    """Write a new single-file spec from a doc dict + a minimal body."""
    dumped = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    with open(path, "w") as f:
        f.write("---\n" + dumped + "---\n" + body)


def feat(spec_dir, slug):
    return os.path.join(spec_dir, "features", f"{slug}.md")


def overview(spec_dir):
    return os.path.join(spec_dir, "overview.md")


# ── 1. base passes ───────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    rc, out = run_validator(d, "--no-baseline")
    check("base fixture passes (exit 0)", rc == 0 and not codes(out))


# ── 1b. a malformed top-level frontmatter (a YAML list, not a mapping) must fail
#       CLOSED via S-001 -- never crash with an uncaught AttributeError ──────────
with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    with open(overview(d), "w") as f:
        f.write("---\n- a\n- b\n---\n\n# bad\n")
    rc, out = run_validator(d, "--no-baseline")
    check("non-dict overview frontmatter -> clean S-001, no traceback",
          rc == 1 and "S-001" in codes(out) and "Traceback" not in out)

with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    with open(feat(d, "checkout"), "w") as f:
        f.write("---\n- not\n- a\n- mapping\n---\n\n# bad\n")
    rc, out = run_validator(d, "--no-baseline")
    check("non-dict feature frontmatter -> clean S-001, no traceback",
          rc == 1 and "S-001" in codes(out) and "Traceback" not in out)


# ── 2. C1 keystone: the fingerprint IN/OUT contract ──────────────────
with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    # priority is OUT -- change it and do NOT re-stamp; must still pass.
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc["requirements"][0].__setitem__("priority", "could"))
    rc, out = run_validator(d, "--no-baseline")
    check("C1 OUT: a priority change without re-stamping still passes",
          rc == 0 and "S-006" not in codes(out))

with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    # description is IN -- change it and do NOT re-stamp; must fail CLOSED.
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc["requirements"][0].__setitem__(
                  "description", "A materially different behavior."))
    rc, out = run_validator(d, "--no-baseline")
    check("C1 IN: a description change without re-stamping fails S-006",
          rc == 1 and codes(out) == {"S-006"})

with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    # acceptance_criteria is IN -- mutate a criterion (to another valid EARS
    # sentence) without re-stamping; must fail CLOSED with only S-006.
    def mut_ac(doc):
        doc["requirements"][0]["acceptance_criteria"][0] = \
            "WHEN the user confirms, the system shall reserve inventory."
    edit_yaml(feat(d, "checkout"), mut_ac)
    rc, out = run_validator(d, "--no-baseline")
    check("C1 IN: an acceptance-criterion change without re-stamping fails S-006",
          rc == 1 and codes(out) == {"S-006"})

with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    # A blank (never-stamped) fingerprint must fail CLOSED, not pass -- this is the
    # un-stamped guard, the more important half of the keystone.
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc["meta"].__setitem__("fingerprint", ""))
    rc, out = run_validator(d, "--no-baseline")
    check("C1 blank: an un-stamped (blank) fingerprint fails S-006",
          rc == 1 and codes(out) == {"S-006"} and "blank" in out)


# ── 3. one targeted mutation per rule (re-stamped) ───────────────────
def m_s001(d):
    edit_yaml(overview(d), lambda doc: doc["meta"].pop("mode", None))

def m_s002_req(d):
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc["requirements"][0].__setitem__("id", "FR-CHK-1"))

def m_s002_goal(d):
    edit_yaml(overview(d),
              lambda doc: doc["goals"][0].__setitem__("id", "GOAL-1"))
    # G-001 is referenced by the features' `supports`; clear those so the
    # malformed-goal-id S-002 is the ONLY rule that trips (a now-dangling
    # supports entry would otherwise also fire S-013 -- the real cascade).
    for slug in ("cart", "checkout"):
        edit_yaml(feat(d, slug), lambda doc: doc.__setitem__("supports", []))

def m_s003_dup_id(d):
    def fn(doc):
        dup = copy.deepcopy(doc["requirements"][0])  # id FR-CART-001 again
        doc["requirements"].append(dup)
    edit_yaml(feat(d, "cart"), fn)

def m_s003_dup_prefix(d):
    extra = {
        "meta": {"doc_type": "spec-feature", "schema_version": "1.0",
                 "slug": "extra", "prefix": "CHK", "title": "Extra",
                 "status": "active", "feature_version": "", "fingerprint": ""},
        "user_stories": ["As a user, I want extra, so that I benefit."],
        "no_gos": [],
        "requirements": [{
            "id": "FR-CHK-900", "name": "Extra", "kind": "functional",
            "description": "An extra behavior.",
            "acceptance_criteria": [
                "The system shall do the extra thing.",
                "IF it cannot, THEN the system shall report why."],
            "governed_by": [], "depends_on": [], "interface": "",
            "priority": "could", "architecture_hints": "", "related_files": [],
            "notes": "", "status": "active"}],
    }
    write_doc(feat(d, "extra"), extra)
    edit_yaml(overview(d), lambda doc: doc["feature_index"].append(
        {"slug": "extra", "prefix": "CHK", "title": "Extra",
         "feature_version": "", "status": "active"}))

def m_s004_dangling_dep(d):
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc["requirements"][0].__setitem__("depends_on",
                                                             ["FR-CART-999"]))

def m_s004_bad_adr(d):
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc["requirements"][0].__setitem__("governed_by",
                                                            ["ADR-1"]))

def m_s007_namespace(d):
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc["requirements"][0].__setitem__("id", "FR-XYZ-001"))

def m_s008_version_drift(d):
    # feature_version is OUT of the overview fingerprint, so this does NOT
    # need a re-stamp and must trip ONLY S-008.
    edit_yaml(overview(d), lambda doc: next(
        r for r in doc["feature_index"] if r["slug"] == "checkout"
    ).__setitem__("feature_version", "000000000000"))

def m_s008_missing_row(d):
    edit_yaml(overview(d), lambda doc: doc.__setitem__(
        "feature_index", [r for r in doc["feature_index"]
                          if r["slug"] != "checkout"]))

def m_s009_unmeasurable(d):
    edit_yaml(overview(d),
              lambda doc: doc["goals"][0].__setitem__("measurement_method", ""))

def m_s010_non_ears(d):
    edit_yaml(feat(d, "cart"), lambda doc: doc["requirements"][0]
              ["acceptance_criteria"].append("The cart is nice."))

def m_s011_no_unwanted(d):
    # drop the IF...THEN criterion from an FR, leaving only the WHEN one
    edit_yaml(feat(d, "cart"), lambda doc: doc["requirements"][0].__setitem__(
        "acceptance_criteria",
        [doc["requirements"][0]["acceptance_criteria"][0]]))

def m_s008_meta_slug(d):
    # meta.slug disagrees with the file slug (dark branch, validate_spec.py:295-296)
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc["meta"].__setitem__("slug", "wrongslug"))

def m_s008_index_prefix(d):
    # a feature_index row's prefix disagrees with the feature meta.prefix (407-409)
    edit_yaml(overview(d), lambda doc: next(
        r for r in doc["feature_index"] if r["slug"] == "checkout"
    ).__setitem__("prefix", "ZZ"))

def m_s004_adr_nofile(d):
    # governed_by names a well-formed ADR with no file under a NON-empty decisions/.
    decdir = os.path.join(d, "decisions")
    os.makedirs(decdir, exist_ok=True)
    with open(os.path.join(decdir, "ADR-0001-seed.md"), "w") as f:
        f.write("# ADR-0001\n")
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc["requirements"][0].__setitem__("governed_by",
                                                             ["ADR-0002"]))

def m_s004_adr_emptydir(d):
    # governed_by names an ADR while decisions/ exists but is EMPTY. The existence
    # check must still fire (has_dec_dir, not the falsy adr_files set) -- the hole
    # the PR review flagged: an empty dir used to short-circuit the check.
    os.makedirs(os.path.join(d, "decisions"), exist_ok=True)
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc["requirements"][0].__setitem__("governed_by",
                                                             ["ADR-0001"]))


def m_s013_dangling_supports(d):
    # a well-formed but dangling goal id in `supports` (IN the fingerprint, so
    # restamp to keep S-006 silent -- only the missing-goal S-013 should fire)
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc.__setitem__("supports", ["G-999"]))


def m_s013_nonlist_supports(d):
    # a bare scalar instead of a list (supports: G-001). The guard must fire one
    # S-013 rather than iterating the string char-by-char into a noisy cascade.
    edit_yaml(feat(d, "checkout"),
              lambda doc: doc.__setitem__("supports", "G-001"))


# (rule, mutate_fn, restamp?) -- restamp so only the intended rule trips
MUTATIONS = [
    ("S-001", m_s001, True),
    ("S-002", m_s002_req, True),
    ("S-002", m_s002_goal, True),
    ("S-003", m_s003_dup_id, True),
    ("S-003", m_s003_dup_prefix, True),
    ("S-004", m_s004_dangling_dep, True),
    ("S-004", m_s004_bad_adr, True),
    ("S-004", m_s004_adr_nofile, True),
    ("S-004", m_s004_adr_emptydir, True),
    ("S-007", m_s007_namespace, True),
    ("S-008", m_s008_version_drift, False),
    ("S-008", m_s008_missing_row, True),
    ("S-008", m_s008_meta_slug, True),
    ("S-008", m_s008_index_prefix, True),
    ("S-009", m_s009_unmeasurable, True),
    ("S-010", m_s010_non_ears, True),
    ("S-011", m_s011_no_unwanted, True),
    ("S-013", m_s013_dangling_supports, True),
    ("S-013", m_s013_nonlist_supports, True),
]

for rule, mut, restamp in MUTATIONS:
    with tempfile.TemporaryDirectory() as tmp:
        d = copy_fixture(os.path.join(tmp, "specs"))
        mut(d)
        if restamp:
            stamp(d)
        rc, out = run_validator(d, "--no-baseline")
        got = codes(out)
        label = f"{rule}: {mut.__name__}"
        if rc == 1 and got == {rule}:
            check(f"{label} trips exactly {rule}", True)
        else:
            check(f"{label} trips exactly {rule} (rc={rc} got={sorted(got)})", False)


# ── 4. EARS classifier ───────────────────────────────────────────────
check("EARS ubiquitous", ears_kind("The system shall encrypt data.") == "ubiquitous")
check("EARS event", ears_kind("WHEN x happens, the system shall y.") == "event")
check("EARS state", ears_kind("WHILE charging, the system shall y.") == "state")
check("EARS optional", ears_kind("WHERE GPS is fitted, the system shall y.") == "optional")
check("EARS unwanted", ears_kind("IF x, THEN the system shall y.") == "unwanted")
check("EARS rejects no-shall", ears_kind("The system encrypts data.") is None)
check("EARS rejects IF without THEN", ears_kind("IF x the system shall y.") is None)
check("EARS rejects 'shall' as a substring (marshall / shallow-copies)",
      ears_kind("Marshall reviews the order.") is None
      and ears_kind("WHEN it fires, the system shallow-copies state.") is None)
check("EARS unwanted is not fooled by 'shallow' appearing before THEN",
      ears_kind("IF the shallow buffer overflows, THEN the system shall reset.")
      == "unwanted")


# ── 5. lean budget warns without failing ─────────────────────────────
with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    rc, out = run_validator(d, "--no-baseline", "--budget-reqs", "1")
    check("S-012 budget warns but does not fail (exit 0)",
          rc == 0 and "warn [S-012]" in out)


# ── 6. M2 no-vanishing against origin/main, fail-closed ──────────────
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV,
                          capture_output=True, text=True)


def init_repo(path, with_specs=True):
    os.makedirs(path)
    git(path, "init", "-q", "-b", "main")
    if with_specs:
        copy_fixture(os.path.join(path, "docs", "specs"))
    else:
        with open(os.path.join(path, "README.md"), "w") as f:
            f.write("# seed\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "base")


git_ok = shutil.which("git") is not None
if not git_ok:
    print("WARN git not available -- skipping S-005 git scenarios")
else:
    # (A) non-repo → fail closed
    with tempfile.TemporaryDirectory() as tmp:
        d = copy_fixture(os.path.join(tmp, "specs"))
        rc, out = run_validator(d)  # default --baseline-ref origin/main
        check("S-005 non-repo fails closed",
              rc == 1 and "S-005" in codes(out) and "not a git" in out)

    # (B) repo but origin/main unresolvable → fail closed
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.join(tmp, "repo")
        init_repo(repo)
        rc, out = run_validator(os.path.join(repo, "docs", "specs"))
        check("S-005 unresolvable ref fails closed",
              rc == 1 and "S-005" in codes(out) and "cannot resolve" in out)

    # (C) origin/main exists, a requirement vanished in the working tree → caught
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin)
        work = os.path.join(tmp, "work")
        git(tmp, "clone", "-q", origin, work)
        wspecs = os.path.join(work, "docs", "specs")
        edit_yaml(feat(wspecs, "checkout"), lambda doc: doc.__setitem__(
            "requirements", [r for r in doc["requirements"]
                             if r["id"] != "FR-CHK-001"]))
        stamp(wspecs)
        rc, out = run_validator(wspecs)  # baseline origin/main
        check("S-005 catches a real vanished id vs origin/main",
              rc == 1 and codes(out) == {"S-005"} and "FR-CHK-001" in out)

    # (D) shallow clone → fail closed (file:// so --depth is honored)
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin)
        shallow = os.path.join(tmp, "shallow")
        git(tmp, "clone", "-q", "--depth", "1", f"file://{os.path.abspath(origin)}",
            shallow)
        rc, out = run_validator(os.path.join(shallow, "docs", "specs"))
        check("S-005 shallow clone fails closed",
              rc == 1 and "S-005" in codes(out) and "shallow" in out)

    # (E) greenfield: origin/main resolves but has no docs/specs → passes
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin, with_specs=False)
        work = os.path.join(tmp, "work")
        git(tmp, "clone", "-q", origin, work)
        wspecs = copy_fixture(os.path.join(work, "docs", "specs"))
        rc, out = run_validator(wspecs)  # baseline origin/main, dir absent there
        check("S-005 greenfield against resolvable main passes",
              rc == 0 and not codes(out))


# ── 7. compute_fingerprint: OUT keys stripped at EVERY level (C1 unit) ───
def _load(path):
    return _vs.load_spec_doc(path)

with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    ov = _load(overview(d))
    ov_base = compute_fingerprint(ov)
    ov_out = copy.deepcopy(ov)
    row = next(r for r in ov_out["feature_index"] if r["slug"] == "checkout")
    row["feature_version"] = "ffffffffffff"
    row["appetite"] = "1 day"
    check("fp: OUT keys inside a feature_index row (feature_version, appetite) do "
          "not flip the overview fingerprint", compute_fingerprint(ov_out) == ov_base)
    ov_in = copy.deepcopy(ov)
    next(r for r in ov_in["feature_index"] if r["slug"] == "checkout")["slug"] = "renamed"
    check("fp: a feature_index identity change (slug) DOES flip the overview fingerprint",
          compute_fingerprint(ov_in) != ov_base)

    ft = _load(feat(d, "checkout"))
    ft_base = compute_fingerprint(ft)
    for outk, val in (("notes", "x"), ("architecture_hints", "y"), ("priority", "could")):
        m = copy.deepcopy(ft)
        m["requirements"][0][outk] = val
        check(f"fp: requirement OUT key '{outk}' does not flip the fingerprint",
              compute_fingerprint(m) == ft_base)
    m = copy.deepcopy(ft)
    m["meta"]["appetite"] = "3 weeks"
    check("fp: meta.appetite does not flip the feature fingerprint",
          compute_fingerprint(m) == ft_base)
    m = copy.deepcopy(ft)
    m["requirements"][0]["acceptance_criteria"][0] = \
        "WHEN paid, the system shall ship the order."
    check("fp: an acceptance_criteria change DOES flip the feature fingerprint",
          compute_fingerprint(m) != ft_base)


# ── 8. baseline_ids fails CLOSED on a degraded git baseline (unit) ───────
# Monkeypatch _vs._git to drive the rare degraded-repo branches a throwaway repo
# can't reliably reproduce (corrupt tree / unreadable blob / erroring probe).
# Probes default to a trusted, resolvable, non-shallow repo; override per case.
class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

def _run_baseline(overrides):
    def fake(args, cwd):
        sub = args[0]
        if sub == "rev-parse" and "--is-inside-work-tree" in args:
            return overrides.get("inside", _FakeProc(0, "true"))
        if sub == "rev-parse" and "--is-shallow-repository" in args:
            return overrides.get("shallow", _FakeProc(0, "false"))
        if sub == "rev-parse" and "--verify" in args:
            return overrides.get("resolve", _FakeProc(0, "deadbeef"))
        if sub == "ls-tree":
            return overrides.get("ls_tree", _FakeProc(0, ""))
        if sub == "show":
            return overrides.get("show", _FakeProc(0, ""))
        return _FakeProc(0, "")
    errs = []
    orig = _vs._git
    _vs._git = fake
    try:
        result = _vs.baseline_ids(".", "origin/main",
                                  lambda rule, msg: errs.append((rule, msg)))
    finally:
        _vs._git = orig
    return result, [r for r, _ in errs]

res, errs = _run_baseline({"ls_tree": _FakeProc(128, "", "fatal: not a tree object")})
check("baseline_ids: ls-tree failure fails CLOSED (None + S-005), not empty set",
      res is None and "S-005" in errs)
res, errs = _run_baseline({"ls_tree": _FakeProc(0, "overview.md\n"),
                           "show": _FakeProc(128, "", "fatal: bad object")})
check("baseline_ids: an unreadable baseline blob fails CLOSED (None + S-005)",
      res is None and "S-005" in errs)
res, errs = _run_baseline({"shallow": _FakeProc(128, "", "fatal")})
check("baseline_ids: an erroring shallow probe fails CLOSED (None + S-005)",
      res is None and "S-005" in errs)
res, errs = _run_baseline({"ls_tree": _FakeProc(0, "overview.md\n"),
                           "show": _FakeProc(0, "---\ngoals:\n- id: G-001\n---\n")})
check("baseline_ids: a clean baseline returns the prior id set (not None)",
      res == {"G-001"} and not errs)


print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("validate_spec: all cases behaved as expected")
sys.exit(0)
