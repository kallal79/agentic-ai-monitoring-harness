"""
dashboard.app

FastAPI server providing REST APIs and static dashboard interface
for real-time agent evaluation, execution DAG visualizer, token economics,
runtime guardrail policy engine, and OpenTelemetry GenAI export.
"""

import json
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent_monitor.harness import EvaluationHarness
from agent_monitor.metrics import MetricsCalculator
from agent_monitor.models import AgentTrace, EvaluationResult
from agent_monitor.tool_registry import DEFAULT_TOOL_REGISTRY
from agent_monitor.profiler import ResourceProfiler
from agent_monitor.dag import DAGBuilder
from agent_monitor.policy import PolicyEngine, DEFAULT_POLICIES
from agent_monitor.opentelemetry_exporter import OpenTelemetryExporter
from agent_monitor.comparator import TraceComparator

app = FastAPI(
    title="Agentic AI Monitoring & Observability API",
    description="Observability, behavioral evaluation, execution DAGs, token economics, and runtime guardrails for AI agents.",
    version="1.2.0",
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
REPO_ROOT = os.path.dirname(BASE_DIR)
TRACES_DIR = os.path.join(REPO_ROOT, "data", "traces")
SCREENSHOTS_DIR = os.path.join(REPO_ROOT, "screenshots")

harness = EvaluationHarness()
policy_engine = PolicyEngine(DEFAULT_POLICIES)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if os.path.exists(SCREENSHOTS_DIR):
    app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")


@app.get("/architecture_diagram.png")
async def serve_architecture_diagram():
    p = os.path.join(REPO_ROOT, "architecture_diagram.png")
    if os.path.exists(p):
        return FileResponse(p, media_type="image/png")
    raise HTTPException(status_code=404, detail="Architecture diagram not found")


@app.get("/linkedin_post_visual.png")
async def serve_linkedin_visual():
    p = os.path.join(REPO_ROOT, "linkedin_post_visual.png")
    if os.path.exists(p):
        return FileResponse(p, media_type="image/png")
    raise HTTPException(status_code=404, detail="LinkedIn visual not found")


@app.get("/download-all-images")
async def download_all_images():
    zip_path = os.path.join(REPO_ROOT, "all_project_images.zip")
    if os.path.exists(zip_path):
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename="all_project_images.zip",
        )
    raise HTTPException(status_code=404, detail="Image bundle not found")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Agentic AI Monitoring Dashboard</h1><p>Static files loading...</p>")


