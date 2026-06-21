from __future__ import annotations

import json
import uuid
from typing import Any

from .settings import Settings
from .store import connect, utc_now

WORKFLOW_TEMPLATE_TABLE = "workflow_templates"


def ensure_workflow_template_registry(settings: Settings) -> None:
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_templates (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                kind TEXT NOT NULL,
                summary TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                recommended_tool TEXT,
                requires_approval INTEGER NOT NULL DEFAULT 0,
                notes_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


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


def _row_to_template(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None

    data = dict(row)
    data["steps"] = _load_json(data.pop("steps_json"), [])
    data["notes"] = _load_json(data.pop("notes_json"), [])
    data["metadata"] = _load_json(data.pop("metadata_json"), {})
    data["recommended_tool"] = data.get("recommended_tool") or None
    data["requires_approval"] = bool(data.get("requires_approval") or 0)
    return data


def get_custom_workflow_template(settings: Settings, *, name: str) -> dict[str, Any] | None:
    ensure_workflow_template_registry(settings)
    conn = connect(settings.db_path)
    try:
        row = conn.execute("SELECT * FROM workflow_templates WHERE name = ?", (name,)).fetchone()
        return _row_to_template(row)
    finally:
        conn.close()


def list_custom_workflow_templates(settings: Settings) -> list[dict[str, Any]]:
    ensure_workflow_template_registry(settings)
    conn = connect(settings.db_path)
    try:
        rows = conn.execute("SELECT * FROM workflow_templates ORDER BY created_at ASC").fetchall()
        return [template for row in rows if (template := _row_to_template(row)) is not None]
    finally:
        conn.close()


def upsert_custom_workflow_template(settings: Settings, template: dict[str, Any]) -> dict[str, Any]:
    ensure_workflow_template_registry(settings)
    name = str(template.get("name") or template.get("template_name") or "").strip()
    if not name:
        raise ValueError("workflow template name is required")

    kind = str(template.get("kind") or template.get("template_kind") or "workflow").strip() or "workflow"
    summary = str(template.get("summary") or "").strip()
    if not summary:
        summary = f"Workflow template: {name}"

    steps = template.get("steps")
    if not isinstance(steps, list):
        steps = []

    notes = template.get("notes")
    if not isinstance(notes, list):
        notes = []

    metadata = template.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    recommended_tool = template.get("recommended_tool")
    if recommended_tool in {None, ""}:
        recommended_tool = None

    now = utc_now()
    template_id = str(template.get("id") or uuid.uuid4())
    conn = connect(settings.db_path)
    try:
        conn.execute(
            """
            INSERT INTO workflow_templates (
                id,
                name,
                kind,
                summary,
                steps_json,
                recommended_tool,
                requires_approval,
                notes_json,
                metadata_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                kind = excluded.kind,
                summary = excluded.summary,
                steps_json = excluded.steps_json,
                recommended_tool = excluded.recommended_tool,
                requires_approval = excluded.requires_approval,
                notes_json = excluded.notes_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                template_id,
                name,
                kind,
                summary,
                json.dumps(steps, ensure_ascii=False),
                recommended_tool,
                1 if bool(template.get("requires_approval") or False) else 0,
                json.dumps(notes, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )
        conn.commit()
        saved = get_custom_workflow_template(settings, name=name)
        if saved is None:
            raise RuntimeError("workflow template could not be saved")
        return saved
    finally:
        conn.close()


def delete_custom_workflow_template(settings: Settings, *, name: str) -> bool:
    ensure_workflow_template_registry(settings)
    conn = connect(settings.db_path)
    try:
        cursor = conn.execute("DELETE FROM workflow_templates WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
