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


def _truncate(text: str, limit: int = 84) -> str:
    cleaned = text.replace("\n", " ").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _record_row(record: dict[str, Any]) -> str:
    scope = f"{record.get('scope_type', '')}:{record.get('scope_id', '')}"
    depth = record.get("depth", 0)
    section = record.get("section")
    section_text = f" section={section}" if section else ""
    return (
        f"{record.get('id', ''):<36} {record.get('kind', ''):<16} {scope:<24} depth={depth:<2} "
        f"{_truncate(str(record.get('title') or ''), 40)}{section_text}"
    )


def _event_row(event: dict[str, Any]) -> str:
    step_index = event.get("step_index")
    step_label = f"step={step_index}" if step_index is not None else "step=-"
    reason_code = event.get("reason_code") or "unknown_error"
    trace = event.get("trace") or {}
    correlation_id = trace.get("correlation_id") or event.get("correlation_id") or ""
    return (
        f"{event.get('id', ''):<6} {event.get('event_name', event.get('event_type', '')):<10} {step_label:<10} "
        f"reason={reason_code:<20} correlation={_truncate(str(correlation_id), 24)} {_truncate(str(event.get('message') or ''), 48)}"
    )


def _artifact_row(artifact: dict[str, Any]) -> str:
    return (
        f"{artifact.get('artifact_type', ''):<20} "
        f"{_truncate(str(artifact.get('artifact_ref') or ''), 40):<40} "
        f"{artifact.get('label') or ''} retention={artifact.get('retention_class') or 'run-scoped'}"
    )


def _step_row(step: dict[str, Any]) -> str:
    return (
        f"[{step.get('index')}] {step.get('status'):<14} {_truncate(str(step.get('title') or ''), 40)}"
        f" tool={step.get('tool_name') or '-'} task={step.get('task_id') or '-'}"
    )


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_runtime_provenance(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, f"/agent/runs/{args.runtime_run_id}/trace?limit={args.limit}&depth={args.depth}")
    runtime_run = data.get("runtime_run") or {}
    provenance = data.get("provenance") or {}
    root = provenance.get("root") or provenance.get("record") or {}
    one_hop = provenance.get("one_hop") or provenance.get("related_records") or []
    transitive = provenance.get("transitive") or provenance.get("transitive_records") or []
    artifact_only = provenance.get("artifact_only") or {}
    navigation = data.get("navigation") or {}
    steps = data.get("steps") or []
    events = data.get("events") or []
    memory_snapshot = data.get("memory_snapshot") or {}
    memory_record = data.get("memory_record") or {}

    if args.json:
        print_json(data)
        return 0

    print(f"runtime run: {runtime_run.get('id')}")
    print(f"goal: {runtime_run.get('goal')}")
    print(f"status: {runtime_run.get('status')}")
    if runtime_run.get("summary"):
        print(f"summary: {runtime_run.get('summary')}")
    if runtime_run.get("blocked_reason"):
        print(f"blocked_reason: {runtime_run.get('blocked_reason')}")
    if runtime_run.get("resume_hint"):
        print(f"resume_hint: {runtime_run.get('resume_hint')}")
    print(f"correlation_id: {navigation.get('correlation_id') or runtime_run.get('correlation_id') or ''}")

    print("timeline:")
    for event in events:
        print(f"  - {_event_row(event)}")

    print("steps:")
    for step in steps:
        print(f"  - {_step_row(step)}")
        if step.get("reason"):
            reason = step.get("reason") or {}
            print(f"    reason: {reason.get('reason_code')} {reason.get('message')}")
        if step.get("artifact_count"):
            print(f"    artifacts: {step.get('artifact_count')}")

    print("root:")
    print(f"  {_record_row(root)}")
    if root.get("summary"):
        print(f"  summary: {_truncate(str(root.get('summary')), 72)}")
    print(f"  artifacts: {int(root.get('artifact_count') or len(root.get('artifacts') or []))}")
    if memory_snapshot:
        print(f"memory_snapshot: {memory_snapshot.get('id')}")
    if memory_record:
        print(f"memory_record: {memory_record.get('id')}")
    print(f"task_ids: {navigation.get('task_ids') or []}")
    print(f"artifact_refs: {navigation.get('artifact_refs') or []}")

    print(f"one_hop_records: {len(one_hop)}")
    print(f"transitive_records: {len(transitive)}")
    print(f"artifact_only_count: {int(artifact_only.get('artifact_count') or len(artifact_only.get('artifacts') or []))}")
    print(f"artifact_links: {len(artifact_only.get('links') or [])}")
    print(f"artifact_refs_total: {len(artifact_only.get('refs') or [])}")

    if root.get("artifacts"):
        print("root artifacts:")
        for artifact in root.get("artifacts") or []:
            print(f"  - {_artifact_row(artifact)}")
    if one_hop:
        print("1-hop records:")
        for related in one_hop:
            print(f"  - {_record_row(related)}")
            if related.get("summary"):
                print(f"    summary: {_truncate(str(related.get('summary')), 72)}")
            if related.get("via"):
                via = related.get("via") or {}
                print(f"    via: {via.get('direction')} {via.get('relation_type')} from {related.get('via_record_id')}")
            print(f"    artifacts: {int(related.get('artifact_count') or len(related.get('artifacts') or []))}")
    if transitive:
        print("transitive records:")
        for related in transitive:
            print(f"  - {_record_row(related)}")
            if related.get("summary"):
                print(f"    summary: {_truncate(str(related.get('summary')), 72)}")
            if related.get("via"):
                via = related.get("via") or {}
                print(f"    via: {via.get('direction')} {via.get('relation_type')} from {related.get('via_record_id')}")
            print(f"    artifacts: {int(related.get('artifact_count') or len(related.get('artifacts') or []))}")
    if artifact_only.get("artifacts"):
        print("artifact-only:")
        for artifact in artifact_only.get("artifacts") or []:
            print(f"  - {_artifact_row(artifact)}")
            sources = artifact.get("sources") or []
            for source in sources:
                print(
                    f"    source: {source.get('section')} {source.get('record_id')} depth={source.get('depth')}"
                )
    if artifact_only.get("links"):
        print("artifact links:")
        for link in artifact_only.get("links") or []:
            source = f"{link.get('source_type', '')}:{link.get('source_id', '')}"
            target = f"{link.get('target_type', '')}:{link.get('target_id', '')}"
            note = _truncate(str(link.get('note') or ''), 30)
            print(f"  - {source:<28} -[{link.get('relation_type', '')}]-> {target:<28} {note}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run-provenance",
        description="Inspect runtime trace, events, provenance, artifacts, and memory snapshots",
    )
    parser.add_argument("runtime_run_id", help="runtime run id")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="FastAPI base URL (default: %(default)s)")
    parser.add_argument("--limit", type=int, default=100, help="maximum number of linked records to inspect")
    parser.add_argument("--depth", type=int, default=2, help="maximum traversal depth for memory links")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    return parser


def dispatch(args: argparse.Namespace) -> int:
    try:
        return cmd_runtime_provenance(args)
    except APIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return dispatch(args)


if __name__ == "__main__":
    raise SystemExit(main())