def _load_trace(trace_id: str) -> AgentTrace:
    trace_path = os.path.join(TRACES_DIR, f"{trace_id}.json")
    if not os.path.exists(trace_path):
        matching = [f for f in os.listdir(TRACES_DIR) if f.startswith(trace_id) and f.endswith(".json")]
        if matching:
            trace_path = os.path.join(TRACES_DIR, matching[0])
        else:
            raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found.")

    with open(trace_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return AgentTrace.model_validate(data)


@app.get("/api/benchmark")
async def get_benchmark():
    """Returns aggregated benchmark metrics over all benchmark traces including token & cost stats."""
    results = harness.evaluate_directory(TRACES_DIR)
    summary = MetricsCalculator.compute_benchmark(results)
    total_tokens = 0
    total_cost = 0.0
    total_wasted_tokens = 0
    traces = [AgentTrace.model_validate(json.load(open(os.path.join(TRACES_DIR, f), "r", encoding="utf-8"))) for f in os.listdir(TRACES_DIR) if f.endswith(".json")]
    for t in traces:
        prof = ResourceProfiler.profile_trace(t)
        total_tokens += prof.total_tokens
        total_cost += prof.total_cost_usd
        total_wasted_tokens += prof.wasted_tokens
    data = summary.model_dump()
    data["economics"] = {
        "total_tokens_consumed": total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "avg_tokens_per_trace": int(total_tokens / max(1, len(traces))),
        "avg_cost_per_trace_usd": round(total_cost / max(1, len(traces)), 4),
        "total_wasted_tokens": total_wasted_tokens,
    }
    return data


@app.get("/api/traces")
async def get_all_traces():
    """Returns evaluation results, economics, and telemetry for all test traces."""
    results = harness.evaluate_directory(TRACES_DIR)
    out = []
    for r in results:
        t = _load_trace(r.trace_id)
        prof = ResourceProfiler.profile_trace(t)
        d = r.model_dump()
        d["cost_profile"] = {
            "total_tokens": prof.total_tokens,
            "total_cost_usd": prof.total_cost_usd,
            "wasted_tokens": prof.wasted_tokens,
            "token_burn_alert": prof.token_burn_alert,
            "efficiency_ratio": prof.cost_efficiency_ratio,
        }
        out.append(d)
    return out


@app.get("/api/trace/{trace_id}")
async def get_trace_details(trace_id: str):
    """Retrieve full raw trace, evaluation, resource profile, and DAG."""
    trace = _load_trace(trace_id)
    eval_result = harness.evaluate_trace(trace)
    profile = ResourceProfiler.profile_trace(trace)
    dag = DAGBuilder.build_dag(trace, eval_result)
    policy_report = policy_engine.evaluate_trace(trace)
    return {
        "raw_trace": trace.model_dump(),
        "evaluation": eval_result.model_dump(),
        "profile": profile.model_dump(),
        "dag": dag.model_dump(),
        "policy_report": policy_report.model_dump(),
    }


@app.get("/api/trace/{trace_id}/dag")
async def get_trace_dag(trace_id: str):
    """Returns interactive Execution DAG node graph for visualization."""
    trace = _load_trace(trace_id)
    eval_result = harness.evaluate_trace(trace)
    dag = DAGBuilder.build_dag(trace, eval_result)
    return dag.model_dump()


@app.get("/api/trace/{trace_id}/otel")
async def export_trace_opentelemetry(trace_id: str):
    """Export trace as OpenTelemetry GenAI Semantic Convention Spans."""
    trace = _load_trace(trace_id)
    eval_result = harness.evaluate_trace(trace)
    otel = OpenTelemetryExporter.export_trace(trace, eval_result)
    return JSONResponse(
        content=otel.model_dump(),
        headers={"Content-Disposition": f"attachment; filename=otel_{trace_id}.json"}
    )


@app.post("/api/eval")
async def evaluate_custom_trace(trace_data: Dict[str, Any]):
    """Evaluate an arbitrary agent trace payload on-the-fly."""
    try:
        trace = AgentTrace.model_validate(trace_data)
        eval_result = harness.evaluate_trace(trace)
        profile = ResourceProfiler.profile_trace(trace)
        policy_report = policy_engine.evaluate_trace(trace)
        dag = DAGBuilder.build_dag(trace, eval_result)
        return {
            "evaluation": eval_result.model_dump(),
            "profile": profile.model_dump(),
            "policy_report": policy_report.model_dump(),
            "dag": dag.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid agent trace schema: {str(e)}")


@app.get("/api/policies")
async def get_policies():
    """Lists active runtime guardrails."""
    return [p.model_dump() for p in policy_engine.policies.values()]


class PolicyToggleRequest(BaseModel):
    rule_id: str
    is_enabled: bool


@app.post("/api/policies/toggle")
async def toggle_policy(req: PolicyToggleRequest):
    """Toggle a guardrail policy rule on or off."""
    if req.rule_id in policy_engine.policies:
        policy_engine.policies[req.rule_id].is_enabled = req.is_enabled
        return {"status": "ok", "rule_id": req.rule_id, "is_enabled": req.is_enabled}
    raise HTTPException(status_code=404, detail="Policy rule not found")


class CompareRequest(BaseModel):
    trace_a_id: str
    trace_b_id: str


@app.post("/api/compare")
async def compare_traces(req: CompareRequest):
    """Side-by-side comparative diff between two traces."""
    trace_a = _load_trace(req.trace_a_id)
    trace_b = _load_trace(req.trace_b_id)
    eval_a = harness.evaluate_trace(trace_a)
    eval_b = harness.evaluate_trace(trace_b)
    comp = TraceComparator.compare(trace_a, trace_b, eval_a, eval_b)
    return comp.model_dump()


@app.get("/api/tools")
async def list_tools():
    """Lists registered tool catalog and schemas."""
    return {
        name: {
            "name": spec.name,
            "description": spec.description,
            "is_sensitive": spec.is_sensitive,
            "parameters": {
                p_name: {
                    "type": p.expected_type.__name__,
                    "required": p.required,
                    "description": p.description,
                }
                for p_name, p in spec.parameters.items()
            },
        }
        for name, spec in DEFAULT_TOOL_REGISTRY.items()
    }
