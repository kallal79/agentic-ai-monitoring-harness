"""
agent_monitor.metrics

Statistical benchmark evaluator: Computes Precision, Recall, F1-Score,
Accuracy, and Confusion Matrix metrics against ground-truth labeled synthetic sets.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from agent_monitor.models import EvaluationResult, FailureCategory


class CategoryMetrics(BaseModel):
    category: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    accuracy: float = 0.0
    support: int = 0  # number of ground truth positive instances


class BenchmarkSummary(BaseModel):
    total_traces: int
    evaluated_with_ground_truth: int
    overall_pass_rate: float
    category_metrics: Dict[str, CategoryMetrics] = Field(default_factory=dict)
    macro_precision: float = 0.0
    macro_recall: float = 0.0
    macro_f1: float = 0.0
    pass_fail_accuracy: float = 0.0
    avg_latency_ms: float = 0.0


class MetricsCalculator:
    """Calculates precision, recall, and F1 across benchmark evaluation runs."""

    @staticmethod
    def compute_benchmark(results: List[EvaluationResult]) -> BenchmarkSummary:
        total = len(results)
        if total == 0:
            return BenchmarkSummary(total_traces=0, evaluated_with_ground_truth=0, overall_pass_rate=0.0)

        labeled_results = [r for r in results if r.ground_truth is not None]
        evaluated_gt = len(labeled_results)

        # Track category stats
        categories = [c.value for c in FailureCategory]
        stats: Dict[str, Dict[str, int]] = {
            cat: {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "support": 0}
            for cat in categories
        }

        # Track overall pass/fail agreement
        pass_fail_tp = 0  # GT is_passing == True and predicted status == PASS
        pass_fail_fp = 0  # GT is_passing == False and predicted status == PASS
        pass_fail_fn = 0  # GT is_passing == True and predicted status != PASS
        pass_fail_tn = 0  # GT is_passing == False and predicted status != PASS

        passing_count = sum(1 for r in results if r.score.status == "PASS")
        overall_pass_rate = round((passing_count / total) * 100.0, 1)

        total_latency = sum(r.latency_ms for r in results)
        avg_latency = round(total_latency / total, 2)

        for res in labeled_results:
            gt = res.ground_truth
            assert gt is not None

            gt_failures = set(f.value for f in gt.failures)
            detected_failures = set(f.value for f in res.detected_failures)

            # Overall pass/fail agreement
            predicted_pass = (res.score.status == "PASS")
            actual_pass = gt.is_passing

            if actual_pass and predicted_pass:
                pass_fail_tp += 1
            elif not actual_pass and predicted_pass:
                pass_fail_fp += 1
            elif actual_pass and not predicted_pass:
                pass_fail_fn += 1
            else:
                pass_fail_tn += 1

            # Per-category counts
            for cat in categories:
                has_gt = cat in gt_failures
                has_det = cat in detected_failures

                if has_gt:
                    stats[cat]["support"] += 1

                if has_gt and has_det:
                    stats[cat]["tp"] += 1
                elif not has_gt and has_det:
                    stats[cat]["fp"] += 1
                elif has_gt and not has_det:
                    stats[cat]["fn"] += 1
                else:
                    stats[cat]["tn"] += 1

        # Calculate metrics per category
        category_metrics: Dict[str, CategoryMetrics] = {}
        precisions: List[float] = []
        recalls: List[float] = []
        f1s: List[float] = []

        for cat in categories:
            s = stats[cat]
            tp = s["tp"]
            fp = s["fp"]
            fn = s["fn"]
            tn = s["tn"]

            denom_p = tp + fp
            prec = (tp / denom_p) if denom_p > 0 else (1.0 if fn == 0 else 0.0)

            denom_r = tp + fn
            rec = (tp / denom_r) if denom_r > 0 else (1.0 if fp == 0 else 0.0)

            denom_f1 = prec + rec
            f1 = (2 * prec * rec / denom_f1) if denom_f1 > 0 else 0.0

            acc = (tp + tn) / evaluated_gt if evaluated_gt > 0 else 1.0

            category_metrics[cat] = CategoryMetrics(
                category=cat,
                tp=tp,
                fp=fp,
                fn=fn,
                tn=tn,
                precision=round(prec, 3),
                recall=round(rec, 3),
                f1_score=round(f1, 3),
                accuracy=round(acc, 3),
                support=s["support"],
            )

            # Include in macro average if category had test samples or detections
            if s["support"] > 0 or denom_p > 0:
                precisions.append(prec)
                recalls.append(rec)
                f1s.append(f1)

        macro_p = sum(precisions) / len(precisions) if precisions else 0.0
        macro_r = sum(recalls) / len(recalls) if recalls else 0.0
        macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0

        pass_fail_acc = (
            (pass_fail_tp + pass_fail_tn) / evaluated_gt
            if evaluated_gt > 0
            else 0.0
        )

        return BenchmarkSummary(
            total_traces=total,
            evaluated_with_ground_truth=evaluated_gt,
            overall_pass_rate=overall_pass_rate,
            category_metrics=category_metrics,
            macro_precision=round(macro_p, 3),
            macro_recall=round(macro_r, 3),
            macro_f1=round(macro_f1, 3),
            pass_fail_accuracy=round(pass_fail_acc, 3),
            avg_latency_ms=avg_latency,
        )
