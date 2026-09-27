"""
agent_monitor.reporter

Generates comprehensive standalone HTML reports, JSON summaries, and formatted CLI tables
for agent evaluation results and benchmark metrics.
"""

import json
import os
from typing import List, Optional
from agent_monitor.metrics import BenchmarkSummary
from agent_monitor.models import EvaluationResult


class ReportGenerator:
    """Generates standalone HTML and terminal reports."""

    @staticmethod
    def generate_html_report(
        results: List[EvaluationResult],
        summary: BenchmarkSummary,
        output_path: str,
        title: str = "Agentic AI Monitoring & Evaluation Report",
    ) -> str:
        """Generate a self-contained, responsive HTML dashboard report."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        results_json = json.dumps([r.model_dump() for r in results], default=str)
        summary_json = json.dumps(summary.model_dump(), default=str)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #090d16;
      --card-bg: rgba(22, 28, 45, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --accent-cyan: #06b6d4;
      --accent-indigo: #6366f1;
      --accent-rose: #f43f5e;
      --accent-emerald: #10b981;
      --accent-amber: #f59e0b;
      --radius: 12px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ background: var(--bg); color: var(--text-main); line-height: 1.5; padding: 32px 20px; }}
    .container {{ max-width: 1300px; margin: 0 auto; }}
    header {{ margin-bottom: 32px; padding-bottom: 24px; border-bottom: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; }}
    .header-title h1 {{ font-size: 28px; font-weight: 700; background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
    .header-title p {{ color: var(--text-muted); font-size: 14px; margin-top: 4px; }}
    .badge-status {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
    .status-pass {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
    .status-fail {{ background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3); }}
    .status-warning {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }}
    
    /* KPI Grid */
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
    .kpi-card {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 20px; backdrop-filter: blur(12px); box-shadow: 0 4px 20px rgba(0,0,0,0.25); }}
    .kpi-label {{ font-size: 13px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }}
    .kpi-val {{ font-size: 32px; font-weight: 700; margin-top: 8px; color: #fff; }}
    
    /* Section Box */
    .section-box {{ background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 24px; margin-bottom: 32px; backdrop-filter: blur(12px); }}
    .section-title {{ font-size: 18px; font-weight: 600; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; }}
    
    /* Tables */
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; text-align: left; }}
    th {{ padding: 12px 14px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--card-border); }}
    td {{ padding: 14px; border-bottom: 1px solid rgba(255,255,255,0.04); vertical-align: middle; }}
    tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}
    
    .tag {{ display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
    .tag-critical {{ background: rgba(244, 63, 94, 0.2); color: #fb7185; }}
    .tag-high {{ background: rgba(249, 115, 22, 0.2); color: #fb923c; }}
    .tag-medium {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; }}
    .tag-low {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; }}
    
    /* Collapsible Details */
    details {{ margin-top: 8px; }}
    summary {{ cursor: pointer; color: var(--accent-cyan); font-weight: 600; outline: none; }}
    summary:hover {{ text-decoration: underline; }}
    .detail-body {{ background: rgba(0,0,0,0.3); border-radius: 8px; padding: 16px; margin-top: 10px; font-size: 13px; }}
    .score-breakdown {{ display: flex; gap: 16px; margin-top: 8px; font-size: 12px; color: var(--text-muted); }}
    .score-chip {{ background: rgba(255,255,255,0.05); padding: 4px 8px; border-radius: 4px; }}
    
    /* Step timeline */
    .step-item {{ border-left: 2px solid var(--accent-indigo); padding-left: 14px; margin-bottom: 14px; position: relative; }}
    .step-item.has-issue {{ border-left-color: var(--accent-rose); }}
    .step-header {{ font-weight: 600; color: #fff; margin-bottom: 4px; display: flex; gap: 8px; align-items: center; }}
    .step-content {{ color: var(--text-muted); font-size: 12px; margin-bottom: 4px; }}
    .issue-callout {{ background: rgba(244, 63, 94, 0.1); border-left: 3px solid #f43f5e; padding: 8px 12px; border-radius: 4px; margin-top: 6px; color: #fecdd3; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-title">
        <h1>Agentic AI Monitoring Harness</h1>
        <p>Automated Behavioral Evaluation, Safety Scrutiny & Detection Benchmark</p>
      </div>
      <div>
        <span class="badge-status status-pass">System Operational</span>
      </div>
    </header>

    <!-- KPI Metric Cards -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Total Traces Evaluated</div>
        <div class="kpi-val">{summary.total_traces}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Benchmark Pass Rate</div>
        <div class="kpi-val" style="color: {'#34d399' if summary.overall_pass_rate >= 50 else '#fb7185'};">{summary.overall_pass_rate}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Macro Precision</div>
        <div class="kpi-val" style="color: #38bdf8;">{summary.macro_precision * 100:.1f}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Macro Recall</div>
        <div class="kpi-val" style="color: #a78bfa;">{summary.macro_recall * 100:.1f}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Macro F1 Score</div>
        <div class="kpi-val" style="color: #34d399;">{summary.macro_f1 * 100:.1f}%</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Avg Trace Latency</div>
        <div class="kpi-val" style="color: #f59e0b;">{summary.avg_latency_ms} ms</div>
      </div>
    </div>

    <!-- Category Performance Table -->
    <div class="section-box">
      <div class="section-title">
        <span>Failure Mode Detector Benchmark (Ground Truth Labeled)</span>
        <span style="font-size: 13px; font-weight: normal; color: var(--text-muted);">Evaluated on {summary.evaluated_with_ground_truth} Traces</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Failure Category</th>
            <th>Support (GT)</th>
            <th>TP</th>
            <th>FP</th>
            <th>FN</th>
            <th>TN</th>
            <th>Precision</th>
            <th>Recall</th>
            <th>F1 Score</th>
            <th>Accuracy</th>
          </tr>
        </thead>
        <tbody>
"""

        for cat_name, m in summary.category_metrics.items():
            f1_color = "#34d399" if m.f1_score >= 0.90 else ("#fbbf24" if m.f1_score >= 0.75 else "#fb7185")
            html += f"""
          <tr>
            <td><strong>{cat_name.replace('_', ' ').title()}</strong></td>
            <td>{m.support}</td>
            <td>{m.tp}</td>
            <td>{m.fp}</td>
            <td>{m.fn}</td>
            <td>{m.tn}</td>
            <td>{m.precision * 100:.1f}%</td>
            <td>{m.recall * 100:.1f}%</td>
            <td style="color: {f1_color}; font-weight: 700;">{m.f1_score * 100:.1f}%</td>
            <td>{m.accuracy * 100:.1f}%</td>
          </tr>
"""

        html += f"""
        </tbody>
      </table>
    </div>

    <!-- Trace Explorer Table -->
    <div class="section-box">
      <div class="section-title">
        <span>Trace-by-Trace Diagnostic Inspection</span>
        <span style="font-size: 13px; font-weight: normal; color: var(--text-muted);">{len(results)} Traces Analyzed</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Trace ID</th>
            <th>Goal Summary</th>
            <th>Steps</th>
            <th>Status</th>
            <th>Score</th>
            <th>Detected Failures</th>
            <th>Ground Truth Match</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
"""

        for r in results:
            status_cls = "status-pass" if r.score.status == "PASS" else ("status-warning" if r.score.status == "WARNING" else "status-fail")
            gt_text = "N/A"
            gt_match = True
            if r.ground_truth:
                gt_actual = "PASS" if r.ground_truth.is_passing else "FAIL"
                pred = "PASS" if r.score.status == "PASS" else "FAIL"
                gt_match = (gt_actual == pred)
                gt_text = f"{gt_actual} [{'MATCH' if gt_match else 'MISMATCH'}]"

            failures_str = ", ".join([f.value.replace('_', ' ') for f in r.detected_failures]) if r.detected_failures else "None (Nominal)"

            # Build detailed issue items
            issues_html = ""
            for iss in r.issues:
                sev_cls = f"tag-{iss.severity.value.lower()}"
                step_txt = f"Step {iss.step_index}" if iss.step_index is not None else "Global / Final"
                issues_html += f"""
                  <div class="issue-callout">
                    <span class="tag {sev_cls}">{iss.severity.value}</span>
                    <strong style="margin-left: 6px;">{iss.title}</strong> ({step_txt})
                    <p style="margin-top: 4px; font-size: 12px; color: #f1f5f9;">{iss.description}</p>
                    {f'<p style="margin-top: 4px; font-size: 11px; color: #93c5fd;">Recommendation: {iss.recommendation}</p>' if iss.recommendation else ''}
                  </div>
                """

            if not issues_html:
                issues_html = "<p style='color: #34d399; font-size: 13px;'>Zero issues flagged. Nominal and safe execution.</p>"

            html += f"""
          <tr>
            <td><code>{r.trace_id}</code></td>
            <td style="max-width: 320px; font-size: 13px;">{r.goal[:90]}...</td>
            <td>{r.step_count}</td>
            <td><span class="badge-status {status_cls}">{r.score.status}</span></td>
            <td><strong>{r.score.composite_score}/100</strong></td>
            <td style="font-size: 12px;">{failures_str}</td>
            <td><span style="color: {'#34d399' if gt_match else '#fb7185'}; font-weight: 600;">{gt_text}</span></td>
            <td>
              <details>
                <summary>Inspect</summary>
                <div class="detail-body">
                  <div class="score-breakdown">
                    <span class="score-chip">Reliability: {r.score.reliability_score}/100</span>
                    <span class="score-chip">Safety: {r.score.safety_score}/100</span>
                    <span class="score-chip">Factuality: {r.score.factuality_score}/100</span>
                    <span class="score-chip">Latency: {r.latency_ms} ms</span>
                  </div>
                  <p style="margin-top: 8px; font-size: 12px; color: #cbd5e1;"><strong>Scoring Rationale:</strong> {r.score.explanation}</p>
                  <div style="margin-top: 12px;">
                    <strong>Flagged Behavioral Anomalies:</strong>
                    {issues_html}
                  </div>
                </div>
              </details>
            </td>
          </tr>
"""

        html += f"""
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return output_path

    @staticmethod
    def print_terminal_summary(results: List[EvaluationResult], summary: BenchmarkSummary):
        """Print rich, readable summary to console."""
        print("\n" + "=" * 80)
        print("  AGENTIC AI MONITORING HARNESS - BENCHMARK & EVALUATION SUMMARY")
        print("=" * 80)
        print(f"  Total Traces Evaluated : {summary.total_traces}")
        print(f"  Benchmark Pass Rate    : {summary.overall_pass_rate}%")
        print(f"  Overall Classification : {summary.pass_fail_accuracy * 100:.1f}% Accuracy")
        print(f"  Macro Precision        : {summary.macro_precision * 100:.1f}%")
        print(f"  Macro Recall           : {summary.macro_recall * 100:.1f}%")
        print(f"  Macro F1-Score         : {summary.macro_f1 * 100:.1f}%")
        print(f"  Average Trace Latency  : {summary.avg_latency_ms} ms")
        print("-" * 80)
        print(f"  {'Category':<22} | {'GT':<4} | {'TP':<4} | {'FP':<4} | {'FN':<4} | {'Prec':<7} | {'Recall':<7} | {'F1':<7}")
        print("-" * 80)
        for cat, m in summary.category_metrics.items():
            print(f"  {cat:<22} | {m.support:<4} | {m.tp:<4} | {m.fp:<4} | {m.fn:<4} | {m.precision * 100:>5.1f}% | {m.recall * 100:>5.1f}% | {m.f1_score * 100:>5.1f}%")
        print("=" * 80)
        print("\n  INDIVIDUAL TRACE VERDICTS:")
        print(f"  {'Trace ID':<35} | {'Status':<7} | {'Score':<5} | {'Issues Flagged'}")
        print("-" * 80)
        for r in results:
            issues_summary = ", ".join([f"{i.severity.value}:{i.category.value}" for i in r.issues]) or "None (Clean)"
            print(f"  {r.trace_id:<35} | {r.score.status:<7} | {r.score.composite_score:<5.1f} | {issues_summary}")
        print("=" * 80 + "\n")
