# Amend & Changelog (brownfield)

How to change a spec that already exists. The prime directive: **diff, don't
rewrite.** Regenerating from scratch destroys ID stability, the content versions,
and every downstream pin. Amend mode touches only what the change touches, and
records the delta in `CHANGELOG.md`.

Every change is the same shape: **a branch -> the Skill edits the affected
doc(s) + writes a structured CHANGELOG entry -> a PR -> merge.** The PR diff is the
reviewable change proposal; merge applies it; **git history is the archive.** There
is no `archive/`/`changes/` folder.

## 1. Intake

Read the existing overview + the affected feature(s) + the change trigger (a
client request, an escalation, a UAT issue, a discovery). If the trigger names
material you don't have (the meeting where it was decided, a thread), gather it
within a named scope first (see `kickoff.md` §1). If you can't pin the change to
specific IDs, you don't understand it well enough to classify yet.

## 2. Classify the change

| Class | Test | Effect |
|---|---|---|
| **Trivial** | Typo / wording, no ID's *meaning* changes (the fingerprint is unchanged) | The `--trivial` lane: record it in the CHANGELOG, no re-derive round-trip. |
| **Minor** | Additive or clarifying: a new requirement within scope, a question answered, wording tightened without changing meaning | Edit in place; CHANGELOG `minor`; re-derive + reconcile. |
| **Major** | The meaning of an existing requirement, goal, or scope item changes; anything cut; a new feature | Edit in place; CHANGELOG `major`; re-derive + reconcile; refactor issues for affected merged work. |

Borderline -> classify up (prefer major). Reclassifying down later is cheap;
discovering at build time that a "minor" edit rewrote a contract is not.

**The `--trivial` lane (resolves the "edits go underground" risk).** A typo fix
shouldn't force a full version churn, or people stop running the skill for small
edits. So: make the edit, re-derive, and confirm the fingerprint is **unchanged**
(it should be -- you only touched OUT content or pure prose). If the fingerprint
*did* change, the edit altered meaning -- it is not trivial; reclassify to minor or
major. The validator's fingerprint gate (S-006) is what makes this lane safe: it
will not let a meaning change masquerade as trivial.

## 3. Apply the diff

- **Never delete or renumber an ID.** A cut or replaced requirement becomes
  `status: superseded` (its replacement gets a NEW id, with a note pointing back)
  or `status: deferred`. The no-vanishing check (S-005) enforces this against
  `origin/main`.
- Edit only the affected sections of the affected markdown.
- **New decision needed?** Don't bake HOW into the feature spec -- leave or add a
  `governed_by` placeholder and run `/make-arch` (it adds the ADR). Reversing a
  decision is a *new* superseding ADR, never an edit to the old one.
- **New feature?** Add `features/<slug>.md` and a Feature Index row with a unique
  prefix.
- Adding a requirement that another feature will depend on is a **seam** -- give it
  one home feature; dependents reference it by id. Note the seam in the
  CHANGELOG's cross-feature impact.

## 4. Write the CHANGELOG entry

One structured entry per change (newest first), per `assets/changelog-entry-template.md`:
the trigger, the why, and the exact **Added / Modified / Removed** id lists, plus
cross-feature impact and any ADR added/superseded. **make-issues reads these id
lists to drive its reconcile**, so they must be accurate -- this entry is the
machine-readable delta, not flavor text.

## 5. Re-derive, stamp, validate

1. Re-derive the affected `*-data.yaml`.
2. `python scripts/stamp_fingerprint.py docs/specs` -- re-stamps changed features
   and rewrites their content versions into the overview Feature Index.
3. Validate against the baseline (this is **not** optional in amend mode -- it is
   what enforces no-vanishing):
   ```
   python scripts/validate_spec.py docs/specs            # baseline: origin/main
   ```
   If the validator reports a vanished id, you deleted or renamed instead of
   superseding -- fix it. If it reports a shallow clone or an unresolvable
   `origin/main`, **fix the git state** (`git fetch --unshallow` / fetch the ref);
   do not reach for `--no-baseline` to silence it -- that flag is only for the
   greenfield first commit.

## 6. Propagation report

The Skill prepares propagation; humans execute it. Output:

- **Changed IDs**, old -> new meaning, one line each (mirrors the CHANGELOG).
- **Downstream owed:** the change reaches GitHub through `/make-issues`, which
  reads the CHANGELOG delta and reconciles -- creating, updating, staling, or
  opening **refactor** issues for affected merged work, all behind its drift gate.
  Surface that `/make-issues` is the next step.
- **Cross-feature impact:** which other features depend on a changed id, and any
  seam touched.
- For a **minor** change the report is lighter: added/changed ids, and that
  unaffected features and their issues are untouched.
