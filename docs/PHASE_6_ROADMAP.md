# Phase 6 roadmap

- **Goal:** harden execution so the platform is safer and more production-ready.
- **Current branch focus:** `phase6-runtime-boundary-hardening`
- **Completed in this step:** shell policy parsing now rejects malformed shell commands and the task runner uses a sandbox helper instead of plain shared-container subprocesses.
- **Near-term roadmap:**
  1. Expand the sandbox prototype with the smallest additional boundary that is still easy to test.
  2. Improve artifact retention/lifecycle handling beyond local-volume storage.
  3. Expand observability into a stronger audit trail for runtime and policy decisions.
  4. Reduce the remaining shared-container execution assumptions where feasible.
  5. Keep the hardening changes small, reviewable, and covered by tests.
- **Current priority:** make one safe hardening change at a time.
- **Owner:** asewiwarlock@duck.com
# Phase 6 Roadmap

## Goal

Make execution safer and more production-ready without losing the control-plane-first shape of the platform.

## Current blockers

- execution still needs stronger filesystem confinement guarantees in the sandbox fallback path
- artifact retention is still local-volume based and does not yet have a production lifecycle policy
- observability is still centered on SQLite runtime events and provenance views rather than a stronger audit pipeline

## Recommended order of work

1. Keep the shell policy regression tests in place.
2. Exercise and harden the sandbox prototype.
3. Add stronger observability and audit logging around runtime execution.
4. Clarify artifact retention and lifecycle behavior.
5. Plan any storage migration only when the hardening path needs it.

## Working rule

Keep Phase 6 changes small, reviewable, and easy to verify. Prefer narrow hardening steps over broad refactors.
