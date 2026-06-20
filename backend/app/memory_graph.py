from __future__ import annotations

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


def build_memory_record_provenance(
    settings: Settings,
    *,
    memory_record_id: str,
    limit: int = 100,
) -> dict[str, Any] | None:
    record = get_memory_record(settings, memory_record_id=memory_record_id)
    if record is None:
        return None

    outbound_links = list_memory_links_for_entity(
        settings,
        entity_type="memory_record",
        entity_id=memory_record_id,
        limit=limit,
    )
    inbound_links = list_memory_links(
        settings,
        target_type="memory_record",
        target_id=memory_record_id,
        limit=limit,
    )
    combined_links = {link["id"]: link for link in [*outbound_links, *inbound_links]}
    links = list(combined_links.values())

    direct_artifacts = _collect_record_artifacts(settings, record)
    related_records: list[dict[str, Any]] = []
    artifact_links: list[dict[str, Any]] = []
    artifact_refs: list[str] = []
    seen_record_ids: set[str] = set()
    seen_artifact_refs: set[str] = set()

    for artifact in direct_artifacts:
        artifact_ref = str(artifact.get("artifact_ref") or "")
        if artifact_ref and artifact_ref not in seen_artifact_refs:
            seen_artifact_refs.add(artifact_ref)
            artifact_refs.append(artifact_ref)

    for link in links:
        source_type = str(link.get("source_type") or "")
        target_type = str(link.get("target_type") or "")
        source_id = str(link.get("source_id") or "")
        target_id = str(link.get("target_id") or "")

        if source_type == "memory_record" and source_id != memory_record_id and source_id not in seen_record_ids:
            related = get_memory_record(settings, memory_record_id=source_id)
            if related is not None:
                seen_record_ids.add(source_id)
                artifacts = _collect_record_artifacts(settings, related)
                related_artifacts = []
                for artifact in artifacts:
                    artifact_ref = str(artifact.get("artifact_ref") or "")
                    if artifact_ref and artifact_ref not in seen_artifact_refs:
                        seen_artifact_refs.add(artifact_ref)
                        artifact_refs.append(artifact_ref)
                    related_artifacts.append(artifact)
                related_records.append(
                    {
                        **related,
                        "artifacts": related_artifacts,
                        "artifact_count": len(related_artifacts),
                    }
                )

        if target_type == "memory_record" and target_id != memory_record_id and target_id not in seen_record_ids:
            related = get_memory_record(settings, memory_record_id=target_id)
            if related is not None:
                seen_record_ids.add(target_id)
                artifacts = _collect_record_artifacts(settings, related)
                related_artifacts = []
                for artifact in artifacts:
                    artifact_ref = str(artifact.get("artifact_ref") or "")
                    if artifact_ref and artifact_ref not in seen_artifact_refs:
                        seen_artifact_refs.add(artifact_ref)
                        artifact_refs.append(artifact_ref)
                    related_artifacts.append(artifact)
                related_records.append(
                    {
                        **related,
                        "artifacts": related_artifacts,
                        "artifact_count": len(related_artifacts),
                    }
                )

        if source_type == "artifact" or target_type == "artifact":
            artifact_links.append(link)
            if source_type == "artifact":
                artifact_ref = source_id
                if artifact_ref and artifact_ref not in seen_artifact_refs:
                    seen_artifact_refs.add(artifact_ref)
                    artifact_refs.append(artifact_ref)
            if target_type == "artifact":
                artifact_ref = target_id
                if artifact_ref and artifact_ref not in seen_artifact_refs:
                    seen_artifact_refs.add(artifact_ref)
                    artifact_refs.append(artifact_ref)

    related_records.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    artifact_links.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)

    return {
        "record": {**record, "artifacts": direct_artifacts, "artifact_count": len(direct_artifacts)},
        "direct_artifacts": direct_artifacts,
        "related_records": related_records,
        "artifact_links": artifact_links,
        "artifact_refs": artifact_refs,
        "links": links,
        "summary": {
            "record_id": memory_record_id,
            "record_kind": record.get("kind"),
            "related_record_count": len(related_records),
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
) -> dict[str, Any]:
    snapshot = find_runtime_snapshot(settings, runtime_run_id=runtime_run_id)
    provenance = (
        build_memory_record_provenance(settings, memory_record_id=str(snapshot["id"]), limit=limit)
        if snapshot is not None
        else None
    )
    return {
        "runtime_run_id": runtime_run_id,
        "memory_snapshot": snapshot,
        "provenance": provenance,
    }
