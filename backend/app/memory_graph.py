from __future__ import annotations

from collections import deque
from typing import Any

from .memory import get_memory_record, list_memory_record_artifacts, list_memory_records
from .memory_links import list_memory_links, list_memory_links_for_entity
from .settings import Settings


def _unique_artifact_key(artifact: dict[str, Any]) -> tuple[Any, ...]:
    return (
        artifact.get("artifact_type"),
        artifact.get("artifact_ref"),
        artifact.get("label"),
    )


def _collect_record_artifacts(settings: Settings, record: dict[str, Any]) -> list[dict[str, Any]]:
    direct_artifacts = list_memory_record_artifacts(settings, memory_record_id=str(record["id"]))
    seen: set[tuple[Any, ...]] = set()
    ordered: list[dict[str, Any]] = []
    for artifact in [*direct_artifacts, *(record.get("artifacts") or [])]:
        if not isinstance(artifact, dict):
            continue
        key = _unique_artifact_key(artifact)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(artifact)
    return ordered


def _memory_record_links_for_record(settings: Settings, record_id: str, *, limit: int) -> list[dict[str, Any]]:
    outbound_links = list_memory_links_for_entity(
        settings,
        entity_type="memory_record",
        entity_id=record_id,
        limit=limit,
    )
    inbound_links = list_memory_links(
        settings,
        target_type="memory_record",
        target_id=record_id,
        limit=limit,
    )
    combined_links = {link["id"]: link for link in [*outbound_links, *inbound_links]}
    return list(combined_links.values())


def _neighbor_for_link(link: dict[str, Any], record_id: str) -> tuple[str | None, str | None]:
    source_type = str(link.get("source_type") or "")
    target_type = str(link.get("target_type") or "")
    source_id = str(link.get("source_id") or "")
    target_id = str(link.get("target_id") or "")

    if source_type == "memory_record" and source_id == record_id and target_type == "memory_record":
        return target_id, "outbound"
    if target_type == "memory_record" and target_id == record_id and source_type == "memory_record":
        return source_id, "inbound"
    return None, None


def _build_record_entry(
    settings: Settings,
    *,
    record: dict[str, Any],
    depth: int,
    via_link: dict[str, Any] | None = None,
    via_record_id: str | None = None,
) -> dict[str, Any]:
    artifacts = _collect_record_artifacts(settings, record)
    entry = {
        **record,
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "depth": depth,
    }
    if via_link is not None:
        entry["via"] = {
            "link_id": via_link.get("id"),
            "relation_type": via_link.get("relation_type"),
            "direction": via_link.get("direction"),
            "source_type": via_link.get("source_type"),
            "source_id": via_link.get("source_id"),
            "target_type": via_link.get("target_type"),
            "target_id": via_link.get("target_id"),
            "note": via_link.get("note"),
        }
    if via_record_id is not None:
        entry["via_record_id"] = via_record_id
    return entry


def _traverse_memory_record_graph(
    settings: Settings,
    *,
    root_record_id: str,
    depth: int,
    limit: int,
) -> dict[str, Any]:
    visited_records: dict[str, dict[str, Any]] = {root_record_id: {"depth": 0}}
    traversal_links: list[dict[str, Any]] = []
    seen_link_ids: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(root_record_id, 0)])

    while queue:
        current_record_id, current_depth = queue.popleft()
        if current_depth >= depth:
            continue

        current_links = _memory_record_links_for_record(settings, current_record_id, limit=limit)
        for link in current_links:
            link_id = str(link.get("id") or "")
            if link_id and link_id not in seen_link_ids:
                seen_link_ids.add(link_id)
                traversal_links.append(link)

            neighbor_id, direction = _neighbor_for_link(link, current_record_id)
            if neighbor_id is None or neighbor_id in visited_records:
                continue

            next_depth = current_depth + 1
            if next_depth > depth:
                continue

            visited_records[neighbor_id] = {
                "depth": next_depth,
                "via_link": {
                    **link,
                    "direction": direction,
                },
                "via_record_id": current_record_id,
            }
            queue.append((neighbor_id, next_depth))

    related_records: list[dict[str, Any]] = []
    transitive_records: list[dict[str, Any]] = []
    artifact_links: list[dict[str, Any]] = []
    artifact_refs: list[str] = []
    seen_record_ids: set[str] = {root_record_id}
    seen_artifact_refs: set[str] = set()

    for artifact in _collect_record_artifacts(settings, get_memory_record(settings, memory_record_id=root_record_id) or {}):
        artifact_ref = str(artifact.get("artifact_ref") or "")
        if artifact_ref and artifact_ref not in seen_artifact_refs:
            seen_artifact_refs.add(artifact_ref)
            artifact_refs.append(artifact_ref)

    ordered_records = [
        (record_id, record_meta)
        for record_id, record_meta in visited_records.items()
        if record_id != root_record_id
    ]
    ordered_records.sort(key=lambda item: (int(item[1].get("depth") or 0), item[0]))

    for record_id, record_meta in ordered_records:
        record = get_memory_record(settings, memory_record_id=record_id)
        if record is None:
            continue
        depth_value = int(record_meta.get("depth") or 0)
        via_link = record_meta.get("via_link")
        via_record_id = record_meta.get("via_record_id")
        entry = _build_record_entry(
            settings,
            record=record,
            depth=depth_value,
            via_link=via_link if isinstance(via_link, dict) else None,
            via_record_id=via_record_id if isinstance(via_record_id, str) else None,
        )
        for artifact in entry.get("artifacts") or []:
            artifact_ref = str(artifact.get("artifact_ref") or "")
            if artifact_ref and artifact_ref not in seen_artifact_refs:
                seen_artifact_refs.add(artifact_ref)
                artifact_refs.append(artifact_ref)
        if depth_value <= 1:
            related_records.append(entry)
        else:
            transitive_records.append(entry)

    for link in traversal_links:
        source_type = str(link.get("source_type") or "")
        target_type = str(link.get("target_type") or "")
        if source_type == "artifact":
            artifact_ref = str(link.get("source_id") or "")
            if artifact_ref and artifact_ref not in seen_artifact_refs:
                seen_artifact_refs.add(artifact_ref)
                artifact_refs.append(artifact_ref)
        if target_type == "artifact":
            artifact_ref = str(link.get("target_id") or "")
            if artifact_ref and artifact_ref not in seen_artifact_refs:
                seen_artifact_refs.add(artifact_ref)
                artifact_refs.append(artifact_ref)
        if source_type == "artifact" or target_type == "artifact":
            artifact_links.append(link)

    related_records.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    transitive_records.sort(key=lambda item: (int(item.get("depth") or 0), str(item.get("updated_at") or "")), reverse=True)
    artifact_links.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)

    return {
        "related_records": related_records,
        "transitive_records": transitive_records,
        "artifact_links": artifact_links,
        "artifact_refs": artifact_refs,
        "traversal_links": traversal_links,
        "visited_record_count": max(0, len(visited_records) - 1),
    }


