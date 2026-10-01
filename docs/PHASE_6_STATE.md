# Phase 6 State

## Snapshot

- Last reviewed: 2026-10-01
- Current phase: Phase 6 runtime hardening is underway in small, reviewable steps
- Current focus: runtime boundary hardening, canonical artifact manifests, traceable execution history, persistence hardening, and security polish with release gates

## What is already true

- workflow templates are in place
- recurring workflow schedule dispatch is working
- runtime history, checkpoints, provenance, and durable memory are already wired in
- runtime trace now joins runtime events, provenance, memory snapshots, tasks, steps, artifacts, and audit summaries into one inspection surface
- shell policy parsing rejects malformed commands safely and blocks basic shell control operators before the runner
- task execution now goes through a sandbox helper with cwd isolation, restricted env, explicit resource limits, and a bubblewrap-backed prototype when available
- writer-side artifact generation now emits canonical artifact manifests for python, shell, browser, and workflow outputs
- the runtime/CLI/docs surfaces now include artifact cleanup helpers and trace navigation for incident review
- the persistence boundary is documented in code and exposes both `/persistence/layers` and `/persistence/schema`
- the schema/versioning strategy and Postgres migration path for durable state are documented in code and in `docs/PHASE_6D_PERSISTENCE_HARDENING.md`
- security controls expose `/security/controls` with trust levels, approval triggers, and operational budgets
- runtime API requests are capped by a hard max-step budget before the loop starts
- release-gate smoke coverage now includes policy regression, schedule dispatch, runtime resume, artifact manifests, provenance fetch, and audit-aware trace assertions
- the Phase 6 operational runbook exists in `docs/PHASE_6_OPERATIONAL_RUNBOOK.md`

## Current blockers

- tasks still need stronger filesystem confinement guarantees beyond the current best-effort sandbox fallback
- artifact retention is still local-volume based, although canonical manifests and cleanup jobs are now in place
- observability is still centered on SQLite runtime events and provenance views rather than a stronger external audit pipeline
- durable state still lives in SQLite, so the Postgres backend swap path still needs runtime exercise
- security controls still need a final pass through the release-gate suite in CI or pre-release checks
- the remaining open Phase 6 docs/bootstrap PR (#16) still needs a fresh review or rebase before it can be closed out cleanly

## Open PRs noted in this snapshot

- PR #16 (`fix: sync settings bootstrap and docs`) is still open and GitHub currently reports `mergeable: false`
- PR #30 (`docs: refresh Phase 6 state snapshot`) is the current docs-sync PR for this snapshot

## Recommended next step

Reconcile PR #16 against current main, then run the release-gate smoke suite and tighten any remaining boundary gaps that show up in runtime trace, policy, schedule-dispatch, or persistence snapshot smoke tests.
