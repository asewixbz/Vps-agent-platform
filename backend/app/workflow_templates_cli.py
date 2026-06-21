from __future__ import annotations

from typing import Any

WORKFLOW_TEMPLATE_HANDLERS: dict[str, Any] = {}


def _format_template_row(template: dict[str, Any]) -> str:
    name = str(template.get("name") or "")
    kind = str(template.get("kind") or "")
    summary = str(template.get("summary") or "")
    step_count = len(template.get("steps") or [])
    recommended_tool = str(template.get("recommended_tool") or "-")
    return f"{name:<24} {kind:<10} steps={step_count:<2} tool={recommended_tool:<12} {summary}"


def _print_template_details(template: dict[str, Any]) -> None:
    print(f"name: {template.get('name')}")
    print(f"kind: {template.get('kind')}")
    print(f"summary: {template.get('summary')}")
    print(f"recommended_tool: {template.get('recommended_tool') or '-'}")
    print(f"requires_approval: {bool(template.get('requires_approval'))}")

    notes = template.get("notes") if isinstance(template.get("notes"), list) else []
    if notes:
        print("notes:")
        for note in notes:
            print(f"  - {note}")

    metadata = template.get("metadata") if isinstance(template.get("metadata"), dict) else {}
    if metadata:
        print("metadata:")
        import json

        print(json.dumps(metadata, indent=2, ensure_ascii=False))

    steps = template.get("steps") if isinstance(template.get("steps"), list) else []
    if steps:
        print("steps:")
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            print(f"  {index}. [{step.get('kind')}] {step.get('title')}")
            if step.get("tool_name"):
                print(f"     tool: {step.get('tool_name')}")
            if step.get("description"):
                print(f"     {step.get('description')}")


def _format_schedule_row(schedule: dict[str, Any]) -> str:
    schedule_id = str(schedule.get("id") or "")
    status = str(schedule.get("status") or "")
    cadence = str(schedule.get("cadence") or "")
    next_run_at = str(schedule.get("next_run_at") or "-")
    target_workflow = str(schedule.get("target_workflow_name") or "")
    target_goal = str(schedule.get("target_goal") or "")
    return f"{schedule_id:<36} {status:<10} cadence={cadence:<16} next={next_run_at:<30} {target_workflow} :: {target_goal}"


def _print_schedule_details(schedule: dict[str, Any]) -> None:
    print(f"id: {schedule.get('id')}")
    print(f"status: {schedule.get('status')}")
    print(f"source_runtime_run_id: {schedule.get('source_runtime_run_id')}")
    print(f"source_template_name: {schedule.get('source_template_name')}")
    print(f"source_goal: {schedule.get('source_goal')}")
    print(f"cadence: {schedule.get('cadence')}")
    print(f"timezone: {schedule.get('timezone')}")
    print(f"target_workflow_name: {schedule.get('target_workflow_name')}")
    print(f"target_goal: {schedule.get('target_goal')}")
    print(f"next_run_at: {schedule.get('next_run_at') or '-'}")
    print(f"last_triggered_at: {schedule.get('last_triggered_at') or '-'}")
    print(f"last_runtime_run_id: {schedule.get('last_runtime_run_id') or '-'}")
    print(f"last_run_status: {schedule.get('last_run_status') or '-'}")
    if schedule.get("last_run_summary"):
        print(f"last_run_summary: {schedule.get('last_run_summary')}")
    target_inputs = schedule.get("target_inputs") if isinstance(schedule.get("target_inputs"), dict) else {}
    if target_inputs:
        import json

        print("target_inputs:")
        print(json.dumps(target_inputs, indent=2, ensure_ascii=False))


def _print_execution_details(execution: dict[str, Any]) -> None:
    print(f"runtime_run_id: {execution.get('runtime_run_id')}")
    print(f"status: {execution.get('status')}")
    print(f"summary: {execution.get('summary')}")
    print(f"iterations: {execution.get('iterations')}")
    print(f"attempts: {execution.get('attempts')}")
    if execution.get("blocked_reason"):
        print(f"blocked_reason: {execution.get('blocked_reason')}")
    if execution.get("resume_hint"):
        print(f"resume_hint: {execution.get('resume_hint')}")

    checkpoint = execution.get("checkpoint") if isinstance(execution.get("checkpoint"), dict) else {}
    if checkpoint:
        print("checkpoint:")
        print(f"  next_step_index: {checkpoint.get('next_step_index')}")
        print(f"  completed_step_count: {checkpoint.get('completed_step_count')}")
        print(f"  total_steps: {checkpoint.get('total_steps')}")
        if checkpoint.get("blocked_step_index") is not None:
            print(f"  blocked_step_index: {checkpoint.get('blocked_step_index')}")
        if checkpoint.get("completed_step_indices"):
            print(f"  completed_step_indices: {checkpoint.get('completed_step_indices')}")

    steps = execution.get("steps") if isinstance(execution.get("steps"), list) else []
    if steps:
        print("steps:")
        for step in steps:
            if not isinstance(step, dict):
                continue
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


