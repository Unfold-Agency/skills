#!/usr/bin/env python3
"""Self-contained test harness for validate_tdd.py.

Asserts the valid fixture passes (exit 0) and that a targeted mutation per
rule trips EXACTLY that rule. Because meta.fingerprint (V-015) covers the
whole file, every mutation recomputes the fingerprint so only the intended
rule fires — except the V-015 case, which leaves a deliberately wrong one.

  python scripts/tests/test_validate_tdd.py
Exit 0 = all cases behaved as expected.
"""
import copy
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import yaml  # noqa: E402
from validate_tdd import compute_fingerprint  # noqa: E402

VALIDATOR = os.path.join(SCRIPTS, "validate_tdd.py")
PASS = os.path.join(HERE, "tdd-data.pass.yaml")
PRD = os.path.join(HERE, "prd-data.fixture.yaml")
MD = os.path.join(HERE, "TDD.fixture.md")


def run(data_file, prev=None):
    cmd = [sys.executable, VALIDATOR, data_file, "--prd", PRD, "--tdd-md", MD]
    if prev:
        cmd += ["--prev", prev]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def write_tmp(doc, fix_fp=True):
    doc = copy.deepcopy(doc)
    if fix_fp:
        doc.setdefault("meta", {})["fingerprint"] = compute_fingerprint(doc)
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    with open(path, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False)
    return path


# --- mutations: each takes the base doc (deep-copied) and breaks one rule ---
def m_v001(d):
    d.pop("change_log", None)

def m_v002(d):
    d["open_questions"].append({"id": "OQ-1", "question": "bad id", "blocks": [],
                                "owner": "x", "status": "open"})

def m_v002_missing_id(d):
    d["entities"].append({"name": "Unidentified", "status": "active"})  # no id field

def m_v003(d):
    d["traceability"]["mapped"] = [r for r in d["traceability"]["mapped"]
                                   if r["requirement_id"] != "FR-002"]

def m_v004(d):
    d["decisions"][0]["derived_from"] = []

def m_v005(d):
    d["nfrs"][0]["derived_from"] = []

def m_v006(d):
    d["assumptions"][0]["owner"] = ""

def m_v007(d):
    d["entities"][0]["satisfies"] = ["FR-999"]

def m_v008(d):
    d["workflows"].append({"id": "WF-002", "name": "Refund", "trigger": "x",
                           "steps": [], "satisfies": [], "needs_diagram": True,
                           "status": "active"})
    # keep the new active capability phased so only V-008 (missing diagram) trips,
    # not V-018 (an unphased active capability)
    if d.get("implementation_phases"):
        d["implementation_phases"][0]["capabilities"].append("WF-002")

def m_v010(d):
    d["meta"]["tdd_status"] = "approved"
    d["risks"][0]["severity"] = "high"
    d["risks"][0]["status"] = "open"

def m_v011(d):
    d["meta"]["tdd_status"] = "bogus"

def m_v012(d):
    d["binding_constraints"][0]["source"] = {"type": "", "ref": "", "prd_constraint_id": ""}

def m_v013(d):
    d["integrations"][0]["bounded_by"] = ["ADR-001"]  # exists, but not a BC-

def m_v013_satisfied_by(d):
    d["traceability"]["mapped"][0]["satisfied_by"] = ["FR-001"]  # PRD id, not a capability

def m_v014(d):
    d["meta"]["system_of_record"] = "bogus"

def m_v016(d):
    d["meta"]["tdd_version"] = "0.2"  # md frontmatter still says 0.1

def m_v017(d):
    d["meta"]["prd_version"] = "0.9"  # prd fixture is locked at 1.0

def m_v018_uncovered(d):
    d["implementation_phases"][1]["capabilities"].remove("WF-001")  # active cap unphased

def m_v018_double(d):
    d["implementation_phases"][0]["capabilities"].append("WF-001")  # also in phase 2

def m_v018_cycle(d):
    d["implementation_phases"][0]["depends_on"] = [2]  # 1->2 and 2->1

