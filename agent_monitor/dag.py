"""
agent_monitor.dag

Directed Acyclic Graph (DAG) and Execution Span Tree Generator.
Translates linear agent steps into a rich structural graph of causal transitions,
tool execution spans, observation gates, and anomaly trigger nodes.
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agent_monitor.models import AgentTrace, EvaluationResult


class DAGNode(BaseModel):
    id: str
    label: str
    node_type: str  # "goal", "thought", "tool", "observation", "evaluator", "anomaly", "response"
    step_index: Optional[int] = None
    status: str = "healthy"  # "healthy", "warning", "critical", "info"
    duration_ms: Optional[float] = None
    tokens: Optional[int] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class DAGEdge(BaseModel):
    source: str
    target: str
    edge_type: str = "flow"  # "flow", "call", "response", "loop", "breach"
    label: Optional[str] = None
    is_anomaly_path: bool = False


class ExecutionDAG(BaseModel):
    trace_id: str
    root_node_id: str
    nodes: List[DAGNode] = Field(default_factory=list)
    edges: List[DAGEdge] = Field(default_factory=list)
    total_nodes: int = 0
    total_edges: int = 0
    has_cycles: bool = False
    critical_path: List[str] = Field(default_factory=list)


class DAGBuilder:
    """Constructs an interactive execution DAG from an AgentTrace and its EvaluationResult."""

    @classmethod
    def build_dag(cls, trace: AgentTrace, eval_result: Optional[EvaluationResult] = None) -> ExecutionDAG:
        nodes: List[DAGNode] = []
        edges: List[DAGEdge] = []

        # Map anomalies by step_index
        anomalies_by_step: Dict[int, List[Any]] = {}
        if eval_result and eval_result.issues:
            for issue in eval_result.issues:
                idx = issue.step_index or 0
                anomalies_by_step.setdefault(idx, []).append(issue)

        # 1. Root Goal Node
        root_id = "node_goal"
        nodes.append(
            DAGNode(
                id=root_id,
                label="User Objective",
                node_type="goal",
                status="info",
                summary=trace.goal[:60] + ("..." if len(trace.goal) > 60 else ""),
                details={"full_goal": trace.goal, "metadata": trace.metadata.model_dump()},
            )
        )

        prev_node_id = root_id
        critical_path: List[str] = [root_id]
        has_cycles = False
        seen_tools = {}

        for step in trace.steps:
            step_idx = step.step_index
            step_issues = anomalies_by_step.get(step_idx, [])
            step_status = "healthy"
            for iss in step_issues:
                if iss.severity.value in ["CRITICAL", "HIGH"]:
                    step_status = "critical"
                    break
                elif iss.severity.value == "MEDIUM":
                    step_status = "warning"

            # 2. Thought Node
            thought_id = f"node_thought_{step_idx}"
            nodes.append(
                DAGNode(
                    id=thought_id,
                    label=f"Step {step_idx}: Reasoning",
                    node_type="thought",
                    step_index=step_idx,
                    status=step_status if any(i.category.value in ["hallucination", "goal_drift"] for i in step_issues) else "healthy",
                    summary=step.thought[:55] + ("..." if len(step.thought) > 55 else "") if step.thought else "Internal planning",
                    details={"thought": step.thought, "action": step.action},
                )
            )
            edges.append(DAGEdge(source=prev_node_id, target=thought_id, label="plans"))
            prev_node_id = thought_id
            critical_path.append(thought_id)

            # 3. Tool Call Node (if tool invoked)
            if step.tool_call:
                tool_id = f"node_tool_{step_idx}"
                tool_name = step.tool_call.tool_name
                is_repeat = tool_name in seen_tools
                if is_repeat:
                    has_cycles = True
                seen_tools[tool_name] = tool_id

                tool_status = "healthy"
                for iss in step_issues:
                    if iss.category.value in ["tool_misuse", "unsafe_action", "looping"]:
                        tool_status = "critical" if iss.severity.value in ["CRITICAL", "HIGH"] else "warning"

                nodes.append(
                    DAGNode(
                        id=tool_id,
                        label=f"Tool: {tool_name}",
                        node_type="tool",
                        step_index=step_idx,
                        status=tool_status,
                        duration_ms=step.step_duration_ms or 120.0,
                        summary=f"Call {tool_name}(...)",
                        details={"parameters": step.tool_call.parameters, "tool_name": tool_name},
                    )
                )
                edges.append(DAGEdge(source=thought_id, target=tool_id, label="executes", edge_type="call"))
                prev_node_id = tool_id
                critical_path.append(tool_id)

                # 4. Observation Node
                obs_id = f"node_obs_{step_idx}"
                obs_summary = str(step.observation)[:50] + "..." if step.observation else "No observation"
                nodes.append(
                    DAGNode(
                        id=obs_id,
                        label=f"Observation {step_idx}",
                        node_type="observation",
                        step_index=step_idx,
                        status="healthy",
                        summary=obs_summary,
                        details={"raw_observation": step.observation},
                    )
                )
                edges.append(DAGEdge(source=tool_id, target=obs_id, label="returns", edge_type="response"))
                prev_node_id = obs_id
                critical_path.append(obs_id)

            # 5. Anomaly Node Callout if flagged
            for iss_idx, iss in enumerate(step_issues):
                anomaly_node_id = f"node_anomaly_{step_idx}_{iss_idx}"
                nodes.append(
                    DAGNode(
                        id=anomaly_node_id,
                        label=f"ANOMALY: {iss.category.value.upper()}",
                        node_type="anomaly",
                        step_index=step_idx,
                        status="critical" if iss.severity.value in ["CRITICAL", "HIGH"] else "warning",
                        summary=iss.title,
                        details={
                            "category": iss.category.value,
                            "severity": iss.severity.value,
                            "description": iss.description,
                            "recommendation": iss.recommendation,
                            "confidence": iss.confidence,
                        },
                    )
                )
                edges.append(
                    DAGEdge(
                        source=prev_node_id,
                        target=anomaly_node_id,
                        label="breach flagged",
                        edge_type="breach",
                        is_anomaly_path=True,
                    )
                )

        # 6. Final Evaluation Gate Node
        eval_node_id = "node_evaluator"
        final_status = "healthy"
        score_val = 100.0
        if eval_result:
            score_val = eval_result.score.composite_score
            if eval_result.score.status == "FAIL":
                final_status = "critical"
            elif eval_result.score.status == "WARNING":
                final_status = "warning"

        nodes.append(
            DAGNode(
                id=eval_node_id,
                label=f"Evaluator Verdict: {final_status.upper()} ({score_val:.1f}/100)",
                node_type="evaluator",
                status=final_status,
                summary=f"Safety Score: {score_val:.1f} | Issues: {len(eval_result.issues) if eval_result else 0}",
                details={"score": eval_result.score.model_dump() if eval_result else None},
            )
        )
        edges.append(DAGEdge(source=prev_node_id, target=eval_node_id, label="verifies"))
        critical_path.append(eval_node_id)

        return ExecutionDAG(
            trace_id=trace.trace_id,
            root_node_id=root_id,
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            total_edges=len(edges),
            has_cycles=has_cycles,
            critical_path=critical_path,
        )
