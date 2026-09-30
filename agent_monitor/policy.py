"""
agent_monitor.policy

Runtime Guardrails and Security Policy Rule Engine for AI Agents.
Provides configurable, sub-millisecond policy checkpoints for tool execution,
spend budgets, privilege boundaries, and prompt-injection interception.
"""

from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agent_monitor.models import AgentTrace, Severity
from agent_monitor.profiler import ResourceProfiler


class PolicyRule(BaseModel):
    rule_id: str
    name: str
    description: str
    category: str  # "security", "reliability", "cost", "compliance"
    severity: Severity = Severity.CRITICAL
    is_enabled: bool = True
    parameters: Dict[str, Any] = Field(default_factory=dict)


class PolicyViolation(BaseModel):
    rule_id: str
    rule_name: str
    severity: Severity
    step_index: Optional[int] = None
    message: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    remediation: str = ""


class PolicyEvaluationReport(BaseModel):
    trace_id: str
    is_compliant: bool
    total_violations: int
    critical_violations: int
    violations: List[PolicyViolation] = Field(default_factory=list)
    enforced_rules_count: int = 0
    passed_rules_count: int = 0


# Default Standard Enterprise Agent Policy Preset
DEFAULT_POLICIES: List[PolicyRule] = [
    PolicyRule(
        rule_id="POL-SEC-01",
        name="Block Destructive Shell Commands",
        description="Prevents execution of rm -rf, mkfs, dd, forkbombs, or system shutdown commands.",
        category="security",
        severity=Severity.CRITICAL,
        is_enabled=True,
        parameters={"patterns": [r"rm\s+-(?:r|f|rf|fr)\s+[/~]", r"\bmkfs\b", r"\bdd\s+if=", r":\(\)\s*\{", r"\bshutdown\b", r"\bdrop\s+database\b"]},
    ),
    PolicyRule(
        rule_id="POL-SEC-02",
        name="Sensitive Credential & Path Isolation",
        description="Blocks unauthorized reads or writes to .env files, private keys, or system password hashes.",
        category="security",
        severity=Severity.CRITICAL,
        is_enabled=True,
        parameters={"patterns": [r"\.env(?:\.local)?\b", r"/etc/(?:shadow|passwd)", r"id_rsa(?:\.pub)?", r"aws_access_key", r"ghp_[A-Za-z0-9_]{36}"]},
    ),
    PolicyRule(
        rule_id="POL-SEC-03",
        name="Indirect Prompt Injection Jailbreak Shield",
        description="Detects external data sources attempting to hijack system instructions via adversarial prompts.",
        category="security",
        severity=Severity.CRITICAL,
        is_enabled=True,
        parameters={"patterns": [r"ignore\s+(?:all\s+)?previous\s+instructions", r"system\s*override", r"disregard\s+above", r"you\s+are\s+now\s+in\s+unrestricted\s+mode"]},
    ),
    PolicyRule(
        rule_id="POL-REL-01",
        name="Consecutive Identical Action Cap",
        description="Limits agents from firing identical tool calls with identical parameters in loops.",
        category="reliability",
        severity=Severity.HIGH,
        is_enabled=True,
        parameters={"max_consecutive_duplicates": 2},
    ),
    PolicyRule(
        rule_id="POL-REL-02",
        name="Strict Tool Schema & Placeholder Prohibition",
        description="Blocks dummy placeholder values (<INSERT_URL>, undefined, null, TODO) from tool parameters.",
        category="reliability",
        severity=Severity.HIGH,
        is_enabled=True,
        parameters={"forbidden_tokens": ["<insert_url>", "<placeholder>", "todo", "undefined", "[insert]"]},
    ),
    PolicyRule(
        rule_id="POL-CST-01",
        name="Max Trace Budget & Token Spend Cap",
        description="Halts agent runs exceeding maximum token consumption budget.",
        category="cost",
        severity=Severity.MEDIUM,
        is_enabled=True,
        parameters={"max_tokens": 15000, "max_cost_usd": 0.25},
    ),
]


