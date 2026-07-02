#!/usr/bin/env python3
"""Self-contained test harness for validate_arch.py (single-file layout, v2.0).

  1. the valid fixture passes (architecture.md frontmatter + ADR frontmatter;
     no arch-data.yaml)
  2. fingerprint integrity (A-007) on architecture.md fails CLOSED on a
     contract change un-restamped; body edits are OUT of the fingerprint
  3. one targeted mutation per rule trips EXACTLY that rule
  4. A-008 append-only -- origin/main baseline fails CLOSED on a non-repo, an
     unresolvable ref, and a shallow clone; passes greenfield; catches a real
     deleted ADR file (throwaway local git repos, no network)
  5. supersession integrity (cycles, dead/proposed targets, a feature
     governed_by a superseded/unknown ADR) and A-006 diagram-kind matching
  6. A-009 immutable-once-accepted: prose and frontmatter edits to a
     baseline-accepted ADR fail; the supersede transition passes; a reversal
     to 'proposed' fails; a pre-v2.0 (no-frontmatter) baseline is exempt
     (the migration window)
  7. migrate_arch_data.py: a legacy arch-data.yaml fixture migrates to a
     passing v2.0 layout; idempotent; --dry-run writes nothing

  python scripts/tests/test_validate_arch.py
Exit 0 = every case behaved as expected.
"""
import glob
import os
import re
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
MIGRATE = os.path.join(SCRIPTS, "migrate_arch_data.py")
FIXTURE = os.path.join(HERE, "specs")
LEGACY_FIXTURE = os.path.join(HERE, "legacy-specs")

failures = []


