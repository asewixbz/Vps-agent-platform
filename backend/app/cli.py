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


def _truncate(text: str, limit: int = 72) -> str:
    cleaned = text.replace("\n", " ").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def format_runtime_run_row(run: dict[str, Any]) -> str:
    checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
    steps = run.get("steps") if isinstance(run.get("steps"), list) else []
    goal = _truncate(str(run.get("goal") or ""), 56)
    return (
        f"{run.get('id', ''):<36} {run.get('status', ''):<14} "
        f"attempts={int(run.get('attempts') or 0):<2} steps={len(steps):<3} "
        f"next={checkpoint.get('next_step_index', '-'):>3}  {goal}"
    )


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


def cmd_runs(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, "/agent/runs")
    if args.json:
        print_json(data)
    else:
        for run in data:
            print(format_runtime_run_row(run))
    return 0


def cmd_run_show(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, f"/agent/runs/{args.runtime_run_id}")
    if args.json:
        print_json(data)
    else:
        print(f"id: {data.get('id')}")
        print(f"goal: {data.get('goal')}")
        print(f"status: {data.get('status')}")
        print(f"attempts: {data.get('attempts')}")
        if data.get("summary"):
            print(f"summary: {data.get('summary')}")
        if data.get("blocked_reason"):
            print(f"blocked_reason: {data.get('blocked_reason')}")
        if data.get("resume_hint"):
            print(f"resume_hint: {data.get('resume_hint')}")
        checkpoint = data.get("checkpoint") or {}
        if checkpoint:
            print("checkpoint:")
            print(f"  next_step_index: {checkpoint.get('next_step_index')}")
            print(f"  completed_step_count: {checkpoint.get('completed_step_count')}")
            print(f"  total_steps: {checkpoint.get('total_steps')}")
            if checkpoint.get("blocked_step_index") is not None:
                print(f"  blocked_step_index: {checkpoint.get('blocked_step_index')}")
            if checkpoint.get("completed_step_indices"):
                print(f"  completed_step_indices: {checkpoint.get('completed_step_indices')}")
        steps = data.get("steps") or []
        if steps:
            print("steps:")
            for step in steps:
                line = f"  [{step.get('status')}] {step.get('title')}"
                if step.get("tool_name"):
                    line += f" (tool: {step.get('tool_name')})"
                print(line)
                if step.get("task_id"):
                    print(f"     task_id: {step.get('task_id')}")
                if step.get("detail"):
                    print(f"     {step.get('detail')}")
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


def cmd_model_health(args: argparse.Namespace) -> int:
    data = request_json("GET", args.base_url, "/model/health")
    if args.json:
        print_json(data)
    else:
        print(f"status: {data.get('status')}")
        print(f"adapter: {data.get('adapter')}")
        print(f"message: {data.get('message')}")
    return 0


def cmd_model_chat(args: argparse.Namespace) -> int:
    payload = load_payload(args.payload, args.payload_file)
    data = request_json("POST", args.base_url, "/model/chat", {"payload": payload})
    if args.json:
        print_json(data)
    else:
        print(f"model: {data.get('model')}")
        print(f"provider: {data.get('provider')}")
        if data.get("finish_reason"):
            print(f"finish_reason: {data.get('finish_reason')}")
        if data.get("text"):
            print(data.get("text"))
        if data.get("tool_calls"):
            print("tool_calls:")
            print(json.dumps(data.get("tool_calls"), indent=2, ensure_ascii=False))
        if data.get("structured_data") is not None:
            print("structured_data:")
            print(json.dumps(data.get("structured_data"), indent=2, ensure_ascii=False))
    return 0


def _print_checkpoint(data: dict[str, Any]) -> None:
    checkpoint = data.get("checkpoint") or {}
    if not checkpoint:
        return
    print("checkpoint:")
    print(f"  next_step_index: {checkpoint.get('next_step_index')}")
    print(f"  completed_step_count: {checkpoint.get('completed_step_count')}")
    print(f"  total_steps: {checkpoint.get('total_steps')}")
    if checkpoint.get("blocked_step_index") is not None:
        print(f"  blocked_step_index: {checkpoint.get('blocked_step_index')}")
    if checkpoint.get("completed_step_indices"):
        print(f"  completed_step_indices: {checkpoint.get('completed_step_indices')}")
    if data.get("resume_hint"):
        print(f"resume_hint: {data.get('resume_hint')}")


