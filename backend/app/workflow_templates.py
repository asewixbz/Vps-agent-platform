from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from textwrap import dedent
from typing import Any

DEFAULT_WORKFLOW_TEMPLATE_NAMES = ("scan_workflow", "rank_workflow", "report_workflow", "compare_workflow")
DEFAULT_WORKFLOW_TEMPLATE_KINDS = ("scan", "rank", "report", "compare")


@dataclass(frozen=True)
class WorkflowTemplateStep:
    title: str
    kind: str
    description: str
    tool_name: str | None = None
    requires_approval: bool = False


@dataclass(frozen=True)
class WorkflowTemplate:
    name: str
    kind: str
    summary: str
    steps: list[WorkflowTemplateStep]
    recommended_tool: str | None = None
    requires_approval: bool = False
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _normalize_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_structure(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, list):
        return [_normalize_structure(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_structure(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _normalize_notes(raw_notes: Any) -> list[str]:
    if not isinstance(raw_notes, list):
        return []
    return [str(item) for item in raw_notes if item is not None]


def _normalize_metadata(raw_metadata: Any) -> dict[str, Any]:
    normalized = _normalize_structure(raw_metadata)
    return normalized if isinstance(normalized, dict) else {}


def _normalize_steps(raw_steps: Any) -> list[WorkflowTemplateStep] | None:
    if not isinstance(raw_steps, list) or not raw_steps:
        return None

    steps: list[WorkflowTemplateStep] = []
    for item in raw_steps:
        if not isinstance(item, dict):
            return None

        title = str(item.get("title") or "").strip()
        kind = str(item.get("kind") or "inspect").strip() or "inspect"
        description = str(item.get("description") or "").strip()
        tool_name = item.get("tool_name")
        if tool_name in {"", None}:
            tool_name = None
        if not title or not description:
            return None
        if kind == "execute" and tool_name is None:
            return None

        steps.append(
            WorkflowTemplateStep(
                title=title,
                kind=kind,
                description=description,
                tool_name=str(tool_name) if tool_name is not None else None,
                requires_approval=bool(item.get("requires_approval") or False),
            )
        )
    return steps


def normalize_workflow_template(raw_template: Any) -> WorkflowTemplate | None:
    if not isinstance(raw_template, dict):
        return None

    name = str(raw_template.get("name") or raw_template.get("template_name") or "").strip()
    kind = str(raw_template.get("kind") or raw_template.get("template_kind") or "workflow").strip() or "workflow"
    steps = _normalize_steps(raw_template.get("steps"))
    if not name or steps is None:
        return None

    summary = str(raw_template.get("summary") or "").strip()
    if not summary:
        summary = f"Workflow template: {name}"

    recommended_tool = raw_template.get("recommended_tool")
    if recommended_tool in {None, ""}:
        recommended_tool = None

    return WorkflowTemplate(
        name=name,
        kind=kind,
        summary=summary,
        steps=steps,
        recommended_tool=str(recommended_tool) if recommended_tool is not None else None,
        requires_approval=bool(raw_template.get("requires_approval") or False),
        notes=_normalize_notes(raw_template.get("notes")),
        metadata=_normalize_metadata(raw_template.get("metadata")),
    )


def workflow_template_to_dict(template: WorkflowTemplate) -> dict[str, Any]:
    data = asdict(template)
    return data


def _python_string_literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _build_report_workflow_script(template: WorkflowTemplate, workflow_inputs: dict[str, Any]) -> str:
    template_json = json.dumps(workflow_template_to_dict(template), ensure_ascii=False, sort_keys=True)
    inputs_json = json.dumps(_normalize_structure(workflow_inputs), ensure_ascii=False, sort_keys=True)
    lines = [
        "from __future__ import annotations",
        "",
        "import json",
        "from pathlib import Path",
        "",
        f"TEMPLATE = json.loads({_python_string_literal(template_json)})",
        f"INPUTS = json.loads({_python_string_literal(inputs_json)})",
        "WORKDIR = Path.cwd()",
        "",
        "def _write_text(path: Path, text: str) -> Path:",
        "    path.write_text(text, encoding=\"utf-8\")",
        "    return path",
        "",
        "def _write_json(path: Path, payload: object) -> Path:",
        "    return _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + \"\\n\")",
        "",
        "def _as_list(value: object) -> list[object]:",
        "    if isinstance(value, list):",
        "        return value",
        "    if isinstance(value, dict):",
        "        return [{\"key\": key, \"value\": value[key]} for key in sorted(value)]",
        "    if value is None:",
        "        return []",
        "    return [value]",
        "",
        "def _stringify(value: object) -> str:",
        "    if value is None:",
        "        return \"\"",
        "    if isinstance(value, str):",
        "        return value",
        "    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)",
        "",
        "def _report_result() -> dict[str, object]:",
        "    title = str(INPUTS.get(\"report_title\") or INPUTS.get(\"title\") or TEMPLATE[\"summary\"])",
        "    audience = str(INPUTS.get(\"audience\") or \"general\")",
        "    output_constraints = _as_list(INPUTS.get(\"output_constraints\"))",
        "    source_data = INPUTS.get(\"source_data\")",
        "    source_items = _as_list(source_data)",
        "    report = {",
        "        \"template_name\": TEMPLATE[\"name\"],",
        "        \"template_kind\": TEMPLATE[\"kind\"],",
        "        \"title\": title,",
        "        \"audience\": audience,",
        "        \"output_constraints\": output_constraints,",
        "        \"source_data\": source_data,",
        "        \"source_count\": len(source_items),",
        "        \"sections\": [",
        "            {\"heading\": \"Overview\", \"body\": f\"{title} for {audience}\"},",
        "            {\"heading\": \"Source data\", \"body\": _stringify(source_data)},",
        "            {\"heading\": \"Output constraints\", \"body\": _stringify(output_constraints)},",
        "        ],",
        "        \"artifact_paths\": [],",
        "    }",
        "    json_path = WORKDIR / \"report.json\"",
        "    md_path = WORKDIR / \"report.md\"",
        "    report[\"artifact_paths\"] = [str(json_path), str(md_path)]",
        "    _write_json(json_path, report)",
        "    md_lines = [",
        "        f\"# {title}\",",
        "        \"\",",
        "        f\"Audience: {audience}\",",
        "        f\"Source count: {len(source_items)}\",",
        "        \"\",",
        "        \"## Source data\",",
        "        _stringify(source_data),",
        "        \"\",",
        "        \"## Output constraints\",",
        "        _stringify(output_constraints),",
        "    ]",
        "    _write_text(md_path, \"\\n\".join(md_lines).rstrip() + \"\\n\")",
        "    return report",
        "",
        "def _score_candidate(candidate: object, criteria: object) -> tuple[float, list[str]]:",
        "    candidate_dict = candidate if isinstance(candidate, dict) else {\"value\": candidate}",
        "    score = 0.0",
        "    rationale: list[str] = []",
        "",
        "    def _missing(value: object) -> bool:",
        "        return value in {None, \"\", [], {}}",
        "",
        "    if isinstance(criteria, dict):",
        "        required_fields = criteria.get(\"required_fields\")",
        "        if isinstance(required_fields, list):",
        "            for field in required_fields:",
        "                key = str(field)",
        "                if _missing(candidate_dict.get(key)):",
        "                    score -= 1000.0",
        "                    rationale.append(f\"{key} missing -> -1000\")",
        "",
        "        preferred_values = criteria.get(\"preferred_values\") if isinstance(criteria.get(\"preferred_values\"), dict) else {}",
        "        weights = criteria.get(\"weights\")",
        "        if isinstance(weights, dict):",
        "            for field in sorted(weights, key=lambda item: str(item)):",
        "                weight = weights[field]",
        "                if not isinstance(weight, (int, float)):",
        "                    continue",
        "                key = str(field)",
        "                value = candidate_dict.get(key)",
        "                if key in preferred_values:",
        "                    if value == preferred_values[key]:",
        "                        score += float(weight)",
        "                        rationale.append(f\"{key} matched preferred value -> +{weight}\")",
        "                    else:",
        "                        rationale.append(f\"{key} did not match preferred value -> +0\")",
        "                elif isinstance(value, (int, float)):",
        "                    contribution = float(value) * float(weight)",
        "                    score += contribution",
        "                    rationale.append(f\"{key}={value} * {weight} -> {contribution}\")",
        "                elif value:",
        "                    score += float(weight)",
        "                    rationale.append(f\"{key} present -> +{weight}\")",
        "                else:",
        "                    rationale.append(f\"{key} missing -> +0\")",
        "    elif isinstance(criteria, list):",
        "        for rule in criteria:",
        "            if not isinstance(rule, dict):",
        "                continue",
        "            key = str(rule.get(\"field\") or \"value\")",
        "            weight = rule.get(\"weight\", 1)",
        "            if not isinstance(weight, (int, float)):",
        "                weight = 1",
        "            preferred = rule.get(\"preferred\")",
        "            required = bool(rule.get(\"required\") or False)",
        "            value = candidate_dict.get(key)",
        "            if required and _missing(value):",
        "                score -= 1000.0",
        "                rationale.append(f\"{key} missing -> -1000\")",
        "                continue",
        "            if preferred is not None:",
        "                if value == preferred:",
        "                    score += float(weight)",
        "                    rationale.append(f\"{key} matched preferred value -> +{weight}\")",
        "                else:",
        "                    rationale.append(f\"{key} did not match preferred value -> +0\")",
        "                continue",
        "            if isinstance(value, (int, float)):",
        "                contribution = float(value) * float(weight)",
        "                score += contribution",
        "                rationale.append(f\"{key}={value} * {weight} -> {contribution}\")",
        "            elif value:",
        "                score += float(weight)",
        "                rationale.append(f\"{key} present -> +{weight}\")",
        "            else:",
        "                rationale.append(f\"{key} missing -> +0\")",
        "    else:",
        "        for key in sorted(candidate_dict, key=lambda item: str(item)):",
        "            value = candidate_dict[key]",
        "            if isinstance(value, (int, float)):",
        "                score += float(value)",
        "                rationale.append(f\"{key}={value} -> +{value}\")",
        "            elif value:",
        "                score += 1.0",
        "                rationale.append(f\"{key} present -> +1\")",
        "",
        "    return score, rationale",
        "",
        "def _rank_result() -> dict[str, object]:",
        "    criteria = INPUTS.get(\"criteria\") or INPUTS.get(\"ranking_criteria\") or INPUTS.get(\"weights\")",
        "    candidates = _as_list(INPUTS.get(\"candidates\"))",
        "    ranked_candidates = []",
        "    for index, candidate in enumerate(candidates):",
        "        candidate_dict = candidate if isinstance(candidate, dict) else {\"value\": candidate}",
        "        score, rationale = _score_candidate(candidate_dict, criteria)",
        "        ranked_candidates.append({",
        "            \"candidate\": candidate_dict,",
        "            \"score\": score,",
        "            \"rationale\": rationale,",
        "            \"original_index\": index,",
        "        })",
        "",
        "    ranked_candidates.sort(",
        "        key=lambda item: (",
        "            -float(item[\"score\"]),",
        "            json.dumps(item[\"candidate\"], ensure_ascii=False, sort_keys=True),",
        "            item[\"original_index\"],",
        "        )",
        "    )",
        "",
        "    result = {",
        "        \"template_name\": TEMPLATE[\"name\"],",
        "        \"template_kind\": TEMPLATE[\"kind\"],",
        "        \"criteria\": criteria,",
        "        \"candidate_count\": len(candidates),",
        "        \"ranked_candidates\": ranked_candidates,",
        "        \"artifact_paths\": [],",
        "    }",
        "    json_path = WORKDIR / \"ranking.json\"",
        "    md_path = WORKDIR / \"ranking.md\"",
        "    result[\"artifact_paths\"] = [str(json_path), str(md_path)]",
        "    _write_json(json_path, result)",
        "    md_lines = [",
        "        f\"# {TEMPLATE['summary']}\",",
        "        \"\",",
        "        f\"Criteria: {_stringify(criteria)}\",",
        "        \"\",",
        "        \"## Ranked candidates\",",
        "    ]",
        "    for item in ranked_candidates:",
        "        md_lines.append(f\"- score={item['score']}: {_stringify(item['candidate'])}\")",
        "        for note in item['rationale']:",
        "            md_lines.append(f\"  - {note}\")",
        "    _write_text(md_path, \"\\n\".join(md_lines).rstrip() + \"\\n\")",
        "    return result",
        "",
        "def _scan_result() -> dict[str, object]:",
        "    source_items = _as_list(INPUTS.get(\"source_items\") or INPUTS.get(\"sources\") or INPUTS.get(\"items\"))",
        "    filters = INPUTS.get(\"filters\")",
        "    normalized_items = []",
        "    seen = set()",
        "    duplicate_count = 0",
        "    for item in source_items:",
        "        item_dict = item if isinstance(item, dict) else {\"value\": item}",
        "        marker = json.dumps(item_dict, ensure_ascii=False, sort_keys=True)",
        "        if marker in seen:",
        "            duplicate_count += 1",
        "            continue",
        "        seen.add(marker)",
        "        normalized_items.append(item_dict)",
        "",
        "    result = {",
        "        \"template_name\": TEMPLATE[\"name\"],",
        "        \"template_kind\": TEMPLATE[\"kind\"],",
        "        \"filters\": filters,",
        "        \"source_count\": len(source_items),",
        "        \"duplicate_count\": duplicate_count,",
        "        \"normalized_items\": normalized_items,",
        "        \"artifact_paths\": [],",
        "    }",
        "    json_path = WORKDIR / \"scan.json\"",
        "    md_path = WORKDIR / \"scan.md\"",
        "    result[\"artifact_paths\"] = [str(json_path), str(md_path)]",
        "    _write_json(json_path, result)",
        "    md_lines = [",
        "        f\"# {TEMPLATE['summary']}\",",
        "        \"\",",
        "        f\"Source count: {len(source_items)}\",",
        "        f\"Duplicate count: {duplicate_count}\",",
        "        \"\",",
        "        \"## Normalized items\",",
        "    ]",
        "    for item in normalized_items:",
        "        md_lines.append(f\"- {_stringify(item)}\")",
        "    _write_text(md_path, \"\\n\".join(md_lines).rstrip() + \"\\n\")",
        "    return result",
        "",
        "def _compare_result() -> dict[str, object]:",
        "    left_label = str(INPUTS.get(\"left_label\") or INPUTS.get(\"left_title\") or \"left\")",
        "    right_label = str(INPUTS.get(\"right_label\") or INPUTS.get(\"right_title\") or \"right\")",
        "    left_items = _as_list(INPUTS.get(\"left_items\") or INPUTS.get(\"left_data\") or INPUTS.get(\"left\"))",
        "    right_items = _as_list(INPUTS.get(\"right_items\") or INPUTS.get(\"right_data\") or INPUTS.get(\"right\"))",
        "",
        "    def _item_key(value: object) -> str:",
        "        normalized = value if isinstance(value, dict) else {\"value\": value}",
        "        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)",
        "",
        "    left_index: dict[str, object] = {}",
        "    right_index: dict[str, object] = {}",
        "    left_keys: list[str] = []",
        "    right_keys: list[str] = []",
        "    for item in left_items:",
        "        key = _item_key(item)",
        "        left_index.setdefault(key, item if isinstance(item, dict) else {\"value\": item})",
        "        left_keys.append(key)",
        "    for item in right_items:",
        "        key = _item_key(item)",
        "        right_index.setdefault(key, item if isinstance(item, dict) else {\"value\": item})",
        "        right_keys.append(key)",
        "",
        "    shared_keys = [key for key in left_keys if key in right_index]",
        "    unique_left_keys = [key for key in left_keys if key not in right_index]",
        "    unique_right_keys = [key for key in right_keys if key not in left_index]",
        "",
        "    def _materialize(keys: list[str], index: dict[str, object]) -> list[object]:",
        "        materialized: list[object] = []",
        "        seen: set[str] = set()",
        "        for key in keys:",
        "            if key in seen:",
        "                continue",
        "            seen.add(key)",
        "            materialized.append(index[key])",
        "        return materialized",
        "",
        "    shared_items = _materialize(shared_keys, left_index)",
        "    unique_left_items = _materialize(unique_left_keys, left_index)",
        "    unique_right_items = _materialize(unique_right_keys, right_index)",
        "    summary = (",
        "        f\"Compared {len(left_items)} {left_label} items against {len(right_items)} {right_label} items; \"",
        "        f\"{len(shared_items)} shared, {len(unique_left_items)} unique to {left_label}, \"",
        "        f\"{len(unique_right_items)} unique to {right_label}.\"",
        "    )",
        "    result = {",
        "        \"template_name\": TEMPLATE[\"name\"],",
        "        \"template_kind\": TEMPLATE[\"kind\"],",
        "        \"left_label\": left_label,",
        "        \"right_label\": right_label,",
        "        \"left_count\": len(left_items),",
        "        \"right_count\": len(right_items),",
        "        \"shared_count\": len(shared_items),",
        "        \"unique_left_count\": len(unique_left_items),",
        "        \"unique_right_count\": len(unique_right_items),",
        "        \"summary\": summary,",
        "        \"shared_items\": shared_items,",
        "        \"unique_left_items\": unique_left_items,",
        "        \"unique_right_items\": unique_right_items,",
        "        \"artifact_paths\": [],",
        "    }",
        "    json_path = WORKDIR / \"compare.json\"",
        "    md_path = WORKDIR / \"compare.md\"",
        "    result[\"artifact_paths\"] = [str(json_path), str(md_path)]",
        "    _write_json(json_path, result)",
        "    md_lines = [",
        "        f\"# {TEMPLATE['summary']}\",",
        "        \"\",",
        "        summary,",
        "        \"\",",
        "        f\"Left: {left_label} ({len(left_items)} items)\",",
        "        f\"Right: {right_label} ({len(right_items)} items)\",",
        "        f\"Shared: {len(shared_items)}\",",
        "        f\"Unique to {left_label}: {len(unique_left_items)}\",",
        "        f\"Unique to {right_label}: {len(unique_right_items)}\",",
        "        \"\",",
        "        \"## Shared items\",",
        "    ]",
        "    for item in shared_items:",
        "        md_lines.append(f\"- {_stringify(item)}\")",
        "    md_lines.extend([\"\", f\"## Unique to {left_label}\"])",
        "    for item in unique_left_items:",
        "        md_lines.append(f\"- {_stringify(item)}\")",
        "    md_lines.extend([\"\", f\"## Unique to {right_label}\"])",
        "    for item in unique_right_items:",
        "        md_lines.append(f\"- {_stringify(item)}\")",
        "    _write_text(md_path, \"\\n\".join(md_lines).rstrip() + \"\\n\")",
        "    return result",
        "",
        "def _workflow_result() -> dict[str, object]:",
        "    if TEMPLATE[\"kind\"] == \"rank\":",
        "        return _rank_result()",
        "    if TEMPLATE[\"kind\"] == \"scan\":",
        "        return _scan_result()",
        "    if TEMPLATE[\"kind\"] == \"compare\":",
        "        return _compare_result()",
        "    return _report_result()",
        "",
        "if __name__ == \"__main__\":",
        "    result = _workflow_result()",
        "    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))",
    ]
    return "\n".join(lines) + "\n"


def _build_schedule_workflow_script(template: WorkflowTemplate, workflow_inputs: dict[str, Any]) -> str:
    script = _build_report_workflow_script(template, workflow_inputs)
    replacements = (
        ('def _report_result() -> dict[str, object]:', 'def _schedule_result() -> dict[str, object]:'),
        ('    title = str(INPUTS.get("report_title") or INPUTS.get("title") or TEMPLATE["summary"])', '    title = str(INPUTS.get("schedule_title") or INPUTS.get("title") or TEMPLATE["summary"])'),
        ('    audience = str(INPUTS.get("audience") or "general")\n    output_constraints = _as_list(INPUTS.get("output_constraints"))', '    audience = str(INPUTS.get("audience") or "general")\n    cadence = str(INPUTS.get("cadence") or INPUTS.get("schedule") or INPUTS.get("schedule_cadence") or "manual")\n    timezone = str(INPUTS.get("timezone") or INPUTS.get("schedule_timezone") or "UTC")\n    target_workflow = str(INPUTS.get("target_workflow") or INPUTS.get("target_workflow_name") or TEMPLATE["name"])\n    target_goal = str(INPUTS.get("target_goal") or INPUTS.get("goal") or TEMPLATE["summary"])\n    target_inputs = INPUTS.get("target_inputs")\n    if not isinstance(target_inputs, dict):\n        workflow_inputs = INPUTS.get("workflow_inputs")\n        target_inputs = workflow_inputs if isinstance(workflow_inputs, dict) else {}\n    output_constraints = _as_list(INPUTS.get("output_constraints"))'),
        ('        "audience": audience,', '        "audience": audience,\n        "cadence": cadence,\n        "timezone": timezone,\n        "target_workflow": target_workflow,\n        "target_goal": target_goal,\n        "target_inputs": target_inputs,'),
        ('            {"heading": "Overview", "body": f"{title} for {audience}"},', '            {"heading": "Overview", "body": f"{title} for {audience}"},\n            {"heading": "Schedule", "body": f"Cadence: {cadence}\\nTimezone: {timezone}\\nTarget workflow: {target_workflow}\\nTarget goal: {target_goal}\\nTarget inputs: {_stringify(target_inputs)}"},'),
        ('        f"Audience: {audience}",', '        f"Audience: {audience}",\n        f"Cadence: {cadence}",\n        f"Timezone: {timezone}",\n        f"Target workflow: {target_workflow}",\n        f"Target goal: {target_goal}",\n        f"Target inputs: {_stringify(target_inputs)}",'),
        ('    report = {', '    schedule = {'),
        ('    report["artifact_paths"] = [str(json_path), str(md_path)]', '    schedule["artifact_paths"] = [str(json_path), str(md_path)]'),
        ('    json_path = WORKDIR / "report.json"', '    json_path = WORKDIR / "schedule.json"'),
        ('    md_path = WORKDIR / "report.md"', '    md_path = WORKDIR / "schedule.md"'),
        ('    _write_json(json_path, report)', '    _write_json(json_path, schedule)'),
        ('    return report', '    return schedule'),
        ('    if TEMPLATE["kind"] == "compare":\n        return _compare_result()\n    return _report_result()', '    if TEMPLATE["kind"] == "compare":\n        return _compare_result()\n    if TEMPLATE["kind"] == "schedule":\n        return _schedule_result()\n    return _report_result()'),
    )
    for old, new in replacements:
        script = script.replace(old, new)
    return script


def _build_rank_workflow_script(template: WorkflowTemplate, workflow_inputs: dict[str, Any]) -> str:
    return _build_report_workflow_script(template, workflow_inputs) if template.kind == "report" else _build_report_workflow_script(template, workflow_inputs) if template.kind == "workflow" else _build_report_workflow_script(template, workflow_inputs)


def _build_scan_workflow_script(template: WorkflowTemplate, workflow_inputs: dict[str, Any]) -> str:
    return _build_report_workflow_script(template, workflow_inputs) if template.kind == "report" else _build_report_workflow_script(template, workflow_inputs) if template.kind == "workflow" else _build_report_workflow_script(template, workflow_inputs)


def workflow_template_execution_payloads(template: WorkflowTemplate, workflow_inputs: Any | None = None) -> dict[str, dict[str, Any]]:
    normalized_inputs = _normalize_structure(workflow_inputs) if workflow_inputs is not None else {}
    if not isinstance(normalized_inputs, dict):
        normalized_inputs = {}

    payloads: dict[str, dict[str, Any]] = {}
    for step in template.steps:
        if step.kind != "execute" or step.tool_name is None:
            continue
        if step.tool_name in payloads:
            continue
        if step.tool_name == "python_local":
            if template.kind == "rank":
                script = _build_rank_workflow_script(template, normalized_inputs)
            elif template.kind == "scan":
                script = _build_scan_workflow_script(template, normalized_inputs)
            elif template.kind == "schedule":
                script = _build_schedule_workflow_script(template, normalized_inputs)
            elif template.kind == "compare":
                script = _build_report_workflow_script(template, normalized_inputs)
            else:
                script = _build_report_workflow_script(template, normalized_inputs)
            payloads[step.tool_name] = {"script": script}
        else:
            payloads[step.tool_name] = {}
    return payloads


def build_workflow_template_context(
    template: WorkflowTemplate,
    *,
    workflow_inputs: Any | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_context = dict(context or {})
    if workflow_inputs is None:
        workflow_inputs = normalized_context.get("workflow_inputs")

    normalized_inputs = _normalize_structure(workflow_inputs) if workflow_inputs is not None else {}
    if not isinstance(normalized_inputs, dict):
        normalized_inputs = {}

    generated_payloads = workflow_template_execution_payloads(template, normalized_inputs)
    if generated_payloads:
        payload_by_tool = normalized_context.get("payload_by_tool")
        if isinstance(payload_by_tool, dict):
            merged_payloads = dict(payload_by_tool)
        else:
            merged_payloads = {}

        tool_payloads = normalized_context.get("tool_payloads")
        if isinstance(tool_payloads, dict):
            for key, value in tool_payloads.items():
                merged_payloads.setdefault(str(key), value)

        for tool_name, payload in generated_payloads.items():
            merged_payloads.setdefault(tool_name, payload)

        normalized_context["payload_by_tool"] = merged_payloads
        normalized_context["tool_payloads"] = merged_payloads

    normalized_context["workflow_template_name"] = template.name
    normalized_context["workflow_template"] = workflow_template_to_dict(template)
    normalized_context["workflow_inputs"] = normalized_inputs
    return normalized_context


def default_workflow_templates() -> dict[str, WorkflowTemplate]:
    templates = [
        WorkflowTemplate(
            name="scan_workflow",
            kind="scan",
            summary="Scan a source set and normalize the items for downstream workflows.",
            recommended_tool="python_local",
            steps=[
                WorkflowTemplateStep(
                    title="Collect scan inputs",
                    kind="inspect",
                    description="Collect the source set, inclusion rules, and any required filters before scanning.",
                ),
                WorkflowTemplateStep(
                    title="Run the scan",
                    kind="execute",
                    description="Scan the inputs and normalize them into structured results.",
                    tool_name="python_local",
                ),
                WorkflowTemplateStep(
                    title="Verify scan output",
                    kind="verify",
                    description="Check the scan output for missing items, duplicates, and obvious mismatches.",
                ),
            ],
            notes=["Phase 5 template for repeatable scanning workflows."],
            metadata={"phase": 5, "category": "scan"},
        ),
        WorkflowTemplate(
            name="rank_workflow",
            kind="rank",
            summary="Rank items against the supplied criteria using a fixed workflow template.",
            recommended_tool="python_local",
            steps=[
                WorkflowTemplateStep(
                    title="Collect ranking criteria",
                    kind="inspect",
                    description="Collect the ranking criteria, weighting rules, and the candidate items to score.",
                ),
                WorkflowTemplateStep(
                    title="Score the candidates",
                    kind="execute",
                    description="Apply the ranking criteria and produce an ordered result set.",
                    tool_name="python_local",
                ),
                WorkflowTemplateStep(
                    title="Verify the ranking",
                    kind="verify",
                    description="Check the ranking for ties, outliers, and missing rationale.",
                ),
            ],
            notes=["Phase 5 template for repeatable ranking workflows."],
            metadata={"phase": 5, "category": "rank"},
        ),
        WorkflowTemplate(
            name="report_workflow",
            kind="report",
            summary="Generate a concise report from workflow inputs with a fixed template.",
            recommended_tool="python_local",
            steps=[
                WorkflowTemplateStep(
                    title="Collect reporting inputs",
                    kind="inspect",
                    description="Collect the data source, audience, and report constraints before generation.",
                ),
                WorkflowTemplateStep(
                    title="Build the report",
                    kind="execute",
                    description="Assemble the report and supporting summary from the supplied inputs.",
                    tool_name="python_local",
                ),
                WorkflowTemplateStep(
                    title="Verify the report",
                    kind="verify",
                    description="Check the report for omissions, unsupported claims, and formatting issues.",
                ),
            ],
            notes=["Phase 5 template for repeatable report generation workflows."],
            metadata={"phase": 5, "category": "report"},
        ),
        WorkflowTemplate(
            name="compare_workflow",
            kind="compare",
            summary="Compare two item sets and highlight shared and unique items.",
            recommended_tool="python_local",
            steps=[
                WorkflowTemplateStep(
                    title="Collect comparison inputs",
                    kind="inspect",
                    description="Collect the left and right item sets, labels, and any comparison constraints before running the workflow.",
                ),
                WorkflowTemplateStep(
                    title="Run the comparison",
                    kind="execute",
                    description="Compare the input sets and produce structured shared and unique item output.",
                    tool_name="python_local",
                ),
                WorkflowTemplateStep(
                    title="Verify the comparison",
                    kind="verify",
                    description="Check the comparison for missing items, unexpected overlaps, and clear summaries.",
                ),
            ],
            notes=["Phase 5 template for repeatable comparison workflows."],
            metadata={"phase": 5, "category": "compare"},
        ),
        WorkflowTemplate(
            name="schedule_workflow",
            kind="schedule",
            summary="Plan a recurring run for a target workflow using cadence and timezone inputs.",
            recommended_tool="python_local",
            steps=[
                WorkflowTemplateStep(
                    title="Collect schedule inputs",
                    kind="inspect",
                    description="Collect the cadence, timezone, target workflow, and supporting inputs before building the schedule.",
                ),
                WorkflowTemplateStep(
                    title="Build the schedule",
                    kind="execute",
                    description="Generate a schedule artifact for the requested workflow.",
                    tool_name="python_local",
                ),
                WorkflowTemplateStep(
                    title="Verify the schedule",
                    kind="verify",
                    description="Check the schedule for missing cadence, timezone, or target workflow details.",
                ),
            ],
            notes=["Phase 5 template for repeatable scheduling workflows."],
            metadata={"phase": 5, "category": "schedule"},
        ),
    ]
    return {template.name: template for template in templates}


def _lookup_template_from_registry(registry: Any, template_name: str) -> Any:
    if isinstance(registry, dict):
        return registry.get(template_name)
    if isinstance(registry, list):
        for item in registry:
            if isinstance(item, dict) and str(item.get("name") or "") == template_name:
                return item
    return None


def resolve_workflow_template(context: dict[str, Any] | None) -> WorkflowTemplate | None:
    normalized_context = dict(context or {})

    direct_template = normalized_context.get("workflow_template")
    if isinstance(direct_template, str):
        direct_template = _lookup_template_from_registry(default_workflow_templates(), direct_template)
    template = normalize_workflow_template(direct_template)
    if template is not None:
        return template

    template_name = normalized_context.get("workflow_template_name")
    if not isinstance(template_name, str) or not template_name.strip():
        return None
    template_name = template_name.strip()

    registry = normalized_context.get("workflow_templates")
    registry_template = _lookup_template_from_registry(registry, template_name)
    if registry_template is None:
        registry_template = default_workflow_templates().get(template_name)

    return normalize_workflow_template(registry_template)
