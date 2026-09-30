"""
agent_monitor.comparator

Trace Comparison and Behavioral Regression Diff Engine.
Calculates semantic divergence points, cost/token differences,
and step-by-step trajectory diffs between two agent execution runs.
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agent_monitor.models import AgentTrace, EvaluationResult
from agent_monitor.profiler import ResourceProfiler


class StepDiff(BaseModel):
    step_index: int
    trace_a_thought: str = ""
    trace_b_thought: str = ""
    trace_a_tool: Optional[str] = None
    trace_b_tool: Optional[str] = None
    is_divergent: bool = False
    notes: str = ""


class TraceComparisonResult(BaseModel):
    trace_a_id: str
    trace_b_id: str
    score_delta: float
    score_a: float
    score_b: float
    status_a: str
    status_b: str
    tokens_delta: int
    cost_delta_usd: float
    divergence_step: Optional[int] = None
    divergence_reason: Optional[str] = None
    step_diffs: List[StepDiff] = Field(default_factory=list)


class TraceComparator:
    """Compares two agent traces to pinpoint where divergence, regressions, or loops begin."""

    @classmethod
    def compare(
        cls,
        trace_a: AgentTrace,
        trace_b: AgentTrace,
        eval_a: Optional[EvaluationResult] = None,
        eval_b: Optional[EvaluationResult] = None,
    ) -> TraceComparisonResult:
        prof_a = ResourceProfiler.profile_trace(trace_a)
        prof_b = ResourceProfiler.profile_trace(trace_b)

        score_a = eval_a.score.composite_score if eval_a else 100.0
        score_b = eval_b.score.composite_score if eval_b else 100.0
        status_a = eval_a.score.status if eval_a else "PASS"
        status_b = eval_b.score.status if eval_b else "PASS"

        max_steps = max(len(trace_a.steps), len(trace_b.steps))
        step_diffs: List[StepDiff] = []
        divergence_step: Optional[int] = None
        divergence_reason: Optional[str] = None

        for idx in range(1, max_steps + 1):
            step_a = next((s for s in trace_a.steps if s.step_index == idx), None)
            step_b = next((s for s in trace_b.steps if s.step_index == idx), None)

            tool_a_str = f"{step_a.tool_call.tool_name}({json.dumps(step_a.tool_call.parameters)})" if step_a and step_a.tool_call else None
            tool_b_str = f"{step_b.tool_call.tool_name}({json.dumps(step_b.tool_call.parameters)})" if step_b and step_b.tool_call else None

            is_div = False
            notes = "Identical / Aligned"

            if step_a is None or step_b is None:
                is_div = True
                notes = "Step missing in one trace (Trajectory length mismatch)"
            elif tool_a_str != tool_b_str:
                is_div = True
                notes = f"Tool mismatch: Trace A used '{step_a.tool_call.tool_name if step_a.tool_call else 'None'}' vs Trace B used '{step_b.tool_call.tool_name if step_b.tool_call else 'None'}'"

            if is_div and divergence_step is None:
                divergence_step = idx
                divergence_reason = notes

            step_diffs.append(
                StepDiff(
                    step_index=idx,
                    trace_a_thought=step_a.thought if step_a else "[N/A]",
                    trace_b_thought=step_b.thought if step_b else "[N/A]",
                    trace_a_tool=tool_a_str,
                    trace_b_tool=tool_b_str,
                    is_divergent=is_div,
                    notes=notes,
                )
            )

        return TraceComparisonResult(
            trace_a_id=trace_a.trace_id,
            trace_b_id=trace_b.trace_id,
            score_delta=round(score_b - score_a, 2),
            score_a=score_a,
            score_b=score_b,
            status_a=status_a,
            status_b=status_b,
            tokens_delta=prof_b.total_tokens - prof_a.total_tokens,
            cost_delta_usd=round(prof_b.total_cost_usd - prof_a.total_cost_usd, 6),
            divergence_step=divergence_step,
            divergence_reason=divergence_reason or "Trajectories maintained identical structural path.",
            step_diffs=step_diffs,
        )
