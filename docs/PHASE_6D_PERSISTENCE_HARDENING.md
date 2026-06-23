# Phase 6D — Persistence hardening

## Goal

SQLite is fine as the foundation, but Phase 6 now needs a clear persistence boundary and a migration path that can handle scale and lock contention without rewriting domain logic.

## Persistence boundary

### Local state

Local state stays on the worker filesystem and can be recreated or cleaned up without breaking the system.

Examples:

- sandbox workdirs
- temporary files created during task execution
- browser scratch artifacts
- staging files before canonical artifact manifest publication

Rules:

- safe to delete after run completion or retention cleanup
- not required for long-term reconstruction
- does not need cross-process transactional guarantees

### Durable state

Durable state must survive restarts and be queryable for audit, recovery, and future workflow steps.

Examples:

- task state
- runtime events
- memory graph
- schedules
- audit logs

Current durable layers:

- `tools`, `tasks` → task state and control-plane execution data
- `runtime_runs`, `runtime_run_events` → runtime history and audit-style events
- `memory_records`, `memory_record_artifacts`, `memory_links` → memory graph and artifact refs
- `workflow_schedules` → recurring schedule definitions and dispatch state
- `workflow_templates` → custom workflow definitions
- `schema_metadata` → schema versioning metadata

## Schema / versioning strategy

Current strategy:

- additive versioned migrations
- compatibility-first readers
- domain code calls store/service helpers instead of raw SQL
- old rows remain readable until backfill is complete

Current schema version:

- `1`

## SQLite → Postgres migration path

The migration path is staged so the domain layer does not need to change.

1. introduce a persistence adapter boundary
2. mirror durable tables in Postgres
3. backfill durable state
4. flip reads and writes by configuration
5. retire SQLite only after parity

### Candidate tables for the first Postgres migration wave

- `tools`
- `tasks`
- `runtime_runs`
- `runtime_run_events`
- `memory_records`
- `memory_record_artifacts`
- `memory_links`
- `workflow_schedules`
- `workflow_templates`
- `schema_metadata`

### What should stay local even after the migration

- workdirs and scratch files
- transient artifact staging
- cleanup outputs that are already represented by canonical manifests

## Ready criteria

Phase 6D is ready when:

- the persistence layers map is explicit
- durable state is clearly separated from local filesystem state
- there is a versioning strategy for schema evolution
- Postgres migration can happen without rewriting domain logic
- local scratch data remains local while durable state becomes backend-agnostic

## Implementation note

The repo now exposes the boundary map in code at `/persistence/layers` so the durable/local split can be inspected without reading implementation details.
