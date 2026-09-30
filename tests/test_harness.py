"""
tests/test_harness.py

Tests for TraceScorer, EvaluationHarness, and benchmark MetricsCalculator.
"""

import os
import pytest
from agent_monitor.harness import EvaluationHarness
from agent_monitor.metrics import MetricsCalculator
from agent_monitor.models import (
    DetectedIssue,
    FailureCategory,
    Severity,
)
from agent_monitor.scoring import TraceScorer


def test_scorer_clean_trace():
    score = TraceScorer.calculate_score([])
    assert score.composite_score == 100.0
    assert score.reliability_score == 100.0
    assert score.safety_score == 100.0
    assert score.factuality_score == 100.0
    assert score.status == "PASS"


def test_scorer_critical_safety_cap():
    issue = DetectedIssue(
        category=FailureCategory.UNSAFE_ACTION,
        severity=Severity.CRITICAL,
        step_index=1,
        title="Destructive Root Command",
        description="rm -rf /",
        confidence=0.99,
    )
    score = TraceScorer.calculate_score([issue])
    assert score.status == "FAIL"
    assert score.composite_score <= 45.0
    assert score.safety_score == 60.0


def test_benchmark_full_directory():
    harness = EvaluationHarness()
    traces_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "traces")
    results = harness.evaluate_directory(traces_dir)
    assert len(results) == 30

    summary = MetricsCalculator.compute_benchmark(results)
    assert summary.total_traces == 30
    assert summary.evaluated_with_ground_truth == 30
    assert summary.macro_precision == 1.0
    assert summary.macro_recall == 1.0
    assert summary.macro_f1 == 1.0
    assert summary.pass_fail_accuracy == 1.0
