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
    if "metadata_json" in data:
        data["metadata"] = _load_json(data.pop("metadata_json"), {})
    return data


def init_memory_links_schema(settings: Settings) -> None:
    conn = connect(settings.db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_links (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                note TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def add_memory_link(
    settings: Settings,
    *,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    relation_type: str,
    note: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    link_id = str(uuid.uuid4())
    now = utc_now()
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            INSERT INTO memory_links (
                id, source_type, source_id, target_type, target_id, relation_type, note, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_id,
                source_type,
                source_id,
                target_type,
                target_id,
                relation_type,
                note,
                json.dumps(metadata or {}),
                now,
                now,
            ),
        )
        conn.commit()
        return get_memory_link(settings, memory_link_id=link_id) or {
            "id": link_id,
            "source_type": source_type,
            "source_id": source_id,
            "target_type": target_type,
            "target_id": target_id,
            "relation_type": relation_type,
            "note": note,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
    finally:
        conn.close()


def get_memory_link(settings: Settings, *, memory_link_id: str) -> dict[str, Any] | None:
    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT * FROM memory_links WHERE id = ?", (memory_link_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_memory_links(
    settings: Settings,
    *,
    source_type: str | None = None,
    source_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    relation_type: str | None = None,
    query: str | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    conn = connect(settings.db_path)
    try:
        sql = "SELECT * FROM memory_links WHERE 1 = 1"
        params: list[Any] = []
        if source_type:
            sql += " AND source_type = ?"
            params.append(source_type)
        if source_id:
            sql += " AND source_id = ?"
            params.append(source_id)
        if target_type:
            sql += " AND target_type = ?"
            params.append(target_type)
        if target_id:
            sql += " AND target_id = ?"
            params.append(target_id)
        if relation_type:
            sql += " AND relation_type = ?"
            params.append(relation_type)
        if query:
            like = f"%{query.strip()}%"
            sql += " AND (source_type LIKE ? OR source_id LIKE ? OR target_type LIKE ? OR target_id LIKE ? OR relation_type LIKE ? OR note LIKE ? OR metadata_json LIKE ?)"
            params.extend([like, like, like, like, like, like, like])
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [link for row in rows if (link := _row_to_dict(row)) is not None]
    finally:
        conn.close()


def list_memory_links_for_entity(
    settings: Settings,
    *,
    entity_type: str,
    entity_id: str,
    relation_type: str | None = None,
    query: str | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    return list_memory_links(
        settings,
        source_type=entity_type,
        source_id=entity_id,
        relation_type=relation_type,
        query=query,
        limit=limit,
    )
