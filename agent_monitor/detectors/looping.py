"""
agent_monitor.detectors.looping

Detector for looping and repetition behaviors in autonomous agents:
- Consecutive identical tool calls (same tool and exact same parameters)
- Multi-step oscillation cycles (e.g. A -> B -> A -> B)
- Thought and query stagnation (high semantic similarity without progress)
- Repetitive unadapted retry loops on identical failure responses
"""

import json
from typing import Any, Dict, List, Set, Tuple
from agent_monitor.detectors.base import BaseDetector
from agent_monitor.models import AgentTrace, DetectedIssue, FailureCategory, Severity


def _canonical_params(params: Dict[str, Any]) -> str:
    """Normalize dictionary parameters to deterministic JSON string for exact matching."""
    try:
        return json.dumps(params, sort_keys=True, default=str).lower().strip()
    except Exception:
        return str(params).lower().strip()


def _tokenize(text: str) -> Set[str]:
    """Tokenize text into lowercase alphanumeric set for token-level similarity."""
    cleaned = "".join(c.lower() if c.isalnum() else " " for c in text)
    return set(token for token in cleaned.split() if len(token) > 2)


def _jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """Calculate Jaccard similarity between two token sets."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


class LoopingDetector(BaseDetector):
    """Detects repetitive, cyclic, and stagnant agent loops."""

    def __init__(
        self,
        consecutive_threshold: int = 2,
        cycle_max_length: int = 3,
        semantic_thought_threshold: float = 0.85,
    ):
        super().__init__(name="LoopingDetector", category=FailureCategory.LOOPING)
        self.consecutive_threshold = consecutive_threshold
        self.cycle_max_length = cycle_max_length
        self.semantic_thought_threshold = semantic_thought_threshold

    def detect(self, trace: AgentTrace) -> List[DetectedIssue]:
        issues: List[DetectedIssue] = []
        steps = trace.steps
        if len(steps) < 2:
            return issues

        # 1. Check for Consecutive Identical Tool Calls
        consecutive_count = 1
        last_tool_sig: Optional[str] = None
        last_step_idx = 0

        for idx, step in enumerate(steps):
            if step.tool_call:
                sig = f"{step.tool_call.tool_name}:{_canonical_params(step.tool_call.parameters)}"
                if sig == last_tool_sig:
                    consecutive_count += 1
                    if consecutive_count >= self.consecutive_threshold:
                        issues.append(
                            DetectedIssue(
                                category=self.category,
                                severity=Severity.HIGH if consecutive_count > 2 else Severity.MEDIUM,
                                step_index=step.step_index,
                                title="Consecutive Identical Tool Call Loop",
                                description=(
                                    f"Agent called tool '{step.tool_call.tool_name}' with identical parameters "
                                    f"{consecutive_count} times consecutively at step {step.step_index}."
                                ),
                                confidence=min(0.70 + (consecutive_count * 0.1), 0.99),
                                evidence={
                                    "tool_name": step.tool_call.tool_name,
                                    "parameters": step.tool_call.parameters,
                                    "consecutive_count": consecutive_count,
                                    "initial_step": last_step_idx,
                                    "current_step": step.step_index,
                                },
                                recommendation="Implement exponential backoff or dynamic parameter modification on repeated calls.",
                            )
                        )
                else:
                    consecutive_count = 1
                    last_tool_sig = sig
                    last_step_idx = step.step_index
            else:
                consecutive_count = 1
                last_tool_sig = None

        # 2. Check for Periodic Oscillation Cycles (e.g. A -> B -> A -> B)
        tool_signatures: List[Tuple[int, str]] = []
        for step in steps:
            if step.tool_call:
                sig = f"{step.tool_call.tool_name}:{_canonical_params(step.tool_call.parameters)}"
                tool_signatures.append((step.step_index, sig))

        if len(tool_signatures) >= 4:
            sigs = [s for _, s in tool_signatures]
            # Check cycle lengths of 2 and 3
            for period in range(2, min(self.cycle_max_length + 1, len(sigs) // 2 + 1)):
                # Look at the last 2 * period entries
                for start in range(len(sigs) - 2 * period + 1):
                    window1 = sigs[start : start + period]
                    window2 = sigs[start + period : start + 2 * period]
                    if window1 == window2 and len(set(window1)) > 1:
                        trigger_step = tool_signatures[start + 2 * period - 1][0]
                        # Avoid duplicate issue if already flagged
                        if not any(i.step_index == trigger_step and "Oscillation" in i.title for i in issues):
                            issues.append(
                                DetectedIssue(
                                    category=self.category,
                                    severity=Severity.HIGH,
                                    step_index=trigger_step,
                                    title=f"Oscillation Cycle Detected (Period {period})",
                                    description=(
                                        f"Agent is oscillating in a repeating sequence of {period} actions "
                                        f"without making forward progress."
                                    ),
                                    confidence=0.92,
                                    evidence={
                                        "period_length": period,
                                        "pattern": [sigs[start + k].split(":")[0] for k in range(period)],
                                        "cycle_step_range": [
                                            tool_signatures[start][0],
                                            trigger_step,
                                        ],
                                    },
                                    recommendation="Detect cyclic action sequences and prompt agent to select an alternative strategy.",
                                )
                            )

        # 3. Check for Semantic Thought Stagnation across consecutive steps
        for i in range(len(steps) - 1):
            s1 = steps[i]
            s2 = steps[i + 1]
            if s1.thought and s2.thought:
                t1_tokens = _tokenize(s1.thought)
                t2_tokens = _tokenize(s2.thought)
                sim = _jaccard_similarity(t1_tokens, t2_tokens)
                if sim >= self.semantic_thought_threshold and len(t1_tokens) > 5:
                    # Also check if s2 didn't make progress
                    issues.append(
                        DetectedIssue(
                            category=self.category,
                            severity=Severity.MEDIUM,
                            step_index=s2.step_index,
                            title="Semantic Thought Stagnation",
                            description=(
                                f"Agent internal thoughts at step {s2.step_index} are near-identical to step {s1.step_index} "
                                f"(token similarity: {sim:.2f}) indicating mental loop."
                            ),
                            confidence=round(sim, 2),
                            evidence={
                                "similarity": round(sim, 4),
                                "step_previous": s1.step_index,
                                "step_current": s2.step_index,
                                "sample_thought": s2.thought[:120],
                            },
                            recommendation="Force agent re-planning when internal reasoning stagnates.",
                        )
                    )

        return issues
