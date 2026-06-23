from __future__ import annotations

import shlex
from typing import Any, Sequence

from .security_controls import GuardrailDecision, evaluate_tool_policy
from .settings import Settings

DANGEROUS_SNIPPETS = (
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
    "ssh ",
    "scp ",
)

SHELL_CONTROL_SNIPPETS = (
    "&&",
    "||",
    ";",
    "|",
    "`",
    "$(",
    ">",
    "<",
)


PolicyDecision = GuardrailDecision


class ShellPolicyError(ValueError):
    pass


def parse_shell_command(command: str, allowed_commands: Sequence[str]) -> list[str]:
    normalized = (command or "").strip()
    if not normalized:
        raise ShellPolicyError("shell payload is missing the command field")

    lowered = normalized.lower()
    for snippet in DANGEROUS_SNIPPETS:
        if snippet in lowered:
            raise ShellPolicyError(f"blocked shell snippet: {snippet}")

    for operator in SHELL_CONTROL_SNIPPETS:
        if operator in normalized:
            raise ShellPolicyError(f"blocked shell operator: {operator}")

    if "\n" in normalized or "\r" in normalized:
        raise ShellPolicyError("blocked shell operator: multiline input")

    try:
        argv = shlex.split(normalized)
    except ValueError as exc:
        raise ShellPolicyError("shell command could not be parsed safely") from exc

    if not argv:
        raise ShellPolicyError("shell payload is missing the command field")

    if argv[0] not in allowed_commands:
        raise ShellPolicyError(f'shell command "{argv[0]}" is not in the allowlist')

    return argv


def evaluate(tool: dict[str, Any], payload: dict[str, Any], settings: Settings, *, approved: bool = False) -> PolicyDecision:
    if tool.get("kind") == "shell":
        command = payload.get("command") or ""
        try:
            parse_shell_command(command, settings.allowed_shell_command_list)
        except ShellPolicyError as exc:
            return PolicyDecision(
                allowed=False,
                requires_approval=False,
                decision="deny",
                reason=str(exc),
                reason_code="deny.shell_parse_error",
                trust_level=int(tool.get("trust_level") or 0),
                details={"tool_name": tool.get("name"), "kind": "shell"},
            )
    return evaluate_tool_policy(tool, payload, settings, approved=approved)