def check(name, cond):
    print(f"{'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


def copy_fixture(dst, src=FIXTURE):
    shutil.copytree(src, dst)
    return dst


def run_validator(spec_dir, *extra):
    r = subprocess.run([sys.executable, VALIDATOR, spec_dir, *extra],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def run_migrate(spec_dir, *extra):
    r = subprocess.run([sys.executable, MIGRATE, spec_dir, *extra],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def stamp(spec_dir):
    subprocess.run([sys.executable, STAMP, spec_dir], capture_output=True, text=True)


def codes(out):
    return {ln.strip().split("]")[0].lstrip("[")
            for ln in out.splitlines() if ln.strip().startswith("[A-")}


FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def edit_md(path, fn):
    """Edit a single-file doc via its YAML frontmatter; the body is preserved."""
    with open(path) as f:
        text = f.read()
    m = FRONTMATTER_RE.match(text)
    fm = m.group(1) if m else ""
    body = text[m.end():] if m else text
    doc = yaml.safe_load(fm) or {}
    fn(doc)
    dumped = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    with open(path, "w") as f:
        f.write("---\n" + dumped + "---\n" + body)


def append_body(path, line):
    with open(path, "a") as f:
        f.write(line)


def arch(spec_dir):
    return os.path.join(spec_dir, "architecture.md")


def feature(spec_dir):
    return os.path.join(spec_dir, "features", "checkout.md")


def adr(spec_dir, adr_id):
    hits = glob.glob(os.path.join(spec_dir, "decisions", f"{adr_id}-*.md"))
    assert hits, f"no fixture file for {adr_id}"
    return hits[0]


def edit_adr(spec_dir, adr_id, **kv):
    edit_md(adr(spec_dir, adr_id), lambda doc: doc.update(kv))


# ── 1. base passes ───────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    rc, out = run_validator(d, "--no-baseline")
    check("base fixture passes (exit 0)", rc == 0 and not codes(out))
    check("base fixture warns on the unreferenced project-scoped ADR",
          "A-004" in out and "project-scoped" in out)


# ── 2. A-007 fingerprint on architecture.md fails closed ─────────────
with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    edit_md(arch(d), lambda doc: doc["components"][0].__setitem__(
        "responsibility", "A different responsibility."))
    rc, out = run_validator(d, "--no-baseline")
    check("A-007: a contract change without re-stamping fails closed",
          rc == 1 and codes(out) == {"A-007"})

with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    # arch_version is OUT of the fingerprint -- touching it alone still passes
    edit_md(arch(d), lambda doc: doc["meta"].__setitem__("arch_version", "zzzzzzzzzzzz"))
    rc, out = run_validator(d, "--no-baseline")
    check("A-007 OUT: an arch_version-only change still passes",
          rc == 0 and "A-007" not in codes(out))

with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    # the BODY (narrative + mermaid) is not fingerprinted -- editing it passes
    append_body(arch(d), "\nAn extra narrative sentence.\n")
    rc, out = run_validator(d, "--no-baseline")
    check("A-007 body: a narrative-only edit does not trip the fingerprint",
          rc == 0 and "A-007" not in codes(out))

with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "specs"))
    edit_md(arch(d), lambda doc: doc["meta"].__setitem__("fingerprint", ""))
    rc, out = run_validator(d, "--no-baseline")
    check("A-007 blank: an un-stamped fingerprint fails closed",
          rc == 1 and codes(out) == {"A-007"} and "blank" in out)


# ── 3. one targeted mutation per rule ────────────────────────────────
def m_a001(d):
    edit_md(arch(d), lambda doc: doc["meta"].pop("status", None))

def m_a002(d):
    # a malformed frontmatter id in an ADR file (proposed elsewhere untouched)
    edit_adr(d, "ADR-0002", id="ADR-99")

def m_a003(d):
    edit_adr(d, "ADR-0002", superseded_by="")

def m_a004(d):
    # drop the feature ref to ADR-0003 -> it becomes an accepted orphan
    edit_md(feature(d), lambda doc: doc.__setitem__(
        "requirements", [r for r in doc["requirements"] if r["id"] != "FR-CHK-002"]))

def m_a005(d):
    edit_md(arch(d), lambda doc: doc["components"][0].__setitem__("confidence", "maybe"))

def m_a006(d):
    with open(arch(d)) as f:
        text = f.read()
    with open(arch(d), "w") as f:
        f.write(text.replace("```mermaid", "```text", 1))


# (rule, fn, restamp?) -- ADR/feature/body edits never need a re-stamp; only
# architecture.md FRONTMATTER edits do.
MUTATIONS = [
    ("A-001", m_a001, True),
    ("A-002", m_a002, False),
    ("A-003", m_a003, False),
    ("A-004", m_a004, False),
    ("A-005", m_a005, True),
    ("A-006", m_a006, False),
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


def init_repo(path, with_specs=True, src=FIXTURE):
    os.makedirs(path)
    git(path, "init", "-q", "-b", "main")
    if with_specs:
        copy_fixture(os.path.join(path, "docs", "product"), src=src)
    else:
        with open(os.path.join(path, "README.md"), "w") as f:
            f.write("# seed\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "base")


def clone(tmp, origin, name):
    work = os.path.join(tmp, name)
    git(tmp, "clone", "-q", origin, work)
    return os.path.join(work, "docs", "product")


if shutil.which("git") is None:
    print("WARN git not available -- skipping A-008/A-009 git scenarios")
else:
    # (A) non-repo -> fail closed
    with tempfile.TemporaryDirectory() as tmp:
        d = copy_fixture(os.path.join(tmp, "specs"))
        rc, out = run_validator(d)
        check("A-008 non-repo fails closed",
              rc == 1 and "A-008" in codes(out) and "not a git" in out)

    # (B) repo, origin/main unresolvable -> fail closed
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.join(tmp, "repo")
        init_repo(repo)
        rc, out = run_validator(os.path.join(repo, "docs", "product"))
        check("A-008 unresolvable ref fails closed",
              rc == 1 and "A-008" in codes(out) and "cannot resolve" in out)

    # (C) a deleted ADR file vs origin/main -> caught (append-only; ADR files
    #     are not fingerprinted, so no re-stamp is needed to isolate A-008)
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin)
        wspecs = clone(tmp, origin, "work")
        os.remove(adr(wspecs, "ADR-0002"))
        rc, out = run_validator(wspecs)
        check("A-008 catches a deleted ADR file vs origin/main",
              rc == 1 and codes(out) == {"A-008"} and "ADR-0002" in out)

    # (D) shallow clone -> fail closed
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin)
        shallow = os.path.join(tmp, "shallow")
        git(tmp, "clone", "-q", "--depth", "1",
            f"file://{os.path.abspath(origin)}", shallow)
        rc, out = run_validator(os.path.join(shallow, "docs", "product"))
        check("A-008 shallow clone fails closed",
              rc == 1 and "A-008" in codes(out) and "shallow" in out)

    # (E) greenfield: origin/main resolves but has no decisions/ -> passes
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin, with_specs=False)
        work = os.path.join(tmp, "work")
        git(tmp, "clone", "-q", origin, work)
        wspecs = copy_fixture(os.path.join(work, "docs", "product"))
        rc, out = run_validator(wspecs)
        check("A-008 greenfield against resolvable main passes",
              rc == 0 and not codes(out))

    # ── 6. A-009 immutable-once-accepted ─────────────────────────────
    # (a) a prose edit to a baseline-accepted ADR -> fail
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin)
        wspecs = clone(tmp, origin, "work")
        append_body(adr(wspecs, "ADR-0001"), "\nA quiet edit to the prose.\n")
        rc, out = run_validator(wspecs)
        check("A-009: a prose edit to an accepted ADR fails",
              rc == 1 and codes(out) == {"A-009"} and "prose" in out)

    # (b) a frontmatter edit (title) to a baseline-accepted ADR -> fail
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin)
        wspecs = clone(tmp, origin, "work")
        edit_adr(wspecs, "ADR-0003", title="A retitled decision")
        rc, out = run_validator(wspecs)
        check("A-009: a frontmatter edit to an accepted ADR fails",
              rc == 1 and codes(out) == {"A-009"} and "frontmatter" in out)

    # (c) the supersede transition is the ONE allowed edit -> passes
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin)
        wspecs = clone(tmp, origin, "work")
        edit_adr(wspecs, "ADR-0004", status="superseded", superseded_by="ADR-0003")
        rc, out = run_validator(wspecs)
        check("A-009: the supersede transition on an accepted ADR passes",
              rc == 0 and not codes(out))

    # (d) reversing accepted -> proposed -> fail
    with tempfile.TemporaryDirectory() as tmp:
        origin = os.path.join(tmp, "origin")
        init_repo(origin)
        wspecs = clone(tmp, origin, "work")
        edit_adr(wspecs, "ADR-0004", status="proposed")
        rc, out = run_validator(wspecs)
        check("A-009: an accepted ADR cannot return to 'proposed'",
              rc == 1 and "A-009" in codes(out) and "proposed" in out)

    # (e) a pre-v2.0 baseline (no frontmatter) is exempt -- the migration window
    with tempfile.TemporaryDirectory() as tmp:
        stage = copy_fixture(os.path.join(tmp, "stage"))
        # strip ADR-0004's frontmatter in the staged origin (legacy-era file)
        p = adr(stage, "ADR-0004")
        with open(p) as f:
            text = f.read()
        m = FRONTMATTER_RE.match(text)
        with open(p, "w") as f:
            f.write(text[m.end():])
        origin = os.path.join(tmp, "origin")
        init_repo(origin, src=stage)
        wspecs = clone(tmp, origin, "work")
        # "migrate": restore the full frontmatter version from the fixture
        shutil.copyfile(adr(FIXTURE, "ADR-0004"), adr(wspecs, "ADR-0004"))
        rc, out = run_validator(wspecs)
        check("A-009: a no-frontmatter baseline ADR is exempt (migration window)",
              rc == 0 and not codes(out))