def m_v018_badcap(d):
    d["implementation_phases"][0]["capabilities"].append("ENT-999")  # not a real cap

def m_v018_badnum(d):
    d["implementation_phases"].append({"number": 0, "name": "Bad", "summary": "",
                                       "delivers": "", "capabilities": [],
                                       "exit_criteria": "", "depends_on": [],
                                       "status": "active"})  # number must be >= 1


MUTATION_CASES = [
    ("V-001", m_v001), ("V-002", m_v002), ("V-002", m_v002_missing_id),
    ("V-003", m_v003), ("V-004", m_v004), ("V-005", m_v005), ("V-006", m_v006),
    ("V-007", m_v007), ("V-008", m_v008), ("V-010", m_v010), ("V-011", m_v011),
    ("V-012", m_v012), ("V-013", m_v013), ("V-013", m_v013_satisfied_by),
    ("V-014", m_v014), ("V-016", m_v016), ("V-017", m_v017),
    ("V-018", m_v018_uncovered), ("V-018", m_v018_double), ("V-018", m_v018_cycle),
    ("V-018", m_v018_badcap), ("V-018", m_v018_badnum),
]


def main():
    base = yaml.safe_load(open(PASS))
    failures = []
    tmps = []

    # 1) the valid fixture passes
    rc, out = run(PASS)
    if rc == 0:
        print("ok   PASS fixture exits 0")
    else:
        print("FAIL PASS fixture did not exit 0")
        print(out)
        failures.append("pass-fixture")

    # 2) each mutation trips exactly its rule
    for rule, mut in MUTATION_CASES:
        d = copy.deepcopy(base)
        mut(d)
        path = write_tmp(d)
        tmps.append(path)
        rc, out = run(path)
        tripped = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("[V-")]
        codes = {t.split("]")[0].lstrip("[") for t in tripped}
        if rc == 1 and codes == {rule}:
            print(f"ok   {rule}: tripped exactly {rule}")
        elif rc == 1 and rule in codes:
            print(f"WARN {rule}: tripped {sorted(codes)} (target present, extras)")
            failures.append(f"{rule}-extras:{sorted(codes)}")
        else:
            print(f"FAIL {rule}: rc={rc} codes={sorted(codes)}")
            failures.append(rule)

    # 3) V-009 — vanished ID via --prev
    prev = copy.deepcopy(base)
    prev["open_questions"].append({"id": "OQ-099", "question": "gone next version",
                                   "blocks": [], "owner": "x", "status": "open"})
    prev_path = write_tmp(prev)
    tmps.append(prev_path)
    rc, out = run(PASS, prev=prev_path)
    codes = {ln.strip().split("]")[0].lstrip("[") for ln in out.splitlines()
             if ln.strip().startswith("[V-")}
    if rc == 1 and codes == {"V-009"}:
        print("ok   V-009: tripped exactly V-009")
    else:
        print(f"FAIL V-009: rc={rc} codes={sorted(codes)}")
        failures.append("V-009")

    # 4) V-015 — wrong fingerprint, no recompute
    d = copy.deepcopy(base)
    path = write_tmp(d, fix_fp=False)
    with open(path) as f:
        bad = yaml.safe_load(f)
    bad["meta"]["fingerprint"] = "0" * 64
    with open(path, "w") as f:
        yaml.safe_dump(bad, f, sort_keys=False)
    tmps.append(path)
    rc, out = run(path)
    codes = {ln.strip().split("]")[0].lstrip("[") for ln in out.splitlines()
             if ln.strip().startswith("[V-")}
    if rc == 1 and codes == {"V-015"}:
        print("ok   V-015: tripped exactly V-015")
    else:
        print(f"FAIL V-015: rc={rc} codes={sorted(codes)}")
        failures.append("V-015")

    for p in tmps:
        try:
            os.unlink(p)
        except OSError:
            pass

    print()
    if failures:
        print(f"FAILURES: {failures}")
        sys.exit(1)
    print("all cases behaved as expected")
    sys.exit(0)


if __name__ == "__main__":
    main()
