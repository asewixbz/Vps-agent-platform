from __future__ import annotations

from app.persistence_layers import get_persistence_boundary_map


def test_persistence_boundary_map_separates_local_and_durable_state() -> None:
    boundary = get_persistence_boundary_map()

    assert boundary["schema_version"] == 1
    assert "local_state" in boundary["layers"]
    assert "durable_state" in boundary["layers"]

    local_state = boundary["layers"]["local_state"]
    durable_state = boundary["layers"]["durable_state"]

    assert "sandbox workdirs" in local_state["examples"]
    assert "task state" in durable_state["examples"]
    assert "runtime events" in durable_state["examples"]
    assert "memory graph" in durable_state["examples"]
    assert "schedules" in durable_state["examples"]
    assert "audit logs" in durable_state["examples"]

    durable_layer_names = {layer["name"] for layer in durable_state["layers"]}
    assert durable_layer_names == {
        "task_state",
        "runtime_history",
        "memory_graph",
        "workflow_schedules",
        "workflow_templates",
        "schema_metadata",
    }

    durable_tables = set(boundary["durable_table_candidates"])
    assert {
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
    }.issubset(durable_tables)

    path_names = [step["name"] for step in boundary["postgres_migration_path"]]
    assert path_names == [
        "introduce persistence adapter boundary",
        "mirror durable tables in Postgres",
        "backfill durable state",
        "flip reads and writes by configuration",
        "retire SQLite only after parity",
    ]
