# Phase 6 roadmap

- **Goal:** harden execution so the platform is safer and more production-ready.
- **Current branch focus:** `harden-shell-policy-quote-check`
- **Completed in this step:** shell policy parsing now rejects malformed shell commands instead of letting parsing errors escape.
- **Near-term roadmap:**
  1. Add stronger per-task sandbox boundaries around local execution.
  2. Improve artifact retention/lifecycle handling beyond local-volume storage.
  3. Expand observability into a stronger audit trail for runtime and policy decisions.
  4. Reduce the remaining shared-container execution assumptions where feasible.
  5. Keep the hardening changes small, reviewable, and covered by tests.
- **Current priority:** make one safe hardening change at a time.
- **Owner:** asewiwarlock@duck.com
