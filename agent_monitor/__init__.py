"""
agent_monitor package

A lightweight, explainable monitoring and evaluation harness for autonomous AI agents.
Detects looping, tool misuse, hallucinated claims, goal drift, and unsafe actions.
"""

from agent_monitor.harness import EvaluationHarness
from agent_monitor.metrics import MetricsCalculator
from agent_monitor.models import (
    AgentTrace,
    DetectedIssue,
    EvaluationResult,
    FailureCategory,
    GroundTruth,
    Severity,
    ToolCall,
    TraceScore,
    TraceStep,
)
from agent_monitor.scoring import TraceScorer

__all__ = [
    "EvaluationHarness",
    "MetricsCalculator",
    "TraceScorer",
    "AgentTrace",
    "TraceStep",
    "ToolCall",
    "DetectedIssue",
    "EvaluationResult",
    "FailureCategory",
    "Severity",
    "GroundTruth",
    "TraceScore",
]
