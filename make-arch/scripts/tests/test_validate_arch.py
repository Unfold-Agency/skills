#!/usr/bin/env python3
"""Self-contained test harness for validate_arch.py.

  1. the valid fixture passes
  2. fingerprint integrity (A-007) fails CLOSED on a contract change un-restamped
  3. one targeted mutation per rule trips EXACTLY that rule
  4. A-008 append-only — origin/main baseline fails CLOSED on a non-repo, an
     unresolvable ref, and a shallow clone; passes greenfield; catches a real
     deleted ADR (throwaway local git repos, no network)

  python scripts/tests/test_validate_arch.py
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

VALIDATOR = os.path.join(SCRIPTS, "validate_arch.py")
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
    subprocess.run([sys.executable, STAMP, spec_dir], capture_output=True, text=True)


def codes(out):
    return {ln.strip().split("]")[0].lstrip("[")
            for ln in out.splitlines() if ln.strip().startswith("[A-")}


def edit_yaml(path, fn):
    with open(path) as f:
        doc = yaml.safe_load(f)
    fn(doc)
    with open(path, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)


def arch(spec_dir):
    return os.path.join(spec_dir, "arch-data.yaml")


def feature(spec_dir):
    return os.path.join(spec_dir, "features", "checkout-data.yaml")


def archmd(spec_dir):
    return os.path.join(spec_dir, "architecture.md")


# ── 1. base passes ───────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    rc, out = run_validator(d, "--no-baseline")
    check("base fixture passes (exit 0)", rc == 0 and not codes(out))


# ── 2. A-007 fingerprint fails closed on a contract change ───────────
with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    edit_yaml(arch(d), lambda doc: doc["components"][0].__setitem__(
        "responsibility", "A different responsibility."))
    rc, out = run_validator(d, "--no-baseline")
    check("A-007: a contract change without re-stamping fails closed",
          rc == 1 and codes(out) == {"A-007"})

with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    # arch_version is OUT of the fingerprint — touching it alone still passes
    edit_yaml(arch(d), lambda doc: doc["meta"].__setitem__("arch_version", "zzzzzzzzzzzz"))
    rc, out = run_validator(d, "--no-baseline")
    check("A-007 OUT: an arch_version-only change still passes",
          rc == 0 and "A-007" not in codes(out))


# ── 3. one targeted mutation per rule ────────────────────────────────
def m_a001(d):
    edit_yaml(arch(d), lambda doc: doc["meta"].pop("status", None))

def m_a002(d):
    # a new decision with a malformed id and no file; proposed so A-004 skips it
    edit_yaml(arch(d), lambda doc: doc["decisions"].append(
        {"id": "ADR-99", "title": "Bad", "status": "proposed", "scope": "feature",
         "superseded_by": "", "confidence": "known", "governs": []}))

def m_a003(d):
    edit_yaml(arch(d), lambda doc: next(
        x for x in doc["decisions"] if x["id"] == "ADR-0002"
    ).__setitem__("superseded_by", ""))

def m_a004(d):
    # drop the feature ref to ADR-0003 -> it becomes an accepted orphan
    edit_yaml(feature(d), lambda doc: doc["requirements"].__setitem__(
        slice(None), [r for r in doc["requirements"] if r["id"] != "FR-CHK-002"]))

def m_a005(d):
    edit_yaml(arch(d), lambda doc: doc["components"][0].__setitem__("confidence", "maybe"))

def m_a006(d):
    # remove the mermaid block from architecture.md (md is not fingerprinted)
    with open(archmd(d)) as f:
        text = f.read()
    text = text.replace("```mermaid", "```text", 1)
    with open(archmd(d), "w") as f:
        f.write(text)


# (rule, fn, restamp?)
MUTATIONS = [
    ("A-001", m_a001, True),
    ("A-002", m_a002, True),
    ("A-003", m_a003, True),
    ("A-004", m_a004, False),   # edits features only; arch fingerprint unchanged
    ("A-005", m_a005, True),
    ("A-006", m_a006, False),   # edits md only; arch fingerprint unchanged
]

for rule, mut, restamp in MUTATIONS:
    with tempfile.TemporaryDirectory() as tmp:
        d = copy_fixture(os.path.join(tmp, "specs"))
        mut(d)
        if restamp:
            stamp(d)
        rc, out = run_validator(d, "--no-baseline")
        got = codes(out)
        if rc == 1 and got == {rule}:
            check(f"{rule}: {mut.__name__} trips exactly {rule}", True)
        else:
            check(f"{rule}: {mut.__name__} trips exactly {rule} (rc={rc} got={sorted(got)})", False)


# ── 4. A-008 append-only against origin/main, fail-closed ────────────
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


if shutil.which("git") is None:
    print("WARN git not available — skipping A-008 git scenarios")
else:
    # (A) non-repo → fail closed
    with tempfile.TemporaryDirectory() as tmp:
        d = copy_fixture(os.path.join(tmp, "specs"))
        rc, out = run_validator(d)
        check("A-008 non-repo fails closed",
              rc == 1 and "A-008" in codes(out) and "not a git" in out)

    # (B) repo, origin/main unresolvable → fail closed
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.join(tmp, "repo")
        init_repo(repo)
        rc, out = run_validator(os.path.join(repo, "docs", "specs"))
        check("A-008 unresolvable ref fails closed",
              rc == 1 and "A-008" in codes(out) and "cannot resolve" in out)

    # (C) a deleted ADR vs origin/main → caught (append-only)
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin)
        work = os.path.join(tmp, "work")
        git(tmp, "clone", "-q", origin, work)
        wspecs = os.path.join(work, "docs", "specs")
        # delete the superseded ADR-0002 from the index + remove its file
        edit_yaml(arch(wspecs), lambda doc: doc.__setitem__(
            "decisions", [x for x in doc["decisions"] if x["id"] != "ADR-0002"]))
        os.remove(os.path.join(wspecs, "decisions", "ADR-0002-self-hosted-form.md"))
        stamp(wspecs)
        rc, out = run_validator(wspecs)
        check("A-008 catches a deleted ADR vs origin/main",
              rc == 1 and codes(out) == {"A-008"} and "ADR-0002" in out)

    # (D) shallow clone → fail closed
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin)
        shallow = os.path.join(tmp, "shallow")
        git(tmp, "clone", "-q", "--depth", "1", f"file://{os.path.abspath(origin)}", shallow)
        rc, out = run_validator(os.path.join(shallow, "docs", "specs"))
        check("A-008 shallow clone fails closed",
              rc == 1 and "A-008" in codes(out) and "shallow" in out)

    # (E) greenfield: origin/main resolves but has no arch-data → passes
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin, with_specs=False)
        work = os.path.join(tmp, "work")
        git(tmp, "clone", "-q", origin, work)
        wspecs = copy_fixture(os.path.join(work, "docs", "specs"))
        rc, out = run_validator(wspecs)
        check("A-008 greenfield against resolvable main passes",
              rc == 0 and not codes(out))


print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("validate_arch: all cases behaved as expected")
sys.exit(0)
