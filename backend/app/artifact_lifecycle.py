from __future__ import annotations

import gzip
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .settings import Settings

ARTIFACT_RETENTION_POLICIES: dict[str, timedelta | None] = {
    "transient": timedelta(days=1),
    "run-scoped": timedelta(days=7),
    "memory-scoped": timedelta(days=90),
    "long-lived": None,
}

_DEFAULT_RETENTION_BY_TYPE = {
    "stdout": "transient",
    "stderr": "transient",
    "log": "transient",
    "page.html": "run-scoped",
    "page.txt": "run-scoped",
    "report.json": "run-scoped",
    "report.md": "run-scoped",
    "ranking.json": "run-scoped",
    "ranking.md": "run-scoped",
    "scan.json": "run-scoped",
    "scan.md": "run-scoped",
    "compare.json": "run-scoped",
    "compare.md": "run-scoped",
    "schedule.json": "run-scoped",
    "schedule.md": "run-scoped",
    "schedule_manifest.json": "run-scoped",
    "artifacts.json": "run-scoped",
}


@dataclass(frozen=True)
class CleanupSummary:
    scanned: int
    deleted: int
    compressed: int
    kept: int
    skipped: int
    invalid_manifests: int
    empty_dirs_removed: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def classify_retention_class(artifact_type: str | None, artifact_ref: str | None = None) -> str:
    normalized_type = str(artifact_type or "").strip().lower()
    if normalized_type in {"memory", "memory_record", "memory_snapshot", "memory-scoped"}:
        return "memory-scoped"
    if normalized_type in {"artifact_manifest", "artifact-manifest", "long-lived"}:
        return "long-lived"
    if normalized_type in {"report", "ranking", "scan", "compare", "schedule"}:
        return "run-scoped"
    if normalized_type in _DEFAULT_RETENTION_BY_TYPE:
        default_retention = _DEFAULT_RETENTION_BY_TYPE[normalized_type]
        return default_retention or "run-scoped"
    ref = str(artifact_ref or "").lower()
    if any(ref.endswith(suffix) for suffix in (".log", ".txt")):
        return "transient"
    if any(ref.endswith(suffix) for suffix in ("report.json", "report.md", "ranking.json", "ranking.md", "scan.json", "scan.md", "compare.json", "compare.md", "schedule.json", "schedule.md")):
        return "run-scoped"
    return "run-scoped"


