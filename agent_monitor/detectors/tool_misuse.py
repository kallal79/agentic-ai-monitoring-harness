"""
agent_monitor.detectors.tool_misuse

Detector for agent tool misuse and schema violations:
- Invocations of unregistered or hallucinated tool names
- Missing mandatory arguments defined in tool schemas
- Parameter type mismatches (e.g. dict where string expected)
- Nonsensical, empty, or placeholder arguments (e.g. 'undefined', '<INSERT_KEY>')
- Parameter value boundary violations
"""

import re
from typing import Any, Dict, List, Optional
from agent_monitor.detectors.base import BaseDetector
from agent_monitor.models import AgentTrace, DetectedIssue, FailureCategory, Severity
from agent_monitor.tool_registry import DEFAULT_TOOL_REGISTRY, ToolSpec

# Typical placeholder strings that indicate hallucinated or unpopulated inputs
NONSENSICAL_PATTERNS = [
    re.compile(r"^\s*undefined\s*$", re.IGNORECASE),
    re.compile(r"^\s*null\s*$", re.IGNORECASE),
    re.compile(r"^\s*nan\s*$", re.IGNORECASE),
    re.compile(r"^<.*>$"),  # e.g. <INSERT_PATH>, <API_KEY>
    re.compile(r"<INSERT_[A-Za-z0-9_]+>", re.IGNORECASE),
    re.compile(r"^\$\{.*\}$"),  # e.g. ${customer_id}
    re.compile(r"^\[.*\]$"),  # e.g. [TODO]
    re.compile(r"^\s*TODO\b", re.IGNORECASE),
]


class ToolMisuseDetector(BaseDetector):
    """Detects invalid tool calls, schema breaches, and nonsensical arguments."""

    def __init__(self, tool_registry: Optional[Dict[str, ToolSpec]] = None):
        super().__init__(name="ToolMisuseDetector", category=FailureCategory.TOOL_MISUSE)
        self.registry = tool_registry or DEFAULT_TOOL_REGISTRY

    def detect(self, trace: AgentTrace) -> List[DetectedIssue]:
        issues: List[DetectedIssue] = []
        allowed_tools = trace.metadata.allowed_tools if trace.metadata else None

        for step in trace.steps:
            if not step.tool_call:
                continue

            tool_name = step.tool_call.tool_name
            params = step.tool_call.parameters or {}

            # 1. Check if tool is allowed or registered
            if allowed_tools is not None and tool_name not in allowed_tools:
                issues.append(
                    DetectedIssue(
                        category=self.category,
                        severity=Severity.HIGH,
                        step_index=step.step_index,
                        title="Unauthorized Tool Invocation",
                        description=(
                            f"Agent invoked tool '{tool_name}' which is not in the allowed tools "
                            f"policy list: {allowed_tools}."
                        ),
                        confidence=0.98,
                        evidence={
                            "tool_name": tool_name,
                            "allowed_tools": allowed_tools,
                        },
                        recommendation="Restrict tool call dispatch in the agent prompt and middleware.",
                    )
                )
                continue

            if tool_name not in self.registry:
                issues.append(
                    DetectedIssue(
                        category=self.category,
                        severity=Severity.HIGH,
                        step_index=step.step_index,
                        title="Unregistered / Hallucinated Tool Invocation",
                        description=(
                            f"Agent attempted to invoke tool '{tool_name}' which does not exist "
                            f"in the system tool catalog."
                        ),
                        confidence=0.99,
                        evidence={
                            "tool_name": tool_name,
                            "available_tools": list(self.registry.keys()),
                        },
                        recommendation="Provide the agent with explicit tool schemas and remove outdated tool references.",
                    )
                )
                continue

            spec = self.registry[tool_name]

            # 2. Check for missing required parameters
            for param_name, param_spec in spec.parameters.items():
                if param_spec.required and param_name not in params:
                    issues.append(
                        DetectedIssue(
                            category=self.category,
                            severity=Severity.HIGH,
                            step_index=step.step_index,
                            title=f"Missing Required Parameter: '{param_name}'",
                            description=(
                                f"Tool '{tool_name}' requires parameter '{param_name}', but it was "
                                f"missing from the agent invocation arguments."
                            ),
                            confidence=0.95,
                            evidence={
                                "tool_name": tool_name,
                                "missing_param": param_name,
                                "provided_params": list(params.keys()),
                            },
                            recommendation=f"Enforce strict client-side JSON schema validation for '{tool_name}'.",
                        )
                    )

            # 3. Check parameter types and invalid/nonsensical values
            for param_name, val in params.items():
                if param_name not in spec.parameters:
                    # Unknown extraneous parameter
                    issues.append(
                        DetectedIssue(
                            category=self.category,
                            severity=Severity.LOW,
                            step_index=step.step_index,
                            title=f"Unexpected Parameter: '{param_name}'",
                            description=(
                                f"Parameter '{param_name}' is not recognized by tool '{tool_name}' schema."
                            ),
                            confidence=0.85,
                            evidence={
                                "tool_name": tool_name,
                                "unexpected_param": param_name,
                            },
                            recommendation="Strip unexpected kwargs before tool execution.",
                        )
                    )
                    continue

                param_spec = spec.parameters[param_name]

                # Type check
                if val is not None and not isinstance(val, param_spec.expected_type):
                    # Special case: float acceptable for int if whole number
                    if param_spec.expected_type is int and isinstance(val, float) and val.is_integer():
                        pass
                    else:
                        issues.append(
                            DetectedIssue(
                                category=self.category,
                                severity=Severity.HIGH,
                                step_index=step.step_index,
                                title=f"Parameter Type Mismatch: '{param_name}'",
                                description=(
                                    f"Parameter '{param_name}' expected type '{param_spec.expected_type.__name__}', "
                                    f"but got '{type(val).__name__}'."
                                ),
                                confidence=0.95,
                                evidence={
                                    "tool_name": tool_name,
                                    "parameter": param_name,
                                    "expected_type": param_spec.expected_type.__name__,
                                    "actual_type": type(val).__name__,
                                    "value": str(val)[:100],
                                },
                                recommendation="Validate argument types against schema before tool execution.",
                            )
                        )

                # String checks: empty or nonsensical placeholder
                if isinstance(val, str):
                    stripped_val = val.strip()
                    if param_spec.required and len(stripped_val) == 0:
                        issues.append(
                            DetectedIssue(
                                category=self.category,
                                severity=Severity.HIGH,
                                step_index=step.step_index,
                                title=f"Empty Required Parameter: '{param_name}'",
                                description=(
                                    f"Tool '{tool_name}' was called with an empty string for required "
                                    f"parameter '{param_name}'."
                                ),
                                confidence=0.96,
                                evidence={
                                    "tool_name": tool_name,
                                    "parameter": param_name,
                                },
                                recommendation="Block execution of tools with blank required inputs.",
                            )
                        )
                    else:
                        for pattern in NONSENSICAL_PATTERNS:
                            if pattern.search(stripped_val):
                                issues.append(
                                    DetectedIssue(
                                        category=self.category,
                                        severity=Severity.HIGH,
                                        step_index=step.step_index,
                                        title=f"Nonsensical / Placeholder Argument in '{param_name}'",
                                        description=(
                                            f"Parameter '{param_name}' contains an unpopulated placeholder or "
                                            f"invalid value: '{stripped_val}'."
                                        ),
                                        confidence=0.94,
                                        evidence={
                                            "tool_name": tool_name,
                                            "parameter": param_name,
                                            "value": stripped_val,
                                        },
                                        recommendation="Verify that agent replaces template placeholders before invoking tools.",
                                    )
                                )
                                break

        return issues
