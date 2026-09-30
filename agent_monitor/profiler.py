"""
agent_monitor.profiler

Token Economics, Latency Decomposition, and Cost Attribution Engine.
Measures token consumption, estimates USD API expenditure, and detects
inefficient token burning in agentic loops.
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agent_monitor.models import AgentTrace, TraceStep

# Model Pricing Matrix (per 1,000,000 tokens in USD)
MODEL_PRICING_TABLE = {
    "gpt-4o": {"input_per_m": 2.50, "output_per_m": 10.00},
    "gpt-4o-mini": {"input_per_m": 0.15, "output_per_m": 0.60},
    "claude-3-5-sonnet": {"input_per_m": 3.00, "output_per_m": 15.00},
    "claude-3-haiku": {"input_per_m": 0.25, "output_per_m": 1.25},
    "llama-3.3-70b": {"input_per_m": 0.80, "output_per_m": 0.80},
    "default": {"input_per_m": 2.50, "output_per_m": 10.00},
}


class StepResourceMetric(BaseModel):
    step_index: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: float
    cost_usd: float
    is_wasteful: bool = False


class TraceCostProfile(BaseModel):
    trace_id: str
    model_name: str
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    wasted_tokens: int = 0
    wasted_cost_usd: float = 0.0
    cost_efficiency_ratio: float = 1.0  # (productive tokens / total tokens)
    token_burn_alert: bool = False
    step_metrics: List[StepResourceMetric] = Field(default_factory=list)
    latency_breakdown: Dict[str, float] = Field(default_factory=dict)


class ResourceProfiler:
    """Calculates token counts, costs, and execution efficiency for agent traces."""

    @staticmethod
    def estimate_tokens(text: Optional[str]) -> int:
        """Heuristic token estimator (approx 3.8 - 4.0 characters per token)."""
        if not text:
            return 0
        return max(1, int(len(text) / 3.8))

    @classmethod
    def profile_trace(cls, trace: AgentTrace) -> TraceCostProfile:
        model_key = (trace.metadata.model_name or "gpt-4o").lower()
        pricing = MODEL_PRICING_TABLE.get(model_key, MODEL_PRICING_TABLE["default"])

        tot_prompt = 0
        tot_comp = 0
        step_metrics: List[StepResourceMetric] = []
        tot_planning_ms = 0.0
        tot_tool_ms = 0.0

        accumulated_context = cls.estimate_tokens(trace.goal)

        seen_tool_signatures = set()
        wasted_tokens = 0
        wasted_cost = 0.0

        for step in trace.steps:
            # Step duration
            step_dur = step.step_duration_ms or 120.0
            tot_planning_ms += step_dur * 0.45
            tot_tool_ms += step_dur * 0.55

            # If telemetry has tokens_used, use it; else estimate
            if step.tokens_used:
                p_tok = step.tokens_used.get("prompt", cls.estimate_tokens(step.thought) + accumulated_context)
                c_tok = step.tokens_used.get("completion", cls.estimate_tokens(step.action))
            else:
                p_tok = accumulated_context + cls.estimate_tokens(step.thought)
                c_tok = cls.estimate_tokens(step.action)
                if step.tool_call:
                    c_tok += cls.estimate_tokens(step.tool_call.tool_name) + cls.estimate_tokens(json.dumps(step.tool_call.parameters))

            s_tot = p_tok + c_tok
            tot_prompt += p_tok
            tot_comp += c_tok

            # Cost for this step
            s_cost = (p_tok * pricing["input_per_m"] / 1_000_000.0) + (c_tok * pricing["output_per_m"] / 1_000_000.0)

            # Check if this step is a duplicate wasteful loop
            is_wasteful = False
            if step.tool_call:
                sig = f"{step.tool_call.tool_name}:{json.dumps(step.tool_call.parameters, sort_keys=True)}"
                if sig in seen_tool_signatures:
                    is_wasteful = True
                    wasted_tokens += s_tot
                    wasted_cost += s_cost
                else:
                    seen_tool_signatures.add(sig)

            step_metrics.append(
                StepResourceMetric(
                    step_index=step.step_index,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                    total_tokens=s_tot,
                    duration_ms=round(step_dur, 2),
                    cost_usd=round(s_cost, 6),
                    is_wasteful=is_wasteful,
                )
            )

            # Accumulate observation tokens into context for subsequent steps
            obs_str = json.dumps(step.observation) if isinstance(step.observation, (dict, list)) else str(step.observation or "")
            accumulated_context += cls.estimate_tokens(obs_str)

        # Final response tokens
        if trace.final_response:
            resp_tok = cls.estimate_tokens(trace.final_response)
            tot_comp += resp_tok

        grand_total_tokens = tot_prompt + tot_comp
        total_cost = (tot_prompt * pricing["input_per_m"] / 1_000_000.0) + (tot_comp * pricing["output_per_m"] / 1_000_000.0)

        burn_alert = (wasted_tokens > 1500) or (wasted_cost > 0.05) or (wasted_tokens / max(1, grand_total_tokens) > 0.35)
        efficiency = 1.0 - (wasted_tokens / max(1, grand_total_tokens))

        return TraceCostProfile(
            trace_id=trace.trace_id,
            model_name=model_key,
            total_prompt_tokens=tot_prompt,
            total_completion_tokens=tot_comp,
            total_tokens=grand_total_tokens,
            total_cost_usd=round(total_cost, 6),
            wasted_tokens=wasted_tokens,
            wasted_cost_usd=round(wasted_cost, 6),
            cost_efficiency_ratio=round(max(0.0, efficiency), 4),
            token_burn_alert=burn_alert,
            step_metrics=step_metrics,
            latency_breakdown={
                "planning_ms": round(tot_planning_ms, 2),
                "tool_execution_ms": round(tot_tool_ms, 2),
                "evaluation_overhead_ms": 0.24,
                "total_trace_ms": round(tot_planning_ms + tot_tool_ms, 2),
            },
        )
