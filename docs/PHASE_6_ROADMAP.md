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
- the current docs/test baseline is consolidated around issue #49, PR #532, the follow-up docs refreshes in PRs #531 and #529, and the adjacent sandbox fallback hardening in PR #530

## Near-term roadmap

1. Consolidate the overlapping Phase 6 docs/test branches and keep the baseline PR set aligned before the next smoke-suite pass.
2. Exercise and harden the sandbox fallback path.
3. Keep the persistence migration scaffolding in place and validate the SQLite -> Postgres path when needed.
4. Continue improving runtime audit and trace visibility for blocked and approved runs.
5. Keep the release-gate smoke suite green while making small hardening changes.
6. Keep documentation and runbooks aligned with the code.
