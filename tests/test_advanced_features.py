"""
tests/test_advanced_features.py

Automated unit tests covering:
- ResourceProfiler (tokens, cost, efficiency)
- DAGBuilder (nodes, edges, anomalies)
- PolicyEngine (security guardrails, caps)
- OpenTelemetryExporter (GenAI spans)
- TraceComparator (divergence, regression diff)
"""

import pytest
from agent_monitor.models import AgentTrace, TraceStep, ToolCall, Severity
from agent_monitor.profiler import ResourceProfiler
from agent_monitor.dag import DAGBuilder
from agent_monitor.policy import PolicyEngine, DEFAULT_POLICIES
from agent_monitor.opentelemetry_exporter import OpenTelemetryExporter
from agent_monitor.comparator import TraceComparator
from agent_monitor.harness import EvaluationHarness


@pytest.fixture
def sample_trace():
    return AgentTrace(
        trace_id="sample_trace_test",
        goal="Fetch cluster pods and restart nginx",
        steps=[
            TraceStep(
                step_index=1,
                thought="Checking active pods",
                action="Execute kubectl get pods",
                tool_call=ToolCall(tool_name="bash", parameters={"cmd": "kubectl get pods"}),
                observation="nginx-pod-1 Running, nginx-pod-2 Error",
                step_duration_ms=150.0,
            ),
            TraceStep(
                step_index=2,
                thought="Restarting failed pod",
                action="Execute kubectl rollout restart",
                tool_call=ToolCall(tool_name="bash", parameters={"cmd": "kubectl rollout restart deployment/nginx"}),
                observation="deployment.apps/nginx restarted",
                step_duration_ms=210.0,
            ),
        ],
        final_response="Restarted deployment nginx successfully.",
    )


@pytest.fixture
def looping_trace():
    return AgentTrace(
        trace_id="looping_trace_test",
        goal="Check database connections",
        steps=[
            TraceStep(
                step_index=1,
                thought="Checking pool",
                action="Execute check",
                tool_call=ToolCall(tool_name="sql_query", parameters={"query": "SELECT count(*) FROM pg_stat_activity"}),
                observation="count: 45",
            ),
            TraceStep(
                step_index=2,
                thought="Checking pool again",
                action="Execute check",
                tool_call=ToolCall(tool_name="sql_query", parameters={"query": "SELECT count(*) FROM pg_stat_activity"}),
                observation="count: 45",
            ),
            TraceStep(
                step_index=3,
                thought="Checking pool third time",
                action="Execute check",
                tool_call=ToolCall(tool_name="sql_query", parameters={"query": "SELECT count(*) FROM pg_stat_activity"}),
                observation="count: 45",
            ),
        ],
    )


def test_resource_profiler_normal_trace(sample_trace):
    profile = ResourceProfiler.profile_trace(sample_trace)
    assert profile.trace_id == "sample_trace_test"
    assert profile.total_tokens > 0
    assert profile.total_cost_usd > 0
    assert profile.wasted_tokens == 0
    assert profile.cost_efficiency_ratio == 1.0
    assert not profile.token_burn_alert
    assert "planning_ms" in profile.latency_breakdown


def test_resource_profiler_looping_trace(looping_trace):
    profile = ResourceProfiler.profile_trace(looping_trace)
    assert profile.wasted_tokens > 0
    assert profile.wasted_cost_usd > 0
    assert profile.cost_efficiency_ratio < 1.0


def test_dag_builder_generation(sample_trace):
    harness = EvaluationHarness()
    eval_result = harness.evaluate_trace(sample_trace)
    dag = DAGBuilder.build_dag(sample_trace, eval_result)

    assert dag.trace_id == "sample_trace_test"
    assert dag.total_nodes >= 6  # goal + 2 thoughts + 2 tools + 2 observations + evaluator
    assert dag.total_edges >= 5
    assert dag.root_node_id == "node_goal"

    node_types = {n.node_type for n in dag.nodes}
    assert "goal" in node_types
    assert "thought" in node_types
    assert "tool" in node_types
    assert "observation" in node_types
    assert "evaluator" in node_types


def test_policy_engine_destructive_command():
    unsafe_trace = AgentTrace(
        trace_id="unsafe_cmd_test",
        goal="Clean up temp files",
        steps=[
            TraceStep(
                step_index=1,
                thought="Wiping drive",
                action="Running rm -rf /",
                tool_call=ToolCall(tool_name="bash", parameters={"cmd": "rm -rf / --no-preserve-root"}),
            )
        ],
    )
    engine = PolicyEngine(DEFAULT_POLICIES)
    report = engine.evaluate_trace(unsafe_trace)

    assert not report.is_compliant
    assert report.critical_violations >= 1
    assert any(v.rule_id == "POL-SEC-01" for v in report.violations)


def test_policy_engine_sensitive_file():
    leak_trace = AgentTrace(
        trace_id="leak_test",
        goal="Read configuration",
        steps=[
            TraceStep(
                step_index=1,
                thought="Inspecting secret env file",
                action="cat .env",
                tool_call=ToolCall(tool_name="bash", parameters={"cmd": "cat .env"}),
            )
        ],
    )
    engine = PolicyEngine(DEFAULT_POLICIES)
    report = engine.evaluate_trace(leak_trace)

    assert not report.is_compliant
    assert any(v.rule_id == "POL-SEC-02" for v in report.violations)


def test_opentelemetry_exporter(sample_trace):
    harness = EvaluationHarness()
    eval_result = harness.evaluate_trace(sample_trace)
    otel = OpenTelemetryExporter.export_trace(sample_trace, eval_result)

    assert otel.total_spans > 0
    root_span = otel.spans[0]
    assert "gen_ai.system" in root_span.attributes
    assert "gen_ai.usage.total_tokens" in root_span.attributes
    assert "gen_ai.evaluation.score" in root_span.attributes
    assert root_span.status["code"] == "STATUS_CODE_OK"


def test_trace_comparator(sample_trace, looping_trace):
    harness = EvaluationHarness()
    eval_a = harness.evaluate_trace(sample_trace)
    eval_b = harness.evaluate_trace(looping_trace)

    comparison = TraceComparator.compare(sample_trace, looping_trace, eval_a, eval_b)
    assert comparison.trace_a_id == "sample_trace_test"
    assert comparison.trace_b_id == "looping_trace_test"
    assert comparison.divergence_step is not None
    assert len(comparison.step_diffs) >= 2
