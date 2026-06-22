# Phase 6 State

## Snapshot

- Last reviewed: 2026-06-22
- Current phase: Phase 5 is complete; Phase 6 is next but not ready yet
- Current focus: Phase 6 runtime hardening in small, reviewable steps

## What is already true

- workflow templates are in place
- recurring workflow schedule dispatch is working
- runtime history, checkpoints, provenance, and durable memory are already wired in
- the repo currently has two open draft PRs for small follow-up work

## Current blockers

- tasks still execute through local subprocesses in the shared backend container
- there is no per-task sandbox boundary such as seccomp/AppArmor
- shell parsing can still fail on malformed quoted commands unless the policy layer handles them defensively
- artifact retention is still local-volume based
- observability is still mostly SQLite runtime events and provenance views

## Open PRs noted in this snapshot

- #12 docs: note one-shot workflow schedule completion
- #13 harden shell policy parsing for malformed commands

## Recommended next step

Review and land the shell policy hardening work, then continue with sandbox boundary and audit/logging hardening.
