from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
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


def _parse_json_object(raw: str, label: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


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


def load_payload(payload: str | None, payload_file: str | None) -> dict[str, Any]:
    if payload_file:
        raw = sys.stdin.read() if payload_file == "-" else Path(payload_file).read_text(encoding="utf-8")
    elif payload is not None:
        raw = payload
    else:
        return {}
    return _parse_json_object(raw, "payload")


def load_metadata(metadata: str | None, metadata_file: str | None) -> dict[str, Any]:
    if metadata_file:
        raw = sys.stdin.read() if metadata_file == "-" else Path(metadata_file).read_text(encoding="utf-8")
    elif metadata is not None:
        raw = metadata
    else:
        return {}
    return _parse_json_object(raw, "metadata")


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def format_tool_row(tool: dict[str, Any]) -> str:
    return f"{tool.get('name', ''):<20} {tool.get('kind', ''):<10} {tool.get('status', ''):<10} trust={tool.get('trust_level', 0)}  {tool.get('description', '')}"


def format_task_row(task: dict[str, Any]) -> str:
    approved = "yes" if task.get("approved") else "no"
    return f"{task.get('id', ''):<36} {task.get('status', ''):<16} {task.get('tool_name', ''):<18} approved={approved}  {task.get('created_at', '')}"


def cmd_health(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, "/health")
    if args.json:
        print_json(data)
    else:
        print(f"status: {data.get('status')}")
        print(f"app: {data.get('app')}")
    return 0


def cmd_phases(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, "/phases")
    if args.json:
        print_json(data)
    else:
        for phase_name, items in data.items():
            print(phase_name)
            for item in items:
                print(f"  - {item}")
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, "/queue")
    if args.json:
        print_json(data)
    else:
        print(f"queue: {data.get('name')}")
        print(f"size: {data.get('size')}")
    return 0


def cmd_tools(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, "/tools")
    if args.json:
        print_json(data)
    else:
        for tool in data:
            print(format_tool_row(tool))
    return 0


def cmd_register_tool(args: argparse.Namespace) -> int:
    metadata = load_metadata(args.metadata, args.metadata_file)
    body: dict[str, Any] = {
        "name": args.name,
        "kind": args.kind,
        "description": args.description or "",
        "entrypoint": args.entrypoint,
        "status": args.status,
        "trust_level": args.trust_level,
        "metadata": metadata,
    }
    data = request_json("POST", args.base_url, "/tools/register", body)
    if args.json:
        print_json(data)
    else:
        print(f"tool registered: {data.get('name')}")
        print(f"kind: {data.get('kind')}")
        print(f"status: {data.get('status')}")
        print(f"trust_level: {data.get('trust_level')}")
    return 0


def cmd_tasks(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, "/tasks")
    if args.json:
        print_json(data)
    else:
        for task in data:
            print(format_task_row(task))
    return 0


def cmd_task(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, f"/tasks/{args.task_id}")
    if args.json:
        print_json(data)
    else:
        print(f"id: {data.get('id')}")
        print(f"tool: {data.get('tool_name')}")
        print(f"status: {data.get('status')}")
        print(f"approved: {bool(data.get('approved'))}")
        if data.get("reason"):
            print(f"reason: {data.get('reason')}")
        if data.get("stdout"):
            print("stdout:")
            print(data.get("stdout"))
        if data.get("stderr"):
            print("stderr:")
            print(data.get("stderr"))
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    payload = load_payload(args.payload, args.payload_file)
    body: dict[str, Any] = {
        "tool_name": args.tool_name,
        "payload": payload,
        "auto_run": args.auto_run,
    }
    if args.timeout_seconds is not None:
        body["timeout_seconds"] = args.timeout_seconds

    data = request_json("POST", args.base_url, "/tasks", body)
    if args.json:
        print_json(data)
    else:
        print(f"task created: {data.get('id')}")
        print(f"tool: {data.get('tool_name')}")
        print(f"status: {data.get('status')}")
        if data.get("reason"):
            print(f"reason: {data.get('reason')}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    body = {"note": args.note} if args.note else {}
    data = request_json("POST", args.base_url, f"/tasks/{args.task_id}/approve", body)
    if args.json:
        print_json(data)
    else:
        print(f"task approved: {data.get('id')}")
        print(f"status: {data.get('status')}")
        if data.get("approval_note"):
            print(f"note: {data.get('approval_note')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vps-agent",
        description="CLI client for the VPS Agent Platform control plane",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="FastAPI base URL (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="print JSON output")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health", help="check API health")
    subparsers.add_parser("phases", help="show roadmap phases exposed by the API")
    subparsers.add_parser("queue", help="show queue size")
    subparsers.add_parser("tools", help="list tools")
    subparsers.add_parser("tasks", help="list tasks")

    register_tool_parser = subparsers.add_parser("register-tool", help="register a tool")
    register_tool_parser.add_argument("name", help="tool name")
    register_tool_parser.add_argument("kind", choices=["python", "shell", "browser", "model", "messaging"], help="tool kind")
    register_tool_parser.add_argument("--description", default="", help="tool description")
    register_tool_parser.add_argument("--entrypoint", help="tool entrypoint")
    register_tool_parser.add_argument("--status", choices=["draft", "tested", "trusted", "blocked"], default="draft", help="tool status")
    register_tool_parser.add_argument("--trust-level", type=int, default=0, help="tool trust level")
    register_tool_parser.add_argument("--metadata", help="JSON metadata string")
    register_tool_parser.add_argument("--metadata-file", help="path to a JSON metadata file, or - for stdin")

    task_parser = subparsers.add_parser("task", help="show a single task")
    task_parser.add_argument("task_id", help="task id")

    submit_parser = subparsers.add_parser("submit", help="create a task")
    submit_parser.add_argument("tool_name", help="registered tool name")
    submit_parser.add_argument("--payload", help="JSON payload string")
    submit_parser.add_argument("--payload-file", help="path to a JSON payload file, or - for stdin")
    submit_parser.add_argument("--auto-run", action=argparse.BooleanOptionalAction, default=True, help="enqueue task immediately")
    submit_parser.add_argument("--timeout-seconds", type=int, help="override execution timeout")

    approve_parser = subparsers.add_parser("approve", help="approve a queued task")
    approve_parser.add_argument("task_id", help="task id")
    approve_parser.add_argument("--note", help="approval note")

    return parser


def dispatch(args: argparse.Namespace) -> int:
    command = args.command
    handlers = {
        "health": cmd_health,
        "phases": cmd_phases,
        "queue": cmd_queue,
        "tools": cmd_tools,
        "register-tool": cmd_register_tool,
        "tasks": cmd_tasks,
        "task": cmd_task,
        "submit": cmd_submit,
        "approve": cmd_approve,
    }
    try:
        return handlers[command](args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except APIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return dispatch(args)


if __name__ == "__main__":
    raise SystemExit(main())