def cmd_workflow_templates(args: Any) -> int:
    from .cli import print_json, request_json

    data = request_json("GET", args.base_url, "/workflow-templates")
    if args.json:
        print_json(data)
    else:
        for template in data:
            if isinstance(template, dict):
                print(_format_template_row(template))
    return 0


def cmd_workflow_template(args: Any) -> int:
    from .cli import print_json, request_json

    data = request_json("GET", args.base_url, f"/workflow-templates/{args.template_name}")
    if args.json:
        print_json(data)
    else:
        _print_template_details(data)
    return 0


def cmd_workflow_template_run(args: Any) -> int:
    from .cli import load_metadata, load_payload, print_json, request_json

    inputs = load_payload(args.inputs, args.inputs_file)
    context = load_metadata(args.context, args.context_file)
    body: dict[str, Any] = {
        "goal": args.goal,
        "inputs": inputs,
        "context": context,
        "max_steps": args.max_steps,
        "resume_from_step_index": args.resume_from_step,
        "runtime_run_id": args.runtime_run_id,
    }
    data = request_json("POST", args.base_url, f"/workflow-templates/{args.template_name}/run", body)
    if args.json:
        print_json(data)
    else:
        template = data.get("workflow_template") if isinstance(data.get("workflow_template"), dict) else {}
        execution = data.get("execution") if isinstance(data.get("execution"), dict) else {}
        if template:
            print(f"workflow_template: {template.get('name')}")
        print(f"goal: {execution.get('goal')}")
        if data.get("schedule"):
            schedule = data.get("schedule") if isinstance(data.get("schedule"), dict) else {}
            print(f"schedule: {schedule.get('id')}")
        if data.get("schedule_registration_error"):
            print(f"schedule_registration_error: {data.get('schedule_registration_error')}")
        _print_execution_details(execution)
    return 0


def cmd_workflow_template_save(args: Any) -> int:
    from .cli import load_payload, print_json, request_json

    payload = load_payload(args.payload, args.payload_file)
    data = request_json("POST", args.base_url, "/workflow-templates", payload)
    if args.json:
        print_json(data)
    else:
        print(f"workflow template saved: {data.get('name')}")
        print(f"kind: {data.get('kind')}")
        print(f"summary: {data.get('summary')}")
        print(f"recommended_tool: {data.get('recommended_tool') or '-'}")
        print(f"requires_approval: {bool(data.get('requires_approval'))}")
    return 0


def cmd_workflow_template_delete(args: Any) -> int:
    from .cli import print_json, request_json

    data = request_json("DELETE", args.base_url, f"/workflow-templates/{args.template_name}")
    if args.json:
        print_json(data)
    else:
        print(f"workflow template deleted: {data.get('template_name')}")
        print(f"deleted: {bool(data.get('deleted'))}")
    return 0


def cmd_workflow_template_compare(args: Any) -> int:
    from .cli import _build_path, print_json, request_json

    path = _build_path(
        f"/workflow-templates/{args.template_name}/compare",
        {
            "left_runtime_run_id": args.left_runtime_run_id,
            "right_runtime_run_id": args.right_runtime_run_id,
        },
    )
    data = request_json("GET", args.base_url, path)
    if args.json:
        print_json(data)
    else:
        workflow_template = data.get("workflow_template") if isinstance(data.get("workflow_template"), dict) else {}
        if workflow_template:
            print(f"workflow_template: {workflow_template.get('name')}")
        comparison = data.get("comparison") if isinstance(data.get("comparison"), dict) else {}
        left = comparison.get("left") if isinstance(comparison.get("left"), dict) else {}
        right = comparison.get("right") if isinstance(comparison.get("right"), dict) else {}
        print(f"left_runtime_run_id: {data.get('left_runtime_run_id')}")
        print(f"right_runtime_run_id: {data.get('right_runtime_run_id')}")
        print(f"left_status: {left.get('status')}")
        print(f"right_status: {right.get('status')}")
        differences = comparison.get("differences") if isinstance(comparison.get("differences"), dict) else {}
        if differences:
            print("differences:")
            for key, value in differences.items():
                if isinstance(value, dict):
                    print(f"  - {key}: {value.get('left')} -> {value.get('right')}")
    return 0


def cmd_workflow_schedules(args: Any) -> int:
    from .cli import print_json, request_json

    data = request_json("GET", args.base_url, "/workflow-schedules")
    if args.json:
        print_json(data)
    else:
        for schedule in data:
            if isinstance(schedule, dict):
                print(_format_schedule_row(schedule))
    return 0


def cmd_workflow_schedule(args: Any) -> int:
    from .cli import print_json, request_json

    data = request_json("GET", args.base_url, f"/workflow-schedules/{args.schedule_id}")
    if args.json:
        print_json(data)
    else:
        _print_schedule_details(data)
    return 0


