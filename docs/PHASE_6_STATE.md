# Phase 6 state

- **Status:** in progress
- **Last update:** shell policy parsing was hardened so malformed commands are rejected safely.
- **Branch:** `harden-shell-policy-quote-check`
- **What changed in the current step:**
  - `backend/app/policy.py` now catches shell parsing failures and returns a safe denial reason.
  - The change matches the existing regression test for unterminated shell quoting.
- **What is still blocking Phase 6 readiness:**
  - execution still happens through local subprocesses inside the shared backend container
  - there is no per-task seccomp/AppArmor-style sandbox boundary yet
  - artifact retention is still local-volume based
  - observability is still centered on SQLite runtime events and provenance views instead of a stronger audit pipeline
- **Next recommended step:** choose the next smallest hardening improvement that can be tested in isolation.
- **Owner:** asewiwarlock@duck.com
