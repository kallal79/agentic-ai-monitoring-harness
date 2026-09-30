"""
agent_monitor.opentelemetry_exporter

OpenTelemetry GenAI Semantic Conventions Exporter.
Converts AgentTraces and EvaluationResults into compliant OTel GenAI Spans,
enabling direct ingestion into Datadog, Jaeger, Arize Phoenix, and OpenTelemetry Collectors.
"""

from __future__ import annotations
import hashlib
import json
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agent_monitor.models import AgentTrace, EvaluationResult
from agent_monitor.profiler import ResourceProfiler


class OTelSpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    name: str
    kind: str = "SPAN_KIND_INTERNAL"  # INTERNAL, CLIENT, SERVER
    start_time_unix_nano: int
    end_time_unix_nano: int
    attributes: Dict[str, Any] = Field(default_factory=dict)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    status: Dict[str, str] = Field(default_factory=lambda: {"code": "STATUS_CODE_OK"})


class OTelTraceExport(BaseModel):
    resource: Dict[str, Any] = Field(default_factory=dict)
    spans: List[OTelSpan] = Field(default_factory=list)
    total_spans: int = 0
    export_timestamp: str = ""


class OpenTelemetryExporter:
    """Converts internal Agentic AI traces to OpenTelemetry GenAI standards."""

    @staticmethod
    def _to_hex_id(seed: str, length: int = 16) -> str:
        return hashlib.sha256(seed.encode()).hexdigest()[:length]

    @classmethod
    def export_trace(cls, trace: AgentTrace, eval_result: Optional[EvaluationResult] = None) -> OTelTraceExport:
        now_nano = int(time.time() * 1_000_000_000)
        trace_hex = cls._to_hex_id(trace.trace_id, 32)
        root_span_id = cls._to_hex_id(f"{trace.trace_id}_root", 16)

        profile = ResourceProfiler.profile_trace(trace)

        # 1. Root Agent Span
        root_attrs = {
            "gen_ai.system": "agentic-ai-monitoring-harness",
            "gen_ai.agent.id": trace.metadata.agent_id or "agent-primary",
            "gen_ai.agent.name": trace.metadata.agent_name or "Autonomous Agent",
            "gen_ai.request.model": trace.metadata.model_name or "gpt-4o",
            "gen_ai.usage.prompt_tokens": profile.total_prompt_tokens,
            "gen_ai.usage.completion_tokens": profile.total_completion_tokens,
            "gen_ai.usage.total_tokens": profile.total_tokens,
            "gen_ai.cost.usd": profile.total_cost_usd,
            "gen_ai.goal": trace.goal,
            "agent.domain": trace.metadata.domain or "general",
        }

        if eval_result:
            root_attrs.update(
                {
                    "gen_ai.evaluation.score": eval_result.score.composite_score,
                    "gen_ai.evaluation.status": eval_result.score.status,
                    "gen_ai.evaluation.anomalies_count": len(eval_result.issues),
                    "gen_ai.evaluation.failures": [f.value for f in eval_result.detected_failures],
                }
            )

        root_status_code = "STATUS_CODE_OK"
        if eval_result and eval_result.score.status == "FAIL":
            root_status_code = "STATUS_CODE_ERROR"

        total_trace_nano = int((profile.latency_breakdown.get("total_trace_ms", 240.0)) * 1_000_000)

        spans: List[OTelSpan] = [
            OTelSpan(
                trace_id=trace_hex,
                span_id=root_span_id,
                name=f"agent.execution: {trace.metadata.agent_name or 'Agent'}",
                kind="SPAN_KIND_SERVER",
                start_time_unix_nano=now_nano - total_trace_nano,
                end_time_unix_nano=now_nano,
                attributes=root_attrs,
                status={"code": root_status_code},
            )
        ]

        curr_nano = now_nano - total_trace_nano

        # 2. Child Spans for Each Step
        for step in trace.steps:
            step_nano_dur = int((step.step_duration_ms or 120.0) * 1_000_000)
            step_span_id = cls._to_hex_id(f"{trace.trace_id}_step_{step.step_index}", 16)

            # Step Thought Span
            thought_attrs = {
                "gen_ai.operation.name": "reasoning",
                "gen_ai.step.index": step.step_index,
                "gen_ai.thought": step.thought[:300] if step.thought else "",
                "gen_ai.action": step.action,
            }
            spans.append(
                OTelSpan(
                    trace_id=trace_hex,
                    span_id=step_span_id,
                    parent_span_id=root_span_id,
                    name=f"step_{step.step_index}:reasoning",
                    kind="SPAN_KIND_INTERNAL",
                    start_time_unix_nano=curr_nano,
                    end_time_unix_nano=curr_nano + int(step_nano_dur * 0.45),
                    attributes=thought_attrs,
                )
            )

            # Step Tool Execution Span
            if step.tool_call:
                tool_span_id = cls._to_hex_id(f"{trace.trace_id}_tool_{step.step_index}", 16)
                tool_attrs = {
                    "gen_ai.operation.name": "tool_execution",
                    "gen_ai.tool.name": step.tool_call.tool_name,
                    "gen_ai.tool.parameters": json.dumps(step.tool_call.parameters),
                    "gen_ai.tool.observation": str(step.observation)[:400] if step.observation else "",
                }
                spans.append(
                    OTelSpan(
                        trace_id=trace_hex,
                        span_id=tool_span_id,
                        parent_span_id=step_span_id,
                        name=f"tool:{step.tool_call.tool_name}",
                        kind="SPAN_KIND_CLIENT",
                        start_time_unix_nano=curr_nano + int(step_nano_dur * 0.45),
                        end_time_unix_nano=curr_nano + step_nano_dur,
                        attributes=tool_attrs,
                    )
                )

            curr_nano += step_nano_dur

        return OTelTraceExport(
            resource={
                "service.name": "agentic-ai-monitoring-service",
                "service.version": "1.2.0",
                "telemetry.sdk.language": "python",
                "telemetry.sdk.name": "opentelemetry",
            },
            spans=spans,
            total_spans=len(spans),
            export_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
