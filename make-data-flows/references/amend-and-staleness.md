# Amend and staleness -- update only what moved

A feature that already has a flows region. The prime directive matches the rest of the
pipeline: **diff, don't rewrite, and never overwork a minor edit.**

## The staleness oracle: feature_version

make-spec stamps each feature with a `feature_version` -- the first 12 hex of a hash
over the feature's **contract** (descriptions, acceptance criteria, `governed_by`,
`depends_on`, `interface`, `supports`, identity). Advisory fields (priority,
architecture_hints, related_files, notes) are OUT of that hash, so a cosmetic edit does
not move the version.

The flows region stamps the `feature_version` it was generated from. On the next run,
`flow_status.py` compares:

```
region stamp feature_version == live feature_version  -> SKIP        (nothing meaningful changed)
region stamp feature_version != live feature_version  -> REGENERATE  (the contract moved)
no region                                              -> CREATE
--force                                                -> REGENERATE anyway
```

This is exactly why `--feature` targeting "avoids overworking minor updates": retitling
a requirement or bumping a priority never moves `feature_version`, so the feature stays
SKIP. Only a change of meaning regenerates.

## Regenerating safely

1. Run `flow_status.py` to see which features are REGENERATE (and, on a scoped run,
   which are stale but out of scope -- reported, not written).
2. Re-model the affected feature(s) from the current requirements (fan out a worker per
   feature). Reuse still-accurate flows; change only what the requirement change
   affected. Keep flow ids stable where the flow still means the same thing.
3. `embed_flows.py` replaces the region in place. It never duplicates the region, and it
   is byte-identical when nothing but the timestamp would change (so a re-run of an
   already-current feature makes no diff).
4. `validate_flows.py` confirms the result; DF-005 goes quiet once the stamp matches the
   live version again.

## What never happens

- The frontmatter is never touched (the fingerprint cannot move).
- Human narrative outside the region is never altered (defensive asserts abort the edit
  if the markers were moved).
- A stale flow never blocks a build -- it warns (DF-005). Flows are advisory.
