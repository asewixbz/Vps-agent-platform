# Phase 6 Roadmap

## Goal

Make execution safer and more production-ready without losing the control-plane-first shape of the platform.

## Current blockers

- execution still happens through local subprocesses in the shared backend container
- there is no seccomp/AppArmor profile or equivalent per-task sandbox boundary
- shell execution is still guarded mainly by an allowlist and heuristic policy checks
- artifact retention is still local-volume based and does not yet have a production lifecycle policy
- observability is still centered on SQLite runtime events and provenance views rather than a stronger audit pipeline

## Recommended order of work

1. Harden shell policy parsing and keep a regression test for malformed commands.
2. Define and prototype a per-task sandbox boundary.
3. Add stronger observability and audit logging around runtime execution.
4. Clarify artifact retention and lifecycle behavior.
5. Plan any storage migration only when the hardening path needs it.

## Working rule

Keep Phase 6 changes small, reviewable, and easy to verify. Prefer narrow hardening steps over broad refactors.