def build_memory_record_provenance(
    settings: Settings,
    *,
    memory_record_id: str,
    limit: int = 100,
    depth: int = 2,
) -> dict[str, Any] | None:
    record = get_memory_record(settings, memory_record_id=memory_record_id)
    if record is None:
        return None

    direct_links = _memory_record_links_for_record(settings, memory_record_id, limit=limit)
    graph = _traverse_memory_record_graph(settings, root_record_id=memory_record_id, depth=depth, limit=limit)
    direct_artifacts = _collect_record_artifacts(settings, record)
    direct_related_records = graph["related_records"]
    transitive_records = graph["transitive_records"]
    artifact_links = graph["artifact_links"]
    artifact_refs = graph["artifact_refs"]
    traversal_links = graph["traversal_links"]

    for artifact in direct_artifacts:
        artifact_ref = str(artifact.get("artifact_ref") or "")
        if artifact_ref and artifact_ref not in artifact_refs:
            artifact_refs.insert(0, artifact_ref)

    related_records = [
        {
            **related,
            "artifact_count": len(related.get("artifacts") or []),
        }
        for related in direct_related_records
    ]
    transitive_records = [
        {
            **related,
            "artifact_count": len(related.get("artifacts") or []),
        }
        for related in transitive_records
    ]

    root_record = {**record, "artifacts": direct_artifacts, "artifact_count": len(direct_artifacts), "depth": 0}

    return {
        "record": root_record,
        "direct_artifacts": direct_artifacts,
        "related_records": related_records,
        "transitive_records": transitive_records,
        "artifact_links": artifact_links,
        "artifact_refs": artifact_refs,
        "links": direct_links,
        "traversal_links": traversal_links,
        "traversal": {
            "root_record_id": memory_record_id,
            "depth": depth,
            "limit": limit,
            "visited_record_count": graph["visited_record_count"],
            "direct_related_record_count": len(related_records),
            "transitive_record_count": len(transitive_records),
            "traversal_link_count": len(traversal_links),
            "artifact_link_count": len(artifact_links),
            "artifact_ref_count": len(artifact_refs),
        },
        "summary": {
            "record_id": memory_record_id,
            "record_kind": record.get("kind"),
            "related_record_count": len(related_records),
            "transitive_record_count": len(transitive_records),
            "direct_artifact_count": len(direct_artifacts),
            "artifact_link_count": len(artifact_links),
            "artifact_ref_count": len(artifact_refs),
        },
    }


def find_runtime_snapshot(settings: Settings, *, runtime_run_id: str) -> dict[str, Any] | None:
    records = list_memory_records(
        settings,
        kind="runtime_summary",
        scope_type="runtime_run",
        scope_id=runtime_run_id,
        limit=1,
    )
    return records[0] if records else None


def build_runtime_run_provenance(
    settings: Settings,
    *,
    runtime_run_id: str,
    limit: int = 100,
    depth: int = 2,
) -> dict[str, Any]:
    snapshot = find_runtime_snapshot(settings, runtime_run_id=runtime_run_id)
    provenance = (
        build_memory_record_provenance(settings, memory_record_id=str(snapshot["id"]), limit=limit, depth=depth)
        if snapshot is not None
        else None
    )
    return {
        "runtime_run_id": runtime_run_id,
        "memory_snapshot": snapshot,
        "provenance": provenance,
    }