def cmd_workflow_schedule_dispatch_due(args: Any) -> int:
    from .cli import print_json, request_json

    data = request_json("POST", args.base_url, f"/workflow-schedules/dispatch-due?limit={args.limit}")
    if args.json:
        print_json(data)
    else:
        print(f"count: {data.get('count')}")
        for item in data.get("dispatched") or []:
            if not isinstance(item, dict):
                continue
            schedule = item.get("schedule") if isinstance(item.get("schedule"), dict) else {}
            execution = item.get("execution") if isinstance(item.get("execution"), dict) else {}
            print(f"schedule: {schedule.get('id')}")
            print(f"  status: {schedule.get('status')}")
            print(f"  next_run_at: {schedule.get('next_run_at') or '-'}")
            print(f"  runtime_run_id: {execution.get('runtime_run_id')}")
            print(f"  runtime_status: {execution.get('status')}")
    return 0


def register_workflow_template_cli(subparsers: Any) -> None:
    workflow_templates_parser = subparsers.add_parser("workflow-templates", help="list workflow templates")
    workflow_templates_parser.set_defaults(func=cmd_workflow_templates)

    workflow_template_parser = subparsers.add_parser("workflow-template", help="show a workflow template")
    workflow_template_parser.add_argument("template_name", help="workflow template name")
    workflow_template_parser.set_defaults(func=cmd_workflow_template)

    workflow_template_run_parser = subparsers.add_parser("workflow-template-run", help="run a workflow template")
    workflow_template_run_parser.add_argument("template_name", help="workflow template name")
    workflow_template_run_parser.add_argument("goal", nargs="?", help="optional goal override")
    workflow_template_run_parser.add_argument("--inputs", help="JSON inputs string")
    workflow_template_run_parser.add_argument("--inputs-file", help="path to a JSON inputs file, or - for stdin")
    workflow_template_run_parser.add_argument("--context", help="JSON context string")
    workflow_template_run_parser.add_argument("--context-file", help="path to a JSON context file, or - for stdin")
    workflow_template_run_parser.add_argument("--max-steps", type=int, default=5, help="maximum number of runtime steps to process")
    workflow_template_run_parser.add_argument("--resume-from-step", type=int, help="resume runtime execution from a 1-based step index")
    workflow_template_run_parser.add_argument("--runtime-run-id", help="reuse or continue a persisted runtime run")
    workflow_template_run_parser.set_defaults(func=cmd_workflow_template_run)

    workflow_template_save_parser = subparsers.add_parser("workflow-template-save", help="save a custom workflow template")
    workflow_template_save_parser.add_argument("--payload", help="JSON payload string")
    workflow_template_save_parser.add_argument("--payload-file", help="path to a JSON payload file, or - for stdin")
    workflow_template_save_parser.set_defaults(func=cmd_workflow_template_save)

    workflow_template_delete_parser = subparsers.add_parser("workflow-template-delete", help="delete a custom workflow template")
    workflow_template_delete_parser.add_argument("template_name", help="workflow template name")
    workflow_template_delete_parser.set_defaults(func=cmd_workflow_template_delete)

    workflow_template_compare_parser = subparsers.add_parser("workflow-template-compare", help="compare two workflow template runs")
    workflow_template_compare_parser.add_argument("template_name", help="workflow template name")
    workflow_template_compare_parser.add_argument("left_runtime_run_id", help="left runtime run id")
    workflow_template_compare_parser.add_argument("right_runtime_run_id", help="right runtime run id")
    workflow_template_compare_parser.set_defaults(func=cmd_workflow_template_compare)

    workflow_schedules_parser = subparsers.add_parser("workflow-schedules", help="list workflow schedules")
    workflow_schedules_parser.set_defaults(func=cmd_workflow_schedules)

    workflow_schedule_parser = subparsers.add_parser("workflow-schedule", help="show a workflow schedule")
    workflow_schedule_parser.add_argument("schedule_id", help="workflow schedule id")
    workflow_schedule_parser.set_defaults(func=cmd_workflow_schedule)

    workflow_schedule_dispatch_due_parser = subparsers.add_parser("workflow-schedule-dispatch-due", help="dispatch due workflow schedules")
    workflow_schedule_dispatch_due_parser.add_argument("--limit", type=int, default=10, help="maximum number of due schedules to dispatch")
    workflow_schedule_dispatch_due_parser.set_defaults(func=cmd_workflow_schedule_dispatch_due)

    WORKFLOW_TEMPLATE_HANDLERS.update(
        {
            "workflow-templates": cmd_workflow_templates,
            "workflow-template": cmd_workflow_template,
            "workflow-template-run": cmd_workflow_template_run,
            "workflow-template-save": cmd_workflow_template_save,
            "workflow-template-delete": cmd_workflow_template_delete,
            "workflow-template-compare": cmd_workflow_template_compare,
            "workflow-schedules": cmd_workflow_schedules,
            "workflow-schedule": cmd_workflow_schedule,
            "workflow-schedule-dispatch-due": cmd_workflow_schedule_dispatch_due,
        }
    )