def cmd_plan(args: argparse.Namespace) -> int:
    context = load_metadata(args.context, args.context_file)
    data = request_json(
        "POST",
        args.base_url,
        "/agent/plan",
        {
            "goal": args.goal,
            "context": context,
        },
    )
    if args.json:
        print_json(data)
    else:
        print(f"source: {data.get('source')}")
        print(f"summary: {data.get('summary')}")
        if data.get("recommended_tool"):
            print(f"recommended_tool: {data.get('recommended_tool')}")
        print(f"requires_approval: {bool(data.get('requires_approval'))}")
        notes = data.get("notes") or []
        if notes:
            print("notes:")
            for note in notes:
                print(f"  - {note}")
        steps = data.get("steps") or []
        if steps:
            print("steps:")
            for index, step in enumerate(steps, start=1):
                print(f"  {index}. [{step.get('kind')}] {step.get('title')}")
                if step.get("tool_name"):
                    print(f"     tool: {step.get('tool_name')}")
                if step.get("description"):
                    print(f"     {step.get('description')}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    context = load_metadata(args.context, args.context_file)
    body: dict[str, Any] = {
        "goal": args.goal,
        "context": context,
        "max_steps": args.max_steps,
        "resume_from_step_index": args.resume_from_step,
        "runtime_run_id": args.runtime_run_id,
    }
    data = request_json("POST", args.base_url, "/agent/run", body)
    if args.json:
        print_json(data)
    else:
        print(f"runtime_run_id: {data.get('runtime_run_id')}")
        print(f"status: {data.get('status')}")
        print(f"summary: {data.get('summary')}")
        print(f"iterations: {data.get('iterations')}")
        print(f"attempts: {data.get('attempts')}")
        if data.get("blocked_reason"):
            print(f"blocked_reason: {data.get('blocked_reason')}")
        plan = data.get("plan") or {}
        if plan.get("recommended_tool"):
            print(f"recommended_tool: {plan.get('recommended_tool')}")
        _print_checkpoint(data)
        steps = data.get("steps") or []
        if steps:
            print("steps:")
            for step in steps:
                line = f"  [{step.get('status')}] {step.get('title')}"
                if step.get("tool_name"):
                    line += f" (tool: {step.get('tool_name')})"
                print(line)
                if step.get("task_id"):
                    print(f"     task_id: {step.get('task_id')}")
                if step.get("detail"):
                    print(f"     {step.get('detail')}")
                if step.get("stdout"):
                    print("     stdout:")
                    for line_text in str(step.get("stdout")).splitlines():
                        print(f"       {line_text}")
                if step.get("stderr"):
                    print("     stderr:")
                    for line_text in str(step.get("stderr")).splitlines():
                        print(f"       {line_text}")
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
    subparsers.add_parser("runs", help="list persisted runtime runs")
    subparsers.add_parser("model-health", help="check model adapter health")

    task_parser = subparsers.add_parser("task", help="show a single task")
    task_parser.add_argument("task_id", help="task id")

    run_show_parser = subparsers.add_parser("run-show", help="show a persisted runtime run")
    run_show_parser.add_argument("runtime_run_id", help="runtime run id")

    model_chat_parser = subparsers.add_parser("model-chat", help="call the configured model adapter")
    model_chat_parser.add_argument("--payload", help="JSON payload string")
    model_chat_parser.add_argument("--payload-file", help="path to a JSON payload file, or - for stdin")

    plan_parser = subparsers.add_parser("plan", help="build an execution plan for a goal")
    plan_parser.add_argument("goal", help="goal or task description")
    plan_parser.add_argument("--context", help="JSON context string")
    plan_parser.add_argument("--context-file", help="path to a JSON context file, or - for stdin")

    run_parser = subparsers.add_parser("run", help="run the conservative multi-step runtime loop")
    run_parser.add_argument("goal", help="goal or task description")
    run_parser.add_argument("--context", help="JSON context string")
    run_parser.add_argument("--context-file", help="path to a JSON context file, or - for stdin")
    run_parser.add_argument("--max-steps", type=int, default=5, help="maximum number of runtime steps to process")
    run_parser.add_argument("--resume-from-step", type=int, help="resume runtime execution from a 1-based step index")
    run_parser.add_argument("--runtime-run-id", help="reuse or continue a persisted runtime run")

    register_tool_parser = subparsers.add_parser("register-tool", help="register a tool")
    register_tool_parser.add_argument("name", help="tool name")
    register_tool_parser.add_argument("kind", choices=["python", "shell", "browser", "model", "messaging"], help="tool kind")
    register_tool_parser.add_argument("--description", default="", help="tool description")
    register_tool_parser.add_argument("--entrypoint", help="tool entrypoint")
    register_tool_parser.add_argument("--status", choices=["draft", "tested", "trusted", "blocked"], default="draft", help="tool status")
    register_tool_parser.add_argument("--trust-level", type=int, default=0, help="tool trust level")
    register_tool_parser.add_argument("--metadata", help="JSON metadata string")
    register_tool_parser.add_argument("--metadata-file", help="path to a JSON metadata file, or - for stdin")

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
        "tasks": cmd_tasks,
        "task": cmd_task,
        "runs": cmd_runs,
        "run-show": cmd_run_show,
        "register-tool": cmd_register_tool,
        "submit": cmd_submit,
        "approve": cmd_approve,
        "model-health": cmd_model_health,
        "model-chat": cmd_model_chat,
        "plan": cmd_plan,
        "run": cmd_run,
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
