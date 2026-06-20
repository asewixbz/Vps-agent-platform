from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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


def _build_path(path: str, params: dict[str, Any]) -> str:
    filtered = {key: str(value) for key, value in params.items() if value is not None and value != ""}
    if not filtered:
        return path
    return f"{path}?{urlencode(filtered)}"


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


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def build_provenance(args: argparse.Namespace) -> dict[str, Any]:
    record = request_json("GET", args.base_url, f"/memory/records/{args.memory_record_id}")
    links = request_json(
        "GET",
        args.base_url,
        _build_path(
            f"/memory/records/{args.memory_record_id}/links",
            {
                "direction": "both",
                "limit": args.limit,
            },
        ),
    )

    related_records: list[dict[str, Any]] = []
    artifact_links: list[dict[str, Any]] = []
    seen_related_ids: set[str] = set()
    for link in links if isinstance(links, list) else []:
        source_type = str(link.get("source_type") or "")
        target_type = str(link.get("target_type") or "")
        source_id = str(link.get("source_id") or "")
        target_id = str(link.get("target_id") or "")
        if source_type == "memory_record" and source_id and source_id != args.memory_record_id and source_id not in seen_related_ids:
            seen_related_ids.add(source_id)
            related_records.append(request_json("GET", args.base_url, f"/memory/records/{source_id}"))
        if target_type == "memory_record" and target_id and target_id != args.memory_record_id and target_id not in seen_related_ids:
            seen_related_ids.add(target_id)
            related_records.append(request_json("GET", args.base_url, f"/memory/records/{target_id}"))
        if source_type == "artifact" or target_type == "artifact":
            artifact_links.append(link)

    return {
        "record": record,
        "links": links,
        "related_records": related_records,
        "artifact_links": artifact_links,
    }


def cmd_memory_provenance(args: argparse.Namespace) -> int:
    data = build_provenance(args)
    record = data["record"]
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
    print(f"links: {len(data['links']) if isinstance(data['links'], list) else 0}")
    print(f"related_records: {len(data['related_records'])}")
    print(f"artifact_links: {len(data['artifact_links'])}")

    if data["related_records"]:
        print("related records:")
        for related in data["related_records"]:
            print(f"  - {format_memory_record_row(related)}")
            if related.get("summary"):
                print(f"    summary: {_truncate(str(related.get('summary')), 72)}")
    if data["artifact_links"]:
        print("artifact links:")
        for link in data["artifact_links"]:
            print(f"  - {format_memory_link_row(link)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory-provenance",
        description="Inspect durable memory provenance and linked records",
    )
    parser.add_argument("memory_record_id", help="memory record id")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="FastAPI base URL (default: %(default)s)")
    parser.add_argument("--limit", type=int, default=100, help="maximum number of links to inspect")
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
