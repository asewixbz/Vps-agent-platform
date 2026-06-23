from __future__ import annotations

from typing import Any

PERSISTENCE_SCHEMA_VERSION = 1


def get_persistence_layers() -> dict[str, Any]:
    return {
        "local_state": {
            "description": "Worker-local and run-local state that can be recreated from durable records or re-derived on the next run.",
            "scope": "ephemeral",
            "examples": [
                "sandbox workdirs",
                "temporary files created during task execution",
                "browser scratch artifacts",
                "staging files before canonical manifest publication",
            ],
            "boundary": [
                "safe to delete after run completion or retention cleanup",
                "does not need cross-process transactional guarantees",
            ],
        },
        "durable_state": {
            "description": "State that must survive process restarts and be reconstructable for audits, retries, and future workflow steps.",
            "scope": "durable",
            "examples": [
                "task state",
                "runtime events",
                "memory graph",
                "schedules",
                "audit logs",
            ],
            "layers": [
                {
                    "name": "task_state",
                    "tables": ["tools", "tasks"],
                    "notes": "Task registry, approvals, execution state, and results are durable control-plane state.",
                },
                {
                    "name": "runtime_history",
                    "tables": ["runtime_runs", "runtime_run_events"],
                    "notes": "Runtime execution history and audit-style events must remain durable and queryable.",
                },
                {
                    "name": "memory_graph",
                    "tables": ["memory_records", "memory_record_artifacts", "memory_links"],
                    "notes": "Long-lived memory and graph links must remain durable to support provenance.",
                },
                {
                    "name": "workflow_schedules",
                    "tables": ["workflow_schedules"],
                    "notes": "Recurring schedule definitions and dispatch state are durable workflow data.",
                },
                {
                    "name": "workflow_templates",
                    "tables": ["workflow_templates"],
                    "notes": "Custom workflow templates are durable because they change workflow behavior across runs.",
                },
                {
                    "name": "schema_metadata",
                    "tables": ["schema_metadata"],
                    "notes": "Version metadata must be durable so future migrations can be coordinated safely.",
                },
            ],
        },
    }


def get_schema_version_strategy() -> dict[str, Any]:
    return {
        "current_schema_version": PERSISTENCE_SCHEMA_VERSION,
        "strategy": "additive versioned migrations with compatibility-first readers",
        "rules": [
            "new fields should be added without breaking existing readers",
            "domain services should continue to call store helpers instead of SQL inline",
            "schema changes should be versioned explicitly before any backend swap",
            "read paths should tolerate old rows until backfill is complete",
        ],
    }


def get_durable_table_candidates() -> list[str]:
    return [
        "tools",
        "tasks",
        "runtime_runs",
        "runtime_run_events",
        "memory_records",
        "memory_record_artifacts",
        "memory_links",
        "workflow_schedules",
        "workflow_templates",
        "schema_metadata",
    ]


def get_postgres_migration_path() -> list[dict[str, Any]]:
    return [
        {
            "step": 1,
            "name": "introduce persistence adapter boundary",
            "goal": "Keep domain logic calling store/service helpers while the backend storage implementation can be swapped.",
        },
        {
            "step": 2,
            "name": "mirror durable tables in Postgres",
            "goal": "Create the Postgres schema for durable tables while preserving the current SQLite tables during the transition.",
            "tables": get_durable_table_candidates(),
        },
        {
            "step": 3,
            "name": "backfill durable state",
            "goal": "Move tasks, runtime history, memory graph, schedules, and template rows into the new durable backend without changing callers.",
        },
        {
            "step": 4,
            "name": "flip reads and writes by configuration",
            "goal": "Switch the repository layer to Postgres while keeping local workdirs and artifact staging on the worker filesystem.",
        },
        {
            "step": 5,
            "name": "retire SQLite only after parity",
            "goal": "Remove SQLite from durable state once parity, migration verification, and operational checks are complete.",
        },
    ]


def get_persistence_boundary_map() -> dict[str, Any]:
    layers = get_persistence_layers()
    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "layers": layers,
        "schema_version_strategy": get_schema_version_strategy(),
        "durable_table_candidates": get_durable_table_candidates(),
        "postgres_migration_path": get_postgres_migration_path(),
    }
