"""
run_monitor.py

CLI entrypoint for Agentic AI Monitoring & Evaluation Harness.
Provides commands to evaluate traces, generate benchmark reports, and launch the interactive dashboard.

Usage:
  python run_monitor.py eval [--dir data/traces] [--trace path/to/trace.json]
  python run_monitor.py report [--dir data/traces] [--output reports/monitoring_report.html]
  python run_monitor.py serve [--port 8000]
"""

import argparse
import json
import os
import sys

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_monitor.harness import EvaluationHarness
from agent_monitor.metrics import MetricsCalculator
from agent_monitor.reporter import ReportGenerator


def run_eval(args):
    harness = EvaluationHarness()
    results = []

    if args.trace:
        if not os.path.exists(args.trace):
            print(f"[ERROR] Trace file not found: {args.trace}")
            sys.exit(1)
        res = harness.evaluate_trace_file(args.trace)
        results.append(res)
    else:
        trace_dir = args.dir or os.path.join("data", "traces")
        if not os.path.exists(trace_dir):
            print(f"[ERROR] Trace directory not found: {trace_dir}")
            sys.exit(1)
        results = harness.evaluate_directory(trace_dir)

    summary = MetricsCalculator.compute_benchmark(results)
    ReportGenerator.print_terminal_summary(results, summary)

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "summary": summary.model_dump(),
                    "results": [r.model_dump() for r in results],
                },
                f,
                indent=2,
                default=str,
            )
        print(f"[INFO] JSON benchmark results exported to: {args.json}")

    return results, summary


def run_report(args):
    results, summary = run_eval(args)
    output_html = args.output or os.path.join("reports", "monitoring_report.html")
    ReportGenerator.generate_html_report(results, summary, output_html)
    print(f"\n[SUCCESS] Standalone HTML Dashboard Report generated at: {os.path.abspath(output_html)}")


def run_serve(args):
    import uvicorn
    from dashboard.app import app

    port = args.port or 8000
    print(f"\n=======================================================")
    print(f"  LAUNCHING AGENTIC AI MONITORING DASHBOARD")
    print(f"  URL: http://127.0.0.1:{port}")
    print(f"=======================================================\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


def main():
    parser = argparse.ArgumentParser(
        description="Agentic AI Monitoring Harness & Benchmark Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: eval
    eval_parser = subparsers.add_parser("eval", help="Evaluate traces and display metrics")
    eval_parser.add_argument("--trace", type=str, help="Path to single trace JSON file")
    eval_parser.add_argument("--dir", type=str, default="data/traces", help="Directory of trace JSON files")
    eval_parser.add_argument("--json", type=str, default="reports/evaluation_results.json", help="Path to output JSON summary")

    # Command: report
    report_parser = subparsers.add_parser("report", help="Run benchmark and generate HTML report")
    report_parser.add_argument("--trace", type=str, help="Path to single trace JSON file")
    report_parser.add_argument("--dir", type=str, default="data/traces", help="Directory of trace JSON files")
    report_parser.add_argument("--output", type=str, default="reports/monitoring_report.html", help="Path to output HTML report")
    report_parser.add_argument("--json", type=str, default="reports/evaluation_results.json", help="Path to output JSON summary")

    # Command: serve
    serve_parser = subparsers.add_parser("serve", help="Launch interactive web dashboard server")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to serve web dashboard (default: 8000)")

    args = parser.parse_args()

    if args.command == "eval":
        run_eval(args)
    elif args.command == "report":
        run_report(args)
    elif args.command == "serve":
        run_serve(args)
    else:
        # Default behavior: run report if no arguments provided
        args.dir = "data/traces"
        args.trace = None
        args.output = "reports/monitoring_report.html"
        args.json = "reports/evaluation_results.json"
        run_report(args)


if __name__ == "__main__":
    main()
