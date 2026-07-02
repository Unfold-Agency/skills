<!--
═══════════════════════════════════════════════════════════════════
CHANGELOG ENTRY TEMPLATE -- docs/product/CHANGELOG.md   (make-spec)

docs/product/CHANGELOG.md is a Keep a Changelog ledger of every spec
change. ONE STRUCTURED ENTRY PER CHANGE. The entry IS the delta: which
IDs were added, modified, or removed, why, and the cross-feature impact.
make-issues reads this ledger to drive its reconcile, so the ADDED /
MODIFIED / REMOVED id lists must be accurate.

Git history is the archive and the PR diff is the change proposal -- the
CHANGELOG is the human-readable, machine-parseable index over that
history, not a second copy of it. There is no archive/ folder.

The file starts with this header (once):

    # Changelog
    All notable spec changes. Format: Keep a Changelog; ids are the
    spec's stable requirement/goal/ADR ids. Newest first.

Then one section per change, newest first, using the block below.
Conventional Commit + GitMoji on the commit; the human reason here.
═══════════════════════════════════════════════════════════════════
-->

## [<project_version or date>] -- <YYYY-MM-DD> -- <class: kickoff | minor | major | trivial>

**Trigger.** <!-- what prompted this: client request, escalation, UAT
issue, discovery, decision. One line. -->

**Why.** <!-- the reasoning, plainly. One short paragraph. -->

### Added
- `FR-CHK-007` -- [one line] (feature: checkout)

### Modified
- `FR-CHK-002` -- [old meaning] -> [new meaning] (feature: checkout)

### Removed
- `FR-CHK-009` -- superseded by `FR-CHK-011` (never deleted; status: superseded)

**Cross-feature impact.** <!-- features that depend on a changed id via
depends_on, and any seam (shared requirement) touched. "none" if none. -->

**Decisions.** <!-- ADR-NNNN added/superseded by this change, or none. -->
