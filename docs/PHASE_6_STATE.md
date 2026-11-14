# Phase 6 State

## Snapshot

- Last reviewed: 2026-11-14
- Current phase: Phase 6 runtime hardening is underway in small, reviewable steps
- Current focus: consolidate overlapping docs/test branches, then keep runtime boundary hardening, canonical artifact manifests, traceable execution history, persistence hardening, and security polish moving with release gates

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
- the active docs cleanup baseline is captured in the roadmap/state sync branch; PR #107 and PR #109 remain part of the older cleanup stream, and PR #108 remains the sandbox fallback test branch

## Current blockers

- tasks still need stronger filesystem confinement guarantees beyond the current best-effort sandbox fallback
- artifact retention is still local-volume based, although canonical manifests and cleanup jobs are now in place
- observability is still centered on SQLite runtime events and provenance views rather than a stronger external audit pipeline
- durable state still lives in SQLite, so the Postgres backend swap path still needs runtime exercise
- security controls still need a final pass through the release-gate suite in CI or pre-release checks
- the overlapping docs/test branch set still needs consolidation around the active roadmap/state sync baseline before the next smoke-suite pass

## Open PRs noted in this snapshot

- the active docs cleanup baseline is the roadmap/state sync branch; PR #107 and PR #109 remain part of the older cleanup stream, and PR #108 remains the sandbox fallback test branch
- older overlapping Phase 6 docs/test drafts can stay open until the baseline is merged and the next smoke pass is complete

## Recommended next step

Merge the active docs cleanup PRs, then rerun the release-gate smoke suite from the consolidated baseline.
