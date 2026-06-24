from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .settings import Settings

TRUST_LEVEL_LABELS = {
    0: "unreviewed",
    1: "limited",
    2: "trusted",
    3: "privileged",
}

DEFAULT_SHELL_APPROVAL_TRIGGERS = (
    "python -c",
    "python3 -c",
    "bash -c",
    "sh -c",
    "pip install",
    "python -m pip install",
    "git push",
    "git reset",
    "git clean",
    "curl ",
    "wget ",
    "ssh ",
    "scp ",
    "kubectl ",
    "terraform ",
    "docker ",
)

DEFAULT_SHELL_DENY_TRIGGERS = (
    "rm -rf /",
    "rm -rf ~",
    "sudo ",
    "shutdown",
    "reboot",
    "mkfs",
    "curl | sh",
    "wget | sh",
    "chmod 777 /",
    "dd if=",
    "nc ",
    "netcat",
)

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    requires_approval: bool
    decision: str
    reason: str
    reason_code: str
    trust_level: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TimeoutBudget:
    allowed: bool
    timeout_seconds: int
    requested_seconds: int | None
    limit_seconds: int
    reason: str
    reason_code: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepBudget:
    allowed: bool
    max_steps: int
    requested_max_steps: int
    limit_max_steps: int
    reason: str
    reason_code: str
    details: dict[str, Any] = field(default_factory=dict)


def _load_json_mapping(raw: Any) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            items.append(text)
    return items


def _unique_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "trigger"


def _first_trigger(text: str, triggers: list[str]) -> str | None:
    for trigger in triggers:
        if trigger and trigger.lower() in text:
            return trigger
    return None


def _is_external_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"}:
        host = (parsed.hostname or "").lower()
        return host not in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme:
        return True
    return bool(url.strip())


def get_trust_level_label(trust_level: int) -> str:
    return TRUST_LEVEL_LABELS.get(trust_level, f"level_{trust_level}")


def get_tool_policy_overrides(settings: Settings) -> dict[str, Any]:
    return _load_json_mapping(getattr(settings, "tool_policy_overrides_json", "{}"))


