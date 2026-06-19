from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from .settings import Settings
from .store import connect, utc_now


def _load_json(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return default
        return parsed if isinstance(parsed, (dict, list)) else default
    return default


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    if "tags_json" in data:
        data["tags"] = _load_json(data.pop("tags_json"), [])
    if "metadata_json" in data:
        data["metadata"] = _load_json(data.pop("metadata_json"), {})
    if "artifacts_json" in data:
        data["artifacts"] = _load_json(data.pop("artifacts_json"), [])
    if "payload_json" in data:
        data["payload"] = _load_json(data.pop("payload_json"), {})
    return data


def init_memory_schema(settings: Settings) -> None:
    conn = connect(settings.db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_records (
                id TEXT PRIMARY KEY,
                memory_key TEXT UNIQUE NOT NULL,
                kind TEXT NOT NULL,
                scope_type TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                tags_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                artifacts_json TEXT NOT NULL DEFAULT '[]',
                source TEXT,
                source_ref TEXT,
                importance INTEGER NOT NULL DEFAULT 0,
                pinned INTEGER NOT NULL DEFAULT 0,
                last_accessed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_record_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_record_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_ref TEXT NOT NULL,
                label TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _serialize_record_args(
    *,
    memory_key: str,
    kind: str,
    scope_type: str,
    scope_id: str,
    title: str,
    summary: str,
    content: str,
    tags: list[str],
    metadata: dict[str, Any],
    artifacts: list[dict[str, Any]],
    source: str | None,
    source_ref: str | None,
    importance: int,
    pinned: bool,
    last_accessed_at: str | None,
) -> tuple[Any, ...]:
    now = utc_now()
    return (
        memory_key,
        kind,
        scope_type,
        scope_id,
        title,
        summary,
        content,
        json.dumps(tags),
        json.dumps(metadata),
        json.dumps(artifacts),
        source,
        source_ref,
        importance,
        1 if pinned else 0,
        last_accessed_at,
        now,
        now,
    )


def _fetch_memory_record(conn: sqlite3.Connection, *, memory_record_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT memory_records.*, (
            SELECT COUNT(1)
            FROM memory_record_artifacts
            WHERE memory_record_artifacts.memory_record_id = memory_records.id
        ) AS artifact_count
        FROM memory_records
        WHERE memory_records.id = ?
        """,
        (memory_record_id,),
    ).fetchone()
    return _row_to_dict(row)


def upsert_memory_record(
    settings: Settings,
    *,
    memory_key: str,
    kind: str,
    scope_type: str,
    scope_id: str,
    title: str,
    summary: str = "",
    content: str = "",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    source: str | None = None,
    source_ref: str | None = None,
    importance: int = 0,
    pinned: bool = False,
    last_accessed_at: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    tags_list = tags or []
    metadata_dict = metadata or {}
    artifacts_list = artifacts or []
    conn = connect(settings.db_path)
    try:
        existing = conn.execute("SELECT id, created_at FROM memory_records WHERE memory_key = ?", (memory_key,)).fetchone()
        if existing is None:
            memory_record_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO memory_records (
                    id, memory_key, kind, scope_type, scope_id, title, summary, content,
                    tags_json, metadata_json, artifacts_json, source, source_ref, importance,
                    pinned, last_accessed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_record_id,
                    *
                    _serialize_record_args(
                        memory_key=memory_key,
                        kind=kind,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        title=title,
                        summary=summary,
                        content=content,
                        tags=tags_list,
                        metadata=metadata_dict,
                        artifacts=artifacts_list,
                        source=source,
                        source_ref=source_ref,
                        importance=importance,
                        pinned=pinned,
                        last_accessed_at=last_accessed_at,
                    ),
                ),
            )
        else:
            memory_record_id = str(existing["id"])
            conn.execute(
                """
                UPDATE memory_records
                SET kind = ?,
                    scope_type = ?,
                    scope_id = ?,
                    title = ?,
                    summary = ?,
                    content = ?,
                    tags_json = ?,
                    metadata_json = ?,
                    artifacts_json = ?,
                    source = ?,
                    source_ref = ?,
                    importance = ?,
                    pinned = ?,
                    last_accessed_at = COALESCE(?, last_accessed_at),
                    updated_at = ?
                WHERE memory_key = ?
                """,
                (
                    kind,
                    scope_type,
                    scope_id,
                    title,
                    summary,
                    content,
                    json.dumps(tags_list),
                    json.dumps(metadata_dict),
                    json.dumps(artifacts_list),
                    source,
                    source_ref,
                    importance,
                    1 if pinned else 0,
                    last_accessed_at,
                    now,
                    memory_key,
                ),
            )
        conn.commit()
        record = _fetch_memory_record(conn, memory_record_id=memory_record_id)
        return record or {}
    finally:
        conn.close()


def get_memory_record(settings: Settings, *, memory_record_id: str) -> dict[str, Any] | None:
    conn = connect(settings.db_path)
    try:
        return _fetch_memory_record(conn, memory_record_id=memory_record_id)
    finally:
        conn.close()


def list_memory_records(
    settings: Settings,
    *,
    kind: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    query: str | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    conn = connect(settings.db_path)
    try:
        sql = """
            SELECT memory_records.*, (
                SELECT COUNT(1)
                FROM memory_record_artifacts
                WHERE memory_record_artifacts.memory_record_id = memory_records.id
            ) AS artifact_count
            FROM memory_records
            WHERE 1 = 1
        """
        params: list[Any] = []
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if scope_type:
            sql += " AND scope_type = ?"
            params.append(scope_type)
        if scope_id:
            sql += " AND scope_id = ?"
            params.append(scope_id)
        if query:
            like = f"%{query.strip()}%"
            sql += " AND (memory_key LIKE ? OR title LIKE ? OR summary LIKE ? OR content LIKE ? OR tags_json LIKE ? OR source LIKE ? OR source_ref LIKE ?)"
            params.extend([like, like, like, like, like, like, like])
        sql += " ORDER BY pinned DESC, updated_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [record for row in rows if (record := _row_to_dict(row)) is not None]
    finally:
        conn.close()


def touch_memory_record(settings: Settings, *, memory_record_id: str) -> dict[str, Any] | None:
    now = utc_now()
    conn = connect(settings.db_path)
    try:
        conn.execute(
            "UPDATE memory_records SET last_accessed_at = ?, updated_at = ? WHERE id = ?",
            (now, now, memory_record_id),
        )
        conn.commit()
        return get_memory_record(settings, memory_record_id=memory_record_id)
    finally:
        conn.close()


def add_memory_record_artifact(
    settings: Settings,
    *,
    memory_record_id: str,
    artifact_type: str,
    artifact_ref: str,
    label: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    now = utc_now()
    conn = connect(settings.db_path)
    try:
        record = _fetch_memory_record(conn, memory_record_id=memory_record_id)
        if record is None:
            return None
        artifact_payload = {
            "artifact_type": artifact_type,
            "artifact_ref": artifact_ref,
            "label": label,
            "metadata": metadata or {},
            "created_at": now,
        }
        current_artifacts = list(record.get("artifacts") or [])
        current_artifacts.append(artifact_payload)
        conn.execute(
            """
            INSERT INTO memory_record_artifacts (
                memory_record_id, artifact_type, artifact_ref, label, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (memory_record_id, artifact_type, artifact_ref, label, json.dumps(metadata or {}), now),
        )
        conn.execute(
            "UPDATE memory_records SET artifacts_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(current_artifacts), now, memory_record_id),
        )
        conn.commit()
        return get_memory_record(settings, memory_record_id=memory_record_id)
    finally:
        conn.close()


def list_memory_record_artifacts(
    settings: Settings,
    *,
    memory_record_id: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    conn = connect(settings.db_path)
    try:
        sql = "SELECT * FROM memory_record_artifacts WHERE memory_record_id = ? ORDER BY id ASC"
        params: list[Any] = [memory_record_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [record for row in rows if (record := _row_to_dict(row)) is not None]
    finally:
        conn.close()
