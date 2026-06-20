from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = os.getenv("VPS_AGENT_API_URL", os.getenv("APP_API_URL", "http://localhost:8000"))


class APIError(RuntimeError):
    pass


def _decode_body(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def request_json(method: str, base_url: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"

    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=30) as response:
            return _decode_body(response.read())
    except HTTPError as exc:
        body = _decode_body(exc.read())
        if isinstance(body, dict):
            detail = body.get("detail", body)
        else:
            detail = body
        raise APIError(f"{exc.code} {exc.reason}: {detail}") from exc
    except URLError as exc:
        raise APIError(f"network error: {exc.reason}") from exc


def _truncate(text: str, limit: int = 72) -> str:
    cleaned = text.replace("\n", " ").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def format_memory_link_row(link: dict[str, Any]) -> str:
    note = _truncate(str(link.get("note") or ""), 34)
    source = f"{link.get('source_type', '')}:{link.get('source_id', '')}"
    target = f"{link.get('target_type', '')}:{link.get('target_id', '')}"
    return f"{link.get('id', ''):<6} {source:<28} -[{link.get('relation_type', '')}]-> {target:<28} {note}"


def format_memory_record_row(record: dict[str, Any]) -> str:
    scope = f"{record.get('scope_type', '')}:{record.get('scope_id', '')}"
    pinned = "yes" if record.get("pinned") else "no"
    title = _truncate(str(record.get("title") or ""), 48)
    return f"{record.get('id', ''):<36} {record.get('kind', ''):<16} {scope:<24} pinned={pinned:<3} {title}"


def format_memory_artifact_row(artifact: dict[str, Any]) -> str:
    label = artifact.get("label") or ""
    return (
        f"{artifact.get('id', ''):<6} {artifact.get('artifact_type', ''):<20} "
        f"{_truncate(str(artifact.get('artifact_ref') or ''), 34):<34} {label}"
    )


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def build_provenance(args: argparse.Namespace) -> dict[str, Any]:
    return request_json(
        "GET",
        args.base_url,
        f"/memory/records/{args.memory_record_id}/provenance?limit={args.limit}",
        None,
    )


def cmd_memory_provenance(args: argparse.Namespace) -> int:
    data = build_provenance(args)
    record = data.get("record") or {}
    summary = data.get("summary") or {}
    direct_artifacts = data.get("direct_artifacts") or []
    related_records = data.get("related_records") or []
    artifact_links = data.get("artifact_links") or []
    artifact_refs = data.get("artifact_refs") or []

    if args.json:
        print_json(data)
        return 0

    print(format_memory_record_row(record))
    metadata = record.get("metadata") or {}
    if metadata.get("runtime_run_id"):
        print(f"runtime_run_id: {metadata.get('runtime_run_id')}")
    if record.get("source_ref"):
        print(f"source_ref: {record.get('source_ref')}")
    if record.get("summary"):
        print(f"summary: {record.get('summary')}")
    if record.get("tags"):
        print(f"tags: {record.get('tags')}")
    print(f"links: {len(data.get('links') or [])}")
    print(f"related_records: {summary.get('related_record_count', len(related_records))}")
    print(f"direct_artifacts: {summary.get('direct_artifact_count', len(direct_artifacts))}")
    print(f"artifact_links: {summary.get('artifact_link_count', len(artifact_links))}")
    print(f"artifact_refs: {summary.get('artifact_ref_count', len(artifact_refs))}")

    if direct_artifacts:
        print("direct artifacts:")
        for artifact in direct_artifacts:
            print(f"  - {format_memory_artifact_row(artifact)}")
    if related_records:
        print("related records:")
        for related in related_records:
            print(f"  - {format_memory_record_row(related)}")
            if related.get("summary"):
                print(f"    summary: {_truncate(str(related.get('summary')), 72)}")
            if related.get("artifacts"):
                print(f"    artifacts: {len(related.get('artifacts') or [])}")
    if artifact_links:
        print("artifact links:")
        for link in artifact_links:
            print(f"  - {format_memory_link_row(link)}")
    if artifact_refs:
        print("artifact refs:")
        for artifact_ref in artifact_refs:
            print(f"  - {artifact_ref}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory-provenance",
        description="Inspect durable memory provenance and linked records",
    )
    parser.add_argument("memory_record_id", help="memory record id")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="FastAPI base URL (default: %(default)s)")
    parser.add_argument("--limit", type=int, default=100, help="maximum number of linked records to inspect")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    return parser


def dispatch(args: argparse.Namespace) -> int:
    try:
        return cmd_memory_provenance(args)
    except APIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return dispatch(args)


if __name__ == "__main__":
    raise SystemExit(main())