def _merge_policy_source(profile: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    merged = dict(profile)
    for key in ("status", "deny_reason", "allow_reason"):
        value = source.get(key)
        if value not in {None, ""}:
            merged[key] = str(value)
    for key in ("trust_level", "timeout_seconds", "max_steps"):
        if key in source and source.get(key) not in {None, ""}:
            merged[key] = _coerce_int(source.get(key), _coerce_int(merged.get(key), 0))
    if "requires_approval" in source and source.get("requires_approval") is not None:
        merged["requires_approval"] = bool(source.get("requires_approval"))
    if "approval_triggers" in source:
        merged["approval_triggers"] = _unique_items(
            [*merged.get("approval_triggers", []), *_coerce_str_list(source.get("approval_triggers"))]
        )
    if "deny_triggers" in source:
        merged["deny_triggers"] = _unique_items([*merged.get("deny_triggers", []), *_coerce_str_list(source.get("deny_triggers"))])
    return merged


def get_tool_policy_profile(settings: Settings, tool: dict[str, Any]) -> dict[str, Any]:
    metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
    overrides = get_tool_policy_overrides(settings)
    profile: dict[str, Any] = {
        "name": str(tool.get("name") or ""),
        "kind": str(tool.get("kind") or ""),
        "status": str(tool.get("status") or ""),
        "trust_level": _coerce_int(tool.get("trust_level"), 0),
        "requires_approval": bool(metadata.get("requires_approval") or False),
        "approval_triggers": list(DEFAULT_SHELL_APPROVAL_TRIGGERS) if str(tool.get("kind") or "") == "shell" else [],
        "deny_triggers": list(DEFAULT_SHELL_DENY_TRIGGERS) if str(tool.get("kind") or "") == "shell" else [],
        "timeout_seconds": None,
        "max_steps": None,
        "deny_reason": None,
        "allow_reason": None,
    }

    for key in ("__default__", profile["kind"], profile["name"]):
        source = overrides.get(key)
        if isinstance(source, dict):
            profile = _merge_policy_source(profile, source)

    metadata_overrides = metadata.get("policy_overrides")
    if isinstance(metadata_overrides, dict):
        profile = _merge_policy_source(profile, metadata_overrides)

    if profile["kind"] == "browser" and not profile["approval_triggers"]:
        profile["approval_triggers"] = ["external_url"]

    return profile


def get_operational_controls(settings: Settings) -> dict[str, Any]:
    overrides = get_tool_policy_overrides(settings)
    return {
        "schema_version": SCHEMA_VERSION,
        "trust_levels": TRUST_LEVEL_LABELS,
        "approval_triggers": {
            "shell": list(DEFAULT_SHELL_APPROVAL_TRIGGERS),
            "browser": ["external_url"],
        },
        "deny_triggers": {
            "shell": list(DEFAULT_SHELL_DENY_TRIGGERS),
        },
        "budgets": {
            "default_timeout_seconds": settings.default_timeout_seconds,
            "task_timeout_hard_limit_seconds": settings.task_timeout_hard_limit_seconds,
            "runtime_max_steps_hard_limit": settings.runtime_max_steps_hard_limit,
        },
        "tool_policy_overrides": overrides,
    }


def evaluate_tool_policy(
    tool: dict[str, Any],
    payload: dict[str, Any],
    settings: Settings,
    *,
    approved: bool = False,
) -> GuardrailDecision:
    profile = get_tool_policy_profile(settings, tool)
    name = profile["name"]
    kind = profile["kind"]
    status = profile["status"]
    trust_level = _coerce_int(profile.get("trust_level"), 0)
    trust_label = get_trust_level_label(trust_level)
    details: dict[str, Any] = {
        "tool_name": name,
        "kind": kind,
        "status": status,
        "trust_level": trust_level,
        "trust_label": trust_label,
        "approval_triggers": profile.get("approval_triggers", []),
        "deny_triggers": profile.get("deny_triggers", []),
        "requires_approval": bool(profile.get("requires_approval") or False),
    }

    if profile.get("deny_reason"):
        return GuardrailDecision(
            allowed=False,
            requires_approval=False,
            decision="deny",
            reason=str(profile["deny_reason"]),
            reason_code="deny.policy_override",
            trust_level=trust_level,
            details=details,
        )

    if status == "blocked":
        return GuardrailDecision(
            allowed=False,
            requires_approval=False,
            decision="deny",
            reason=f'tool "{name}" is blocked',
            reason_code="deny.tool_blocked",
            trust_level=trust_level,
            details=details,
        )

    if kind == "shell":
        command = str(payload.get("command") or "").strip()
        if not command:
            return GuardrailDecision(
                allowed=False,
                requires_approval=False,
                decision="deny",
                reason="shell payload is missing the command field",
                reason_code="deny.shell_missing_command",
                trust_level=trust_level,
                details=details,
            )
        lowered = command.lower()
        deny_trigger = _first_trigger(lowered, list(profile.get("deny_triggers") or []))
        if deny_trigger is not None:
            return GuardrailDecision(
                allowed=False,
                requires_approval=False,
                decision="deny",
                reason=f"blocked shell trigger: {deny_trigger}",
                reason_code=f"deny.shell.{_slugify(deny_trigger)}",
                trust_level=trust_level,
                details={**details, "matched_trigger": deny_trigger},
            )
        approval_trigger = _first_trigger(lowered, list(profile.get("approval_triggers") or []))
        if approval_trigger is not None and not approved:
            return GuardrailDecision(
                allowed=False,
                requires_approval=True,
                decision="approval_required",
                reason=f"shell command requires approval because it matches trigger: {approval_trigger}",
                reason_code=f"approval.shell.{_slugify(approval_trigger)}",
                trust_level=trust_level,
                details={**details, "matched_trigger": approval_trigger},
            )
        if trust_level < 2 and not approved:
            return GuardrailDecision(
                allowed=False,
                requires_approval=True,
                decision="approval_required",
                reason=f'shell tool "{name}" has trust level {trust_level} ({trust_label}) and needs approval',
                reason_code="approval.shell.trust_level",
                trust_level=trust_level,
                details=details,
            )
        return GuardrailDecision(
            allowed=True,
            requires_approval=False,
            decision="allow",
            reason=profile.get("allow_reason") or f'shell tool "{name}" passed policy checks',
            reason_code="allow.shell_policy_passed",
            trust_level=trust_level,
            details=details,
        )

    if kind == "browser":
        url = str(payload.get("url") or "").strip()
        if not url:
            return GuardrailDecision(
                allowed=False,
                requires_approval=False,
                decision="deny",
                reason="browser payload is missing the url field",
                reason_code="deny.browser_missing_url",
                trust_level=trust_level,
                details=details,
            )
        parsed = urlparse(url)
        if not parsed.scheme:
            return GuardrailDecision(
                allowed=False,
                requires_approval=False,
                decision="deny",
                reason="browser payload is missing a URL scheme",
                reason_code="deny.browser_missing_scheme",
                trust_level=trust_level,
                details=details,
            )
        if parsed.scheme not in {"http", "https"}:
            return GuardrailDecision(
                allowed=False,
                requires_approval=False,
                decision="deny",
                reason=f"browser url scheme '{parsed.scheme}' is not supported",
                reason_code="deny.browser_unsupported_scheme",
                trust_level=trust_level,
                details={**details, "url": url, "scheme": parsed.scheme},
            )
        if _is_external_url(url) and not approved:
            return GuardrailDecision(
                allowed=False,
                requires_approval=True,
                decision="approval_required",
                reason=f'browser execution requires approval for external url: {url}',
                reason_code="approval.browser.external_url",
                trust_level=trust_level,
                details={**details, "url": url},
            )
        if trust_level < 2 and not approved:
            return GuardrailDecision(
                allowed=False,
                requires_approval=True,
                decision="approval_required",
                reason=f'browser tool "{name}" has trust level {trust_level} ({trust_label}) and needs approval',
                reason_code="approval.browser.trust_level",
                trust_level=trust_level,
                details={**details, "url": url},
            )
        return GuardrailDecision(
            allowed=True,
            requires_approval=False,
            decision="allow",
            reason=profile.get("allow_reason") or f'browser tool "{name}" passed policy checks',
            reason_code="allow.browser_policy_passed",
            trust_level=trust_level,
            details={**details, "url": url},
        )

    if kind == "model":
        if not settings.model_runner_enabled:
            return GuardrailDecision(
                allowed=False,
                requires_approval=False,
                decision="deny",
                reason="model runner is not enabled",
                reason_code="deny.model_runner_disabled",
                trust_level=trust_level,
                details=details,
            )
        if trust_level < 1 and not approved:
            return GuardrailDecision(
                allowed=False,
                requires_approval=True,
                decision="approval_required",
                reason=f'model tool "{name}" has trust level {trust_level} ({trust_label}) and needs approval',
                reason_code="approval.model.trust_level",
                trust_level=trust_level,
                details=details,
            )
        return GuardrailDecision(
            allowed=True,
            requires_approval=False,
            decision="allow",
            reason=profile.get("allow_reason") or f'model tool "{name}" passed policy checks',
            reason_code="allow.model_policy_passed",
            trust_level=trust_level,
            details=details,
        )

    if status != "trusted" and not approved:
        return GuardrailDecision(
            allowed=False,
            requires_approval=True,
            decision="approval_required",
            reason=f'tool "{name}" is not trusted yet ({status or "unknown"})',
            reason_code="approval.tool_status",
            trust_level=trust_level,
            details=details,
        )

    if trust_level < 2 and not approved:
        return GuardrailDecision(
            allowed=False,
            requires_approval=True,
            decision="approval_required",
            reason=f'tool "{name}" has trust level {trust_level} ({trust_label}) and needs approval',
            reason_code="approval.tool_trust_level",
            trust_level=trust_level,
            details=details,
        )

    if profile.get("requires_approval") and not approved:
        return GuardrailDecision(
            allowed=False,
            requires_approval=True,
            decision="approval_required",
            reason=f'tool "{name}" is configured to require approval',
            reason_code="approval.tool_override",
            trust_level=trust_level,
            details=details,
        )

    return GuardrailDecision(
        allowed=True,
        requires_approval=False,
        decision="allow",
        reason=profile.get("allow_reason") or f'tool "{name}" passed policy checks',
        reason_code="allow.policy_passed",
        trust_level=trust_level,
        details=details,
    )


def resolve_task_timeout_budget(
    settings: Settings,
    tool: dict[str, Any],
    payload: dict[str, Any],
    *,
    requested_timeout_seconds: int | None = None,
) -> TimeoutBudget:
    profile = get_tool_policy_profile(settings, tool)
    tool_timeout = _coerce_int(profile.get("timeout_seconds"), 0)
    requested = requested_timeout_seconds
    if requested is None:
        requested = _coerce_int(payload.get("timeout_seconds"), 0) or None

    base_limit = max(1, _coerce_int(settings.default_timeout_seconds, 60))
    hard_limit = max(1, _coerce_int(settings.task_timeout_hard_limit_seconds, base_limit))
    candidate_limits = [base_limit, hard_limit]
    if tool_timeout > 0:
        candidate_limits.append(tool_timeout)
    limit_seconds = min(candidate_limits)

    details = {
        "tool_name": profile["name"],
        "kind": profile["kind"],
        "trust_level": profile["trust_level"],
        "limit_seconds": limit_seconds,
        "hard_limit_seconds": hard_limit,
        "default_timeout_seconds": base_limit,
    }

    if requested is None:
        return TimeoutBudget(
            allowed=True,
            timeout_seconds=limit_seconds,
            requested_seconds=None,
            limit_seconds=limit_seconds,
            reason=f"timeout budget set to {limit_seconds}s",
            reason_code="allow.timeout_budget_default",
            details=details,
        )

    requested = _coerce_int(requested, 0)
    if requested <= 0:
        return TimeoutBudget(
            allowed=False,
            timeout_seconds=limit_seconds,
            requested_seconds=requested,
            limit_seconds=limit_seconds,
            reason="timeout budget must be greater than zero",
            reason_code="deny.timeout_invalid",
            details={**details, "requested_seconds": requested},
        )

    if requested > limit_seconds:
        return TimeoutBudget(
            allowed=False,
            timeout_seconds=limit_seconds,
            requested_seconds=requested,
            limit_seconds=limit_seconds,
            reason=f"requested timeout {requested}s exceeds policy limit {limit_seconds}s",
            reason_code="deny.timeout_exceeds_limit",
            details={**details, "requested_seconds": requested},
        )

    return TimeoutBudget(
        allowed=True,
        timeout_seconds=requested,
        requested_seconds=requested,
        limit_seconds=limit_seconds,
        reason=f"timeout budget accepted at {requested}s (limit {limit_seconds}s)",
        reason_code="allow.timeout_budget",
        details={**details, "requested_seconds": requested},
    )


def resolve_runtime_step_budget(settings: Settings, requested_max_steps: int) -> StepBudget:
    limit_max_steps = max(1, _coerce_int(settings.runtime_max_steps_hard_limit, 10))
    requested_max_steps = _coerce_int(requested_max_steps, 0)
    details = {"limit_max_steps": limit_max_steps}

    if requested_max_steps <= 0:
        return StepBudget(
            allowed=False,
            max_steps=limit_max_steps,
            requested_max_steps=requested_max_steps,
            limit_max_steps=limit_max_steps,
            reason="max_steps must be greater than zero",
            reason_code="deny.max_steps_invalid",
            details=details,
        )

    if requested_max_steps > limit_max_steps:
        return StepBudget(
            allowed=False,
            max_steps=limit_max_steps,
            requested_max_steps=requested_max_steps,
            limit_max_steps=limit_max_steps,
            reason=f"requested max_steps {requested_max_steps} exceeds runtime limit {limit_max_steps}",
            reason_code="deny.max_steps_exceeds_limit",
            details={**details, "requested_max_steps": requested_max_steps},
        )

    return StepBudget(
        allowed=True,
        max_steps=requested_max_steps,
        requested_max_steps=requested_max_steps,
        limit_max_steps=limit_max_steps,
        reason=f"runtime step budget accepted at {requested_max_steps} step(s)",
        reason_code="allow.max_steps",
        details={**details, "requested_max_steps": requested_max_steps},
    )
