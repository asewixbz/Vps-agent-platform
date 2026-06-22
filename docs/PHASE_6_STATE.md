# Phase 6 State

## Snapshot

- Last reviewed: 2026-06-22
- Current phase: Phase 5 is complete; Phase 6 is next but not ready yet
- Current focus: shell policy hardening branch is ready for review, then sandbox-boundary prototyping

## What is already true

- workflow templates are in place
- recurring workflow schedule dispatch is working
- runtime history, checkpoints, provenance, and durable memory are already wired in
- the shell policy branch rejects malformed commands safely and is covered by a regression test
- the repo currently has one open PR for small follow-up work

## Current blockers

- tasks still execute through local subprocesses in the shared backend container
- there is no per-task sandbox boundary such as seccomp/AppArmor
- artifact retention is still local-volume based
- observability is still mostly SQLite runtime events and provenance views

## Open PRs noted in this snapshot

- #13 harden shell policy parsing for malformed commands

## Recommended next step

Review and land the shell policy hardening work, then define the smallest sandbox-boundary prototype that can be tested in isolation.
