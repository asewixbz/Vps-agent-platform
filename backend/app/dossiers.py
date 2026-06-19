from __future__ import annotations

from typing import Any

from .memory import list_memory_records, upsert_memory_record
from .settings import Settings

CONTACT_DOSSIER_KIND = "contact_dossier"
PROJECT_DOSSIER_KIND = "project_dossier"


def _merge_tags(base_tags: list[str], tags: list[str] | None) -> list[str]:
    merged: list[str] = []
    for tag in [*base_tags, *(tags or [])]:
        if tag and tag not in merged:
            merged.append(tag)
    return merged


def _merge_metadata(
    *,
    dossier_type: str,
    scope_type: str,
    scope_id: str,
    title: str,
    summary: str,
    content: str,
    stage: str | None,
    next_step: str | None,
    status: str | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    merged.update(
        {
            "dossier_type": dossier_type,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "title": title,
            "summary": summary,
            "content": content,
        }
    )
    if stage:
        merged["stage"] = stage
    if next_step:
        merged["next_step"] = next_step
    if status:
        merged["status"] = status
    return merged


def upsert_contact_dossier(
    settings: Settings,
    *,
    contact_id: str,
    title: str,
    summary: str = "",
    content: str = "",
    stage: str | None = None,
    next_step: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    source: str | None = None,
    source_ref: str | None = None,
    importance: int = 0,
    pinned: bool = False,
    last_accessed_at: str | None = None,
) -> dict[str, Any]:
    merged_tags = _merge_tags(["dossier", "contact", "relationship"], tags)
    merged_metadata = _merge_metadata(
        dossier_type=CONTACT_DOSSIER_KIND,
        scope_type="contact",
        scope_id=contact_id,
        title=title,
        summary=summary,
        content=content,
        stage=stage,
        next_step=next_step,
        status=status,
        metadata=metadata,
    )
    return upsert_memory_record(
        settings,
        memory_key=f"contact:{contact_id}",
        kind=CONTACT_DOSSIER_KIND,
        scope_type="contact",
        scope_id=contact_id,
        title=title,
        summary=summary,
        content=content,
        tags=merged_tags,
        metadata=merged_metadata,
        source=source,
        source_ref=source_ref,
        importance=importance,
        pinned=pinned,
        last_accessed_at=last_accessed_at,
    )


def upsert_project_dossier(
    settings: Settings,
    *,
    project_id: str,
    title: str,
    summary: str = "",
    content: str = "",
    stage: str | None = None,
    next_step: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    source: str | None = None,
    source_ref: str | None = None,
    importance: int = 0,
    pinned: bool = False,
    last_accessed_at: str | None = None,
) -> dict[str, Any]:
    merged_tags = _merge_tags(["dossier", "project", "workspace"], tags)
    merged_metadata = _merge_metadata(
        dossier_type=PROJECT_DOSSIER_KIND,
        scope_type="project",
        scope_id=project_id,
        title=title,
        summary=summary,
        content=content,
        stage=stage,
        next_step=next_step,
        status=status,
        metadata=metadata,
    )
    return upsert_memory_record(
        settings,
        memory_key=f"project:{project_id}",
        kind=PROJECT_DOSSIER_KIND,
        scope_type="project",
        scope_id=project_id,
        title=title,
        summary=summary,
        content=content,
        tags=merged_tags,
        metadata=merged_metadata,
        source=source,
        source_ref=source_ref,
        importance=importance,
        pinned=pinned,
        last_accessed_at=last_accessed_at,
    )


def get_contact_dossier(settings: Settings, *, contact_id: str) -> dict[str, Any] | None:
    records = list_memory_records(
        settings,
        kind=CONTACT_DOSSIER_KIND,
        scope_type="contact",
        scope_id=contact_id,
        limit=1,
    )
    return records[0] if records else None


def get_project_dossier(settings: Settings, *, project_id: str) -> dict[str, Any] | None:
    records = list_memory_records(
        settings,
        kind=PROJECT_DOSSIER_KIND,
        scope_type="project",
        scope_id=project_id,
        limit=1,
    )
    return records[0] if records else None


def list_contact_dossiers(
    settings: Settings,
    *,
    query: str | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    return list_memory_records(
        settings,
        kind=CONTACT_DOSSIER_KIND,
        scope_type="contact",
        query=query,
        limit=limit,
    )


def list_project_dossiers(
    settings: Settings,
    *,
    query: str | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    return list_memory_records(
        settings,
        kind=PROJECT_DOSSIER_KIND,
        scope_type="project",
        query=query,
        limit=limit,
    )


def list_dossiers(
    settings: Settings,
    *,
    query: str | None = None,
    limit: int | None = 100,
) -> list[dict[str, Any]]:
    records = [
        *list_contact_dossiers(settings, query=query, limit=None),
        *list_project_dossiers(settings, query=query, limit=None),
    ]
    records.sort(key=lambda record: (bool(record.get("pinned")), str(record.get("updated_at") or "")), reverse=True)
    if limit is not None:
        return records[:limit]
    return records
