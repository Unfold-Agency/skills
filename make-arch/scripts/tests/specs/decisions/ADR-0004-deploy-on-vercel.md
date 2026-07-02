---
id: ADR-0004
title: "Deploy the storefront on Vercel"
status: accepted
date: "2026-06-29"
scope: project
confidence: assumption
supersedes: ""
superseded_by: ""
governs: []
---

# ADR-0004 -- Deploy the storefront on Vercel

## Context
The storefront is Next.js; the team has no stated hosting constraint.

## Decision
Deploy on Vercel until a constraint says otherwise.

## Consequences
- Zero-config Next.js deploys; vendor coupling to Vercel's runtime.

## Rejected alternatives
- **Self-managed containers** -- more control, more ops burden than the
  project justifies today.
