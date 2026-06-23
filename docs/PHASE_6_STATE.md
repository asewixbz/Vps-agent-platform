# Phase 6 State

## Snapshot

- Last reviewed: 2026-06-22
- Current phase: Phase 6 runtime hardening is underway in small, reviewable steps
- Current focus: runtime boundary hardening with sandboxed task execution and shell policy tightening

## What is already true

- workflow templates are in place
- recurring workflow schedule dispatch is working
- runtime history, checkpoints, provenance, and durable memory are already wired in
- shell policy parsing rejects malformed commands safely and now blocks basic shell control operators before the runner
- task execution now goes through a sandbox helper with cwd isolation, restricted env, explicit resource limits, and a bubblewrap-backed prototype when available
- writer-side artifact generation now emits canonical artifact manifests for python, shell, browser, and workflow outputs
- the docs sync and shell hardening PRs (#15 and #13) are merged
- the current docs snapshot should match the codebase

## Current blockers

- tasks still need stronger filesystem confinement guarantees beyond the current best-effort sandbox fallback
- artifact retention is still local-volume based
- observability is still mostly SQLite runtime events and provenance views

## Open PRs noted in this snapshot

- none

## Recommended next step

Exercise the sandbox prototype on shell/python tasks and then tighten any remaining boundary gaps that show up in smoke tests.
