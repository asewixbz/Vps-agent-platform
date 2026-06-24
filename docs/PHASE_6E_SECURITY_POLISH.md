# Phase 6E — Security polish and operational controls

## Goal

Phase 6 already has the audit and persistence foundations. This layer tightens execution policy and adds pre-release controls so risky actions fail fast instead of drifting into production behavior.

## 5.1 Stronger approval gates

### What is now defined

- trust levels are now explicit: `unreviewed`, `limited`, `trusted`, `privileged`
- approval triggers are treated separately from simple trust checks
- explicit deny vs allow reasoning is carried in policy decisions
- shell approval triggers include risky patterns such as `python -c`, `pip install`, `git push`, `curl`, `wget`, `ssh`, `scp`, `kubectl`, and `terraform`
- browser execution requires approval for external URLs
- tool- and kind-specific policy overrides can be supplied in `tool_policy_overrides_json` or in tool metadata via `policy_overrides`

### Ready criteria

- a risky action can be traced to a specific approval trigger
- a policy response clearly says whether the action was allowed, denied, or paused for approval
- per-tool overrides can raise or lower policy strictness without changing domain logic

## 5.2 Operational guardrails

### What is now defined

- timeout budgets are enforced before execution starts
- runtime step limits are enforced before the loop begins
- per-tool timeout overrides can tighten the budget for a specific tool
- fail-fast behavior blocks tasks that exceed budget or policy instead of silently running too long
- guardrails are exposed through `/security/controls`
- runtime traces now carry audit summaries so blocked and approved behavior is easier to inspect

### Ready criteria

- execution requests that exceed timeout or step budgets fail early with a clear reason
- the runtime loop never runs past the configured step ceiling
- policy overrides can be inspected without reading code
- runtime traces clearly surface the relevant audit context

## 5.3 Smoke tests / release gates

### Minimal pre-release coverage

- policy regression
- schedule dispatch
- runtime resume
- artifact manifest
- provenance fetch
- audit-aware trace checks

### Current smoke set

- `backend/tests/test_release_gates.py`
  - verifies safe shell allow, approval-triggered shell behavior, and hard deny cases
  - checks timeout and max-step guardrails
  - exercises schedule dispatch end to end
  - exercises runtime resume, canonical artifact manifests, runtime trace/provenance fetch, and audit summary assertions
- `docs/PHASE_6_OPERATIONAL_RUNBOOK.md`
  - documents the fast path for diagnosing blocked tasks, runtime runs, security controls, and persistence snapshots

## Status

Phase 6E is ready when the security controls are visible, the guardrails fail fast, and the smoke suite can be used as a release gate before merging the next runtime change.
