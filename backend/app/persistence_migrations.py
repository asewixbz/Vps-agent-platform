from __future__ import annotations

import json
from typing import Any

from .persistence_layers import (
    PERSISTENCE_SCHEMA_METADATA_TABLE,
    PERSISTENCE_SCHEMA_NAME,
    PERSISTENCE_SCHEMA_VERSION,
    get_persistence_boundary_map,
    get_schema_metadata_contract,
    get_schema_version_strategy,
)
from .settings import Settings
from .store import connect, utc_now


def _schema_metadata_payload() -> dict[str, Any]:
    boundary = get_persistence_boundary_map()
    return {
        "schema_name": PERSISTENCE_SCHEMA_NAME,
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "metadata_table": PERSISTENCE_SCHEMA_METADATA_TABLE,
        "versioning_model": get_schema_metadata_contract()["versioning_model"],
        "migration_strategy": get_schema_version_strategy()["strategy"],
        "durable_table_candidates": boundary["durable_table_candidates"],
        "migration_path": [step["name"] for step in boundary["postgres_migration_path"]],
    }


def _schema_metadata_row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    raw_metadata = data.pop("metadata_json", "{}")
    try:
        data["metadata"] = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
    except json.JSONDecodeError:
        data["metadata"] = {}
    return data


def ensure_persistence_schema(settings: Settings) -> dict[str, Any]:
    conn = connect(settings.db_path)
    try:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {PERSISTENCE_SCHEMA_METADATA_TABLE} (
                schema_name TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{{}}',
                applied_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        now = utc_now()
        metadata = _schema_metadata_payload()
        conn.execute(
            f"""
            INSERT INTO {PERSISTENCE_SCHEMA_METADATA_TABLE} (
                schema_name,
                schema_version,
                metadata_json,
                applied_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(schema_name) DO UPDATE SET
                schema_version = excluded.schema_version,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                PERSISTENCE_SCHEMA_NAME,
                PERSISTENCE_SCHEMA_VERSION,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )
        conn.commit()
        return get_schema_metadata(settings) or {}
    finally:
        conn.close()


def get_schema_metadata(settings: Settings, *, schema_name: str = PERSISTENCE_SCHEMA_NAME) -> dict[str, Any] | None:
    conn = connect(settings.db_path)
    try:
        row = conn.execute(
            f"SELECT * FROM {PERSISTENCE_SCHEMA_METADATA_TABLE} WHERE schema_name = ?",
            (schema_name,),
        ).fetchone()
        return _schema_metadata_row_to_dict(row)
    finally:
        conn.close()


def list_schema_metadata(settings: Settings) -> list[dict[str, Any]]:
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(f"SELECT * FROM {PERSISTENCE_SCHEMA_METADATA_TABLE} ORDER BY schema_name ASC").fetchall()
        return [item for row in rows if (item := _schema_metadata_row_to_dict(row)) is not None]
    finally:
        conn.close()


def get_persistence_schema_snapshot(settings: Settings) -> dict[str, Any]:
    current = get_schema_metadata(settings)
    return {
        "schema_name": PERSISTENCE_SCHEMA_NAME,
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "present": current is not None,
        "current": current,
        "schema_metadata_contract": get_schema_metadata_contract(),
        "schema_version_strategy": get_schema_version_strategy(),
        "boundary": get_persistence_boundary_map(),
    }