class PolicyEngine:
    """Evaluates agent traces against active enterprise guardrail policies."""

    def __init__(self, policies: Optional[List[PolicyRule]] = None):
        self.policies = {p.rule_id: p for p in (policies or DEFAULT_POLICIES)}

    def evaluate_trace(self, trace: AgentTrace) -> PolicyEvaluationReport:
        violations: List[PolicyViolation] = []
        enforced_count = 0
        passed_count = 0

        # Profile resource consumption for cost policy
        cost_profile = ResourceProfiler.profile_trace(trace)

        for rule in self.policies.values():
            if not rule.is_enabled:
                continue
            enforced_count += 1
            rule_violated = False

            # POL-SEC-01: Destructive Commands
            if rule.rule_id == "POL-SEC-01":
                patterns = [re.compile(p, re.IGNORECASE) for p in rule.parameters.get("patterns", [])]
                for step in trace.steps:
                    params_str = json.dumps(step.tool_call.parameters) if step.tool_call else ""
                    cmd_to_check = f"{step.action} {params_str}"
                    for pat in patterns:
                        if pat.search(cmd_to_check):
                            violations.append(
                                PolicyViolation(
                                    rule_id=rule.rule_id,
                                    rule_name=rule.name,
                                    severity=rule.severity,
                                    step_index=step.step_index,
                                    message=f"Destructive system command intercepted matching '{pat.pattern}'.",
                                    evidence={"command": cmd_to_check[:150]},
                                    remediation="Block tool execution and sandbox shell environment.",
                                )
                            )
                            rule_violated = True
                            break

            # POL-SEC-02: Sensitive Files
            elif rule.rule_id == "POL-SEC-02":
                patterns = [re.compile(p, re.IGNORECASE) for p in rule.parameters.get("patterns", [])]
                for step in trace.steps:
                    params_str = json.dumps(step.tool_call.parameters) if step.tool_call else ""
                    to_check = f"{step.thought} {step.action} {params_str}"
                    for pat in patterns:
                        if pat.search(to_check):
                            violations.append(
                                PolicyViolation(
                                    rule_id=rule.rule_id,
                                    rule_name=rule.name,
                                    severity=rule.severity,
                                    step_index=step.step_index,
                                    message=f"Access to sensitive resource/credential blocked matching '{pat.pattern}'.",
                                    evidence={"matched_pattern": pat.pattern},
                                    remediation="Enforce strict RBAC path isolation for agent runtime.",
                                )
                            )
                            rule_violated = True
                            break

            # POL-SEC-03: Indirect Prompt Injection
            elif rule.rule_id == "POL-SEC-03":
                patterns = [re.compile(p, re.IGNORECASE) for p in rule.parameters.get("patterns", [])]
                for step in trace.steps:
                    obs_str = str(step.observation or "")
                    for pat in patterns:
                        if pat.search(obs_str):
                            violations.append(
                                PolicyViolation(
                                    rule_id=rule.rule_id,
                                    rule_name=rule.name,
                                    severity=rule.severity,
                                    step_index=step.step_index,
                                    message=f"Indirect prompt injection vector detected in tool observation.",
                                    evidence={"snippet": obs_str[:120]},
                                    remediation="Sanitize external tool outputs before ingesting into model context.",
                                )
                            )
                            rule_violated = True
                            break

            # POL-REL-01: Looping
            elif rule.rule_id == "POL-REL-01":
                max_dups = rule.parameters.get("max_consecutive_duplicates", 2)
                last_sig = None
                dup_count = 1
                for step in trace.steps:
                    if step.tool_call:
                        sig = f"{step.tool_call.tool_name}:{json.dumps(step.tool_call.parameters, sort_keys=True)}"
                        if sig == last_sig:
                            dup_count += 1
                            if dup_count >= max_dups:
                                violations.append(
                                    PolicyViolation(
                                        rule_id=rule.rule_id,
                                        rule_name=rule.name,
                                        severity=rule.severity,
                                        step_index=step.step_index,
                                        message=f"Repeated identical tool call '{step.tool_call.tool_name}' {dup_count} times in sequence.",
                                        evidence={"tool_name": step.tool_call.tool_name},
                                        remediation="Terminate loop and trigger fallback human-in-the-loop escalation.",
                                    )
                                )
                                rule_violated = True
                                break
                        else:
                            last_sig = sig
                            dup_count = 1

            # POL-REL-02: Placeholders
            elif rule.rule_id == "POL-REL-02":
                forbidden = [f.lower() for f in rule.parameters.get("forbidden_tokens", [])]
                for step in trace.steps:
                    if step.tool_call:
                        param_str = json.dumps(step.tool_call.parameters).lower()
                        for tok in forbidden:
                            if tok in param_str:
                                violations.append(
                                    PolicyViolation(
                                        rule_id=rule.rule_id,
                                        rule_name=rule.name,
                                        severity=rule.severity,
                                        step_index=step.step_index,
                                        message=f"Placeholder token '{tok}' passed into tool '{step.tool_call.tool_name}'.",
                                        evidence={"tool_name": step.tool_call.tool_name, "token": tok},
                                        remediation="Pre-validate tool parameters against schema before dispatching.",
                                    )
                                )
                                rule_violated = True
                                break

            # POL-CST-01: Cost & Token Spend Cap
            elif rule.rule_id == "POL-CST-01":
                max_tokens = rule.parameters.get("max_tokens", 15000)
                max_cost = rule.parameters.get("max_cost_usd", 0.25)
                if cost_profile.total_tokens > max_tokens or cost_profile.total_cost_usd > max_cost:
                    violations.append(
                        PolicyViolation(
                            rule_id=rule.rule_id,
                            rule_name=rule.name,
                            severity=rule.severity,
                            step_index=None,
                            message=f"Trace budget exceeded: {cost_profile.total_tokens} tokens (${cost_profile.total_cost_usd:.4f}).",
                            evidence={"tokens": cost_profile.total_tokens, "cost_usd": cost_profile.total_cost_usd},
                            remediation="Set circuit breaker on agent context window to enforce budget limits.",
                        )
                    )
                    rule_violated = True

            if not rule_violated:
                passed_count += 1

        crit_count = sum(1 for v in violations if v.severity == Severity.CRITICAL)
        return PolicyEvaluationReport(
            trace_id=trace.trace_id,
            is_compliant=(len(violations) == 0),
            total_violations=len(violations),
            critical_violations=crit_count,
            violations=violations,
            enforced_rules_count=enforced_count,
            passed_rules_count=passed_count,
        )