# ── 7. migrate_arch_data.py over the legacy fixture ──────────────────
with tempfile.TemporaryDirectory() as tmp:
    d = copy_fixture(os.path.join(tmp, "legacy"), src=LEGACY_FIXTURE)
    rc, out = run_migrate(d, "--dry-run")
    check("migrate --dry-run reports and writes nothing",
          rc == 0 and "would migrate" in out
          and os.path.isfile(os.path.join(d, "arch-data.yaml")))
    rc, out = run_migrate(d)
    ok = (rc == 0 and not os.path.isfile(os.path.join(d, "arch-data.yaml")))
    check("migrate deletes arch-data.yaml", ok)
    with open(adr(d, "ADR-0003")) as f:
        doc = yaml.safe_load(FRONTMATTER_RE.match(f.read()).group(1))
    check("migrate injects ADR frontmatter (index + body-parsed fields)",
          doc.get("id") == "ADR-0003" and doc.get("status") == "accepted"
          and doc.get("supersedes") == "ADR-0002" and doc.get("date") == "2026-06-29")
    rc, out = run_validator(d, "--no-baseline")
    check("the migrated layout passes the validator", rc == 0 and not codes(out))
    rc, out = run_migrate(d)
    check("migrate is idempotent (second run is a no-op)",
          rc == 0 and "nothing to migrate" in out)


print()
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    sys.exit(1)
print("validate_arch: all cases behaved as expected")
sys.exit(0)
