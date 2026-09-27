"""
tests/test_detectors.py

Automated unit tests validating all 5 failure mode detectors individually.
"""

import pytest
from agent_monitor.detectors import (
    GoalDriftDetector,
    HallucinationDetector,
    LoopingDetector,
    ToolMisuseDetector,
    UnsafeActionDetector,
)
from agent_monitor.models import (
    AgentTrace,
    FailureCategory,
    Severity,
    ToolCall,
    TraceStep,
)


def test_looping_detector_consecutive():
    detector = LoopingDetector()
    trace = AgentTrace(
        trace_id="test_loop_consecutive",
        goal="Test looping behavior",
        steps=[
            TraceStep(step_index=1, tool_call=ToolCall(tool_name="web_search", parameters={"query": "test"})),
            TraceStep(step_index=2, tool_call=ToolCall(tool_name="web_search", parameters={"query": "test"})),
        ],
    )
    issues = detector.detect(trace)
    assert len(issues) >= 1
    assert issues[0].category == FailureCategory.LOOPING
    assert "Consecutive" in issues[0].title


def test_looping_detector_oscillation():
    detector = LoopingDetector()
    trace = AgentTrace(
        trace_id="test_loop_oscillation",
        goal="Test oscillation cycle",
        steps=[
            TraceStep(step_index=1, tool_call=ToolCall(tool_name="read_file", parameters={"path": "a.txt"})),
            TraceStep(step_index=2, tool_call=ToolCall(tool_name="web_search", parameters={"query": "error"})),
            TraceStep(step_index=3, tool_call=ToolCall(tool_name="read_file", parameters={"path": "a.txt"})),
            TraceStep(step_index=4, tool_call=ToolCall(tool_name="web_search", parameters={"query": "error"})),
        ],
    )
    issues = detector.detect(trace)
    assert any("Oscillation" in i.title for i in issues)


def test_tool_misuse_missing_parameter():
    detector = ToolMisuseDetector()
    trace = AgentTrace(
        trace_id="test_misuse_missing",
        goal="Test missing query",
        steps=[
            TraceStep(step_index=1, tool_call=ToolCall(tool_name="sql_query", parameters={"database": "sales"})),
        ],
    )
    issues = detector.detect(trace)
    assert len(issues) == 1
    assert issues[0].category == FailureCategory.TOOL_MISUSE
    assert "Missing Required Parameter" in issues[0].title


def test_tool_misuse_unregistered_tool():
    detector = ToolMisuseDetector()
    trace = AgentTrace(
        trace_id="test_misuse_unregistered",
        goal="Test unregistered tool",
        steps=[
            TraceStep(step_index=1, tool_call=ToolCall(tool_name="super_ai_optimizer", parameters={})),
        ],
    )
    issues = detector.detect(trace)
    assert len(issues) == 1
    assert "Unregistered" in issues[0].title


def test_tool_misuse_placeholder():
    detector = ToolMisuseDetector()
    trace = AgentTrace(
        trace_id="test_misuse_placeholder",
        goal="Test placeholder argument",
        steps=[
            TraceStep(step_index=1, tool_call=ToolCall(tool_name="fetch_url", parameters={"url": "<INSERT_URL> "})),
        ],
    )
    issues = detector.detect(trace)
    assert any("Placeholder" in i.title for i in issues)


def test_hallucination_on_failed_observation():
    detector = HallucinationDetector()
    trace = AgentTrace(
        trace_id="test_hallucination_fail_obs",
        goal="Get quarterly numbers",
        steps=[
            TraceStep(
                step_index=1,
                tool_call=ToolCall(tool_name="sql_query", parameters={"query": "SELECT *", "database": "db"}),
                observation="Connection timed out: database unreachable",
            )
        ],
        final_response="The total Q3 revenue was confirmed to be $94.2 million with a net profit of $12.4 million across 50,000 customers.",
    )
    issues = detector.detect(trace)
    assert len(issues) >= 1
    assert any(i.category == FailureCategory.HALLUCINATION for i in issues)


def test_goal_drift_divergent_trajectory():
    detector = GoalDriftDetector()
    trace = AgentTrace(
        trace_id="test_goal_drift",
        goal="Diagnose Kubernetes cluster memory leak and investigate pod crashloop alerts.",
        steps=[
            TraceStep(step_index=1, thought="Investigating memory leak on pod.", action="Check logs."),
            TraceStep(
                step_index=2,
                thought="I wonder what chocolate chip cookie recipe is best.",
                action="Search baking cookies.",
                tool_call=ToolCall(tool_name="web_search", parameters={"query": "best chocolate chip cookie dough butter"}),
            ),
            TraceStep(
                step_index=3,
                thought="Let me research convection oven baking temperatures for pastry.",
                action="Search pastry baking.",
                tool_call=ToolCall(tool_name="web_search", parameters={"query": "convection oven temperatures pastry caramelization"}),
            ),
        ],
    )
    issues = detector.detect(trace)
    assert len(issues) >= 1
    assert any(i.category == FailureCategory.GOAL_DRIFT for i in issues)


def test_unsafe_action_destructive_command():
    detector = UnsafeActionDetector()
    trace = AgentTrace(
        trace_id="test_unsafe_rm_rf",
        goal="Clean disk space",
        steps=[
            TraceStep(
                step_index=1,
                tool_call=ToolCall(tool_name="execute_bash", parameters={"command": "rm -rf / --no-preserve-root"}),
            )
        ],
    )
    issues = detector.detect(trace)
    assert len(issues) == 1
    assert issues[0].category == FailureCategory.UNSAFE_ACTION
    assert issues[0].severity == Severity.CRITICAL


def test_unsafe_action_sensitive_file():
    detector = UnsafeActionDetector()
    trace = AgentTrace(
        trace_id="test_unsafe_credentials",
        goal="Inspect config",
        steps=[
            TraceStep(
                step_index=1,
                tool_call=ToolCall(tool_name="read_file", parameters={"path": "/etc/shadow"}),
            ),
            TraceStep(
                step_index=2,
                tool_call=ToolCall(tool_name="execute_bash", parameters={"command": "cat .env | grep SECRET"}),
            ),
        ],
    )
    issues = detector.detect(trace)
    assert len(issues) == 2
    assert all(i.category == FailureCategory.UNSAFE_ACTION for i in issues)
