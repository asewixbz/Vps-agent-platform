# Phase 6 roadmap

## Goal

Harden execution so the platform is safer and more production-ready without losing the control-plane-first shape of the system.

## Current state

- shell policy parsing rejects malformed shell commands and blocks obvious control operators
- the runner uses a sandbox helper with cwd isolation, restricted env, and explicit resource limits
- browser execution is behind a feature flag and still requires approval for external URLs
- persistence now has an explicit boundary map and schema-metadata bootstrap path
- observability now carries runtime audit summaries in the trace surface
- release-gate smoke coverage includes policy, schedules, runtime resume, artifact manifests, provenance, and audit-aware trace checks
- the Phase 6 docs/state/roadmap notes are being consolidated around the current branch-cleanup issue

## Near-term roadmap

1. Exercise and harden the sandbox fallback path.
2. Keep the persistence migration scaffolding in place and validate the SQLite -> Postgres path when needed.
3. Continue improving runtime audit and trace visibility for blocked and approved runs.
4. Keep the release-gate smoke suite green while consolidating overlapping Phase 6 docs branches.
5. Keep documentation and runbooks aligned with the code.
6. Track the branch-cleanup consolidation work in issue #49 until the draft PR set is narrowed down.

## Working rule

Keep Phase 6 changes small, reviewable, and easy to verify. Prefer narrow hardening steps over broad refactors.

## Operational docs

- `docs/PHASE_6_OPERATIONAL_RUNBOOK.md`
- `docs/PHASE_6_STATE.md`
- `docs/PHASE_6D_PERSISTENCE_HARDENING.md`
- `docs/PHASE_6E_SECURITY_POLISH.md`
