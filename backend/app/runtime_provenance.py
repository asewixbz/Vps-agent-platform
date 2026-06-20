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
    return (
        f"{record.get('id', ''):<36} {record.get('kind', ''):<16} {scope:<24} "
        f"{_truncate(str(record.get('title') or ''), 40)}"
    )


def _link_row(link: dict[str, Any]) -> str:
    source = f"{link.get('source_type', '')}:{link.get('source_id', '')}"
    target = f"{link.get('target_type', '')}:{link.get('target_id', '')}"
    note = _truncate(str(link.get('note') or ''), 30)
    return f"{source:<28} -[{link.get('relation_type', '')}]-> {target:<28} {note}"


def _artifact_row(artifact: dict[str, Any]) -> str:
    return (
        f"{artifact.get('artifact_type', ''):<20} "
        f"{_truncate(str(artifact.get('artifact_ref') or ''), 40):<40} {artifact.get('label') or ''}"
    )


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_runtime_provenance(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, f"/agent/runs/{args.runtime_run_id}/provenance")
    runtime_run = data.get("runtime_run") or {}
    snapshot = data.get("memory_snapshot") or {}
    provenance = data.get("provenance") or {}

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
    print(f"memory_snapshot: {snapshot.get('id')}")
    if snapshot.get("summary"):
        print(f"snapshot_summary: {snapshot.get('summary')}")
    print(f"related_records: {len(provenance.get('related_records') or [])}")
    print(f"direct_artifacts: {len(provenance.get('direct_artifacts') or [])}")
    print(f"artifact_links: {len(provenance.get('artifact_links') or [])}")
    print(f"artifact_refs: {len(provenance.get('artifact_refs') or [])}")

    if snapshot:
        print("snapshot:")
        print(f"  {_record_row(snapshot)}")
    if provenance.get("direct_artifacts"):
        print("direct artifacts:")
        for artifact in provenance.get("direct_artifacts") or []:
            print(f"  - {_artifact_row(artifact)}")
    if provenance.get("related_records"):
        print("related records:")
        for related in provenance.get("related_records") or []:
            print(f"  - {_record_row(related)}")
            if related.get("summary"):
                print(f"    summary: {_truncate(str(related.get('summary')), 72)}")
            if related.get("artifacts"):
                print(f"    artifacts: {len(related.get('artifacts') or [])}")
    if provenance.get("artifact_links"):
        print("artifact links:")
        for link in provenance.get("artifact_links") or []:
            print(f"  - {_link_row(link)}")
    if provenance.get("artifact_refs"):
        print("artifact refs:")
        for artifact_ref in provenance.get("artifact_refs") or []:
            print(f"  - {artifact_ref}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run-provenance",
        description="Inspect provenance for a runtime run and its memory snapshot",
    )
    parser.add_argument("runtime_run_id", help="runtime run id")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="FastAPI base URL (default: %(default)s)")
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
