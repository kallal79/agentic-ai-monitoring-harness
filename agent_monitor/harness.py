"""
agent_monitor.harness

Core evaluation harness that ingests agent traces, orchestrates all detectors,
calculates scores, and aggregates results.
"""

from datetime import datetime, timezone
import json
import os
import time
from typing import List, Optional
from agent_monitor.detectors import (
    BaseDetector,
    GoalDriftDetector,
    HallucinationDetector,
    LoopingDetector,
    ToolMisuseDetector,
    UnsafeActionDetector,
)
from agent_monitor.models import (
    AgentTrace,
    DetectedIssue,
    EvaluationResult,
    FailureCategory,
)
from agent_monitor.scoring import TraceScorer


class EvaluationHarness:
    """Orchestrates multi-detector evaluation pipelines on agent traces."""

    def __init__(self, detectors: Optional[List[BaseDetector]] = None):
        if detectors is not None:
            self.detectors = detectors
        else:
            self.detectors = [
                LoopingDetector(),
                ToolMisuseDetector(),
                HallucinationDetector(),
                GoalDriftDetector(),
                UnsafeActionDetector(),
            ]
        self.scorer = TraceScorer()

    def evaluate_trace(self, trace: AgentTrace) -> EvaluationResult:
        """Run all detectors against an agent trace and compute evaluation results."""
        start_time = time.perf_counter()
        all_issues: List[DetectedIssue] = []

        for detector in self.detectors:
            try:
                issues = detector.detect(trace)
                all_issues.extend(issues)
            except Exception as e:
                # Catch any unexpected detector error gracefully
                print(f"[WARN] Error running detector {detector.name}: {e}")

        # Derive unique detected failure categories
        detected_categories = list(set(issue.category for issue in all_issues))

        # Calculate scores
        score = self.scorer.calculate_score(all_issues)
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        return EvaluationResult(
            trace_id=trace.trace_id,
            goal=trace.goal,
            step_count=len(trace.steps),
            issues=all_issues,
            score=score,
            detected_failures=detected_categories,
            ground_truth=trace.ground_truth,
            evaluation_timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=latency_ms,
        )

    def evaluate_trace_file(self, file_path: str) -> EvaluationResult:
        """Load a JSON trace file and run evaluation."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        trace = AgentTrace.model_validate(data)
        return self.evaluate_trace(trace)

    def evaluate_directory(self, dir_path: str) -> List[EvaluationResult]:
        """Load and evaluate all .json trace files in a directory."""
        results: List[EvaluationResult] = []
        if not os.path.exists(dir_path):
            raise FileNotFoundError(f"Trace directory '{dir_path}' does not exist.")

        filenames = sorted(os.listdir(dir_path))
        for filename in filenames:
            if filename.endswith(".json"):
                full_path = os.path.join(dir_path, filename)
                res = self.evaluate_trace_file(full_path)
                results.append(res)

        return results