def normalize_artifact_entry(
    artifact: dict[str, Any],
    *,
    default_retention_class: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(artifact, dict):
        return None
    artifact_ref = str(artifact.get("artifact_ref") or artifact.get("path") or artifact.get("ref") or "").strip()
    artifact_type = str(artifact.get("artifact_type") or artifact.get("type") or "file").strip() or "file"
    if not artifact_ref:
        return None
    retention_class = str(
        artifact.get("retention_class") or default_retention_class or classify_retention_class(artifact_type, artifact_ref)
    )
    label = artifact.get("label")
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
    references = artifact.get("references") if isinstance(artifact.get("references"), list) else []
    return {
        "artifact_type": artifact_type,
        "artifact_ref": artifact_ref,
        "label": label,
        "retention_class": retention_class,
        "references": [str(item) for item in references if item is not None],
        "metadata": metadata,
    }


def _unique_artifact_refs(artifacts: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for artifact in artifacts:
        ref = str(artifact.get("artifact_ref") or "").strip()
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def build_artifact_manifest(
    *,
    scope_type: str,
    scope_id: str,
    artifacts: list[dict[str, Any]],
    correlation_id: str | None = None,
    runtime_run_id: str | None = None,
    task_id: str | None = None,
    source: str | None = None,
    created_at: str | None = None,
    retention_class: str | None = None,
) -> dict[str, Any]:
    normalized_artifacts = [item for item in (normalize_artifact_entry(artifact, default_retention_class=retention_class) for artifact in artifacts) if item is not None]
    manifest = {
        "schema_version": 1,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "runtime_run_id": runtime_run_id,
        "task_id": task_id,
        "source": source or "artifact_lifecycle",
        "created_at": created_at or _now().isoformat(),
        "updated_at": _now().isoformat(),
        "retention_class": retention_class or (normalized_artifacts[0]["retention_class"] if normalized_artifacts else "run-scoped"),
        "artifacts": normalized_artifacts,
        "artifact_paths": _unique_artifact_refs(normalized_artifacts),
    }
    return manifest


def normalize_artifact_manifest(
    raw_manifest: Any,
    *,
    default_scope_type: str | None = None,
    default_scope_id: str | None = None,
    source: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(raw_manifest, dict):
        return None

    if raw_manifest.get("artifacts") and isinstance(raw_manifest.get("artifacts"), list):
        artifacts = [item for item in (normalize_artifact_entry(artifact) for artifact in raw_manifest.get("artifacts") or []) if item is not None]
    else:
        artifacts = []
        for key, value in raw_manifest.items():
            if key in {"artifact_paths", "schema_version", "scope_type", "scope_id", "runtime_run_id", "task_id", "source", "created_at", "updated_at", "retention_class", "correlation_id"}:
                continue
            if not isinstance(value, str):
                continue
            artifact_type = "file"
            if key.endswith("_md_path"):
                artifact_type = "markdown"
            elif key.endswith("_json_path") or key.endswith("_path"):
                artifact_type = "file"
            artifact = normalize_artifact_entry(
                {
                    "artifact_type": artifact_type,
                    "artifact_ref": value,
                    "label": key,
                }
            )
            if artifact is not None:
                artifacts.append(artifact)
        for ref in raw_manifest.get("artifact_paths") or []:
            if isinstance(ref, str):
                artifact = normalize_artifact_entry({"artifact_type": "file", "artifact_ref": ref, "label": Path(ref).name})
                if artifact is not None:
                    artifacts.append(artifact)

    scope_type = str(raw_manifest.get("scope_type") or default_scope_type or "task")
    scope_id = str(raw_manifest.get("scope_id") or default_scope_id or "")
    retention_class = str(raw_manifest.get("retention_class") or (artifacts[0]["retention_class"] if artifacts else "run-scoped"))
    manifest = {
        "schema_version": int(raw_manifest.get("schema_version") or 1),
        "scope_type": scope_type,
        "scope_id": scope_id,
        "correlation_id": raw_manifest.get("correlation_id"),
        "runtime_run_id": raw_manifest.get("runtime_run_id"),
        "task_id": raw_manifest.get("task_id"),
        "source": raw_manifest.get("source") or source or "artifact_lifecycle",
        "created_at": str(raw_manifest.get("created_at") or _now().isoformat()),
        "updated_at": str(raw_manifest.get("updated_at") or _now().isoformat()),
        "retention_class": retention_class,
        "artifacts": artifacts,
        "artifact_paths": _unique_artifact_refs(artifacts),
    }
    if not manifest["scope_id"] and default_scope_id is not None:
        manifest["scope_id"] = default_scope_id
    return manifest


def artifact_manifest_issues(manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(manifest.get("schema_version"), int):
        issues.append("schema_version must be an integer")
    if not str(manifest.get("scope_type") or "").strip():
        issues.append("scope_type is required")
    if not str(manifest.get("scope_id") or "").strip():
        issues.append("scope_id is required")
    if not isinstance(manifest.get("artifacts"), list):
        issues.append("artifacts must be a list")
    else:
        for index, artifact in enumerate(manifest.get("artifacts") or []):
            if not isinstance(artifact, dict):
                issues.append(f"artifact[{index}] must be an object")
                continue
            if not str(artifact.get("artifact_ref") or "").strip():
                issues.append(f"artifact[{index}] artifact_ref is required")
            if not str(artifact.get("artifact_type") or "").strip():
                issues.append(f"artifact[{index}] artifact_type is required")
    return issues


def write_artifact_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_artifact_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return normalize_artifact_manifest(raw, source=path.name)


def _artifact_retention_deadline(manifest: dict[str, Any], *, now: datetime) -> datetime | None:
    retention_class = str(manifest.get("retention_class") or "run-scoped")
    retention = ARTIFACT_RETENTION_POLICIES.get(retention_class, ARTIFACT_RETENTION_POLICIES["run-scoped"])
    if retention is None:
        return None
    created_at = str(manifest.get("created_at") or "")
    try:
        timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else now
    except ValueError:
        timestamp = now
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp + retention


def _maybe_compress_text_artifacts(directory: Path) -> int:
    compressed = 0
    for file_path in directory.glob("**/*"):
        if not file_path.is_file() or file_path.suffix not in {".log", ".txt", ".md"}:
            continue
        gz_path = file_path.with_suffix(file_path.suffix + ".gz")
        if gz_path.exists():
            continue
        try:
            with file_path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            compressed += 1
        except OSError:
            continue
    return compressed


def cleanup_artifact_roots(settings: Settings, *, now: datetime | None = None, dry_run: bool = False, compress_logs: bool = False) -> dict[str, int]:
    current = now or _now()
    roots = [Path(settings.work_dir)]
    if settings.artifact_dir:
        roots.append(Path(settings.artifact_dir))

    scanned = deleted = compressed = kept = skipped = invalid_manifests = empty_dirs_removed = 0

    for root in roots:
        if not root.exists():
            continue
        for entry in list(root.iterdir()):
            if not entry.is_dir():
                continue
            scanned += 1
            manifest_path = entry / "artifacts.json"
            if not manifest_path.exists():
                manifest_path = entry / "artifact_manifest.json"
            manifest = read_artifact_manifest(manifest_path) if manifest_path.exists() else None
            if manifest is None and manifest_path.exists():
                invalid_manifests += 1
                continue

            if manifest is not None:
                deadline = _artifact_retention_deadline(manifest, now=current)
                if deadline is None:
                    kept += 1
                    continue
                if current < deadline:
                    kept += 1
                    continue
            elif any(True for _ in entry.iterdir()):
                kept += 1
                continue

            if compress_logs and not dry_run:
                compressed += _maybe_compress_text_artifacts(entry)

            if dry_run:
                skipped += 1
                continue

            try:
                shutil.rmtree(entry)
                deleted += 1
            except OSError:
                skipped += 1
                continue

        for entry in list(root.iterdir()):
            if entry.is_dir() and not any(entry.iterdir()):
                if dry_run:
                    continue
                try:
                    entry.rmdir()
                    empty_dirs_removed += 1
                except OSError:
                    pass

    return {
        "scanned": scanned,
        "deleted": deleted,
        "compressed": compressed,
        "kept": kept,
        "skipped": skipped,
        "invalid_manifests": invalid_manifests,
        "empty_dirs_removed": empty_dirs_removed,
    }
