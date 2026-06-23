# Phase 6 State

## Snapshot

- Last reviewed: 2026-06-23
- Current phase: Phase 6 runtime hardening is underway in small, reviewable steps
- Current focus: runtime boundary hardening with sandboxed task execution, canonical artifact manifests, and traceable execution history

## What is already true

- workflow templates are in place
- recurring workflow schedule dispatch is working
- runtime history, checkpoints, provenance, and durable memory are already wired in
- runtime trace now joins runtime events, provenance, memory snapshots, tasks, steps, and artifacts into one inspection surface
- shell policy parsing rejects malformed commands safely and now blocks basic shell control operators before the runner
- task execution now goes through a sandbox helper with cwd isolation, restricted env, explicit resource limits, and a bubblewrap-backed prototype when available
- writer-side artifact generation now emits canonical artifact manifests for python, shell, browser, and workflow outputs
- the runtime/CLI/docs surfaces now include artifact cleanup helpers and trace navigation for incident review
- the docs sync and shell hardening PRs (#15 and #13) are merged
- the current docs snapshot should match the codebase

## Current blockers

- tasks still need stronger filesystem confinement guarantees beyond the current best-effort sandbox fallback
- artifact retention is still local-volume based, although canonical manifests and cleanup jobs are now in place
- observability is still mostly SQLite runtime events and provenance views rather than a stronger audit pipeline

## Open PRs noted in this snapshot

- #19 — draft Phase 6B/6C observability and artifact-lifecycle work

## Recommended next step

Exercise the runtime trace and artifact manifest path on shell/python/workflow tasks, then tighten any remaining boundary gaps that show up in smoke tests.
