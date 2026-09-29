"""
dashboard.app

FastAPI server providing REST APIs and static dashboard interface
for real-time agent evaluation and benchmark exploration.
"""

import json
import os
from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from agent_monitor.harness import EvaluationHarness
from agent_monitor.metrics import MetricsCalculator
from agent_monitor.models import AgentTrace, EvaluationResult
from agent_monitor.tool_registry import DEFAULT_TOOL_REGISTRY

app = FastAPI(
    title="Agentic AI Monitoring Dashboard API",
    description="Observability, evaluation, and safety scoring harness for autonomous AI agents.",
    version="1.0.0",
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


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Agentic AI Monitoring Dashboard</h1><p>Static files loading...</p>")


@app.get("/api/benchmark")
async def get_benchmark():
    """Returns aggregated benchmark metrics over all benchmark traces."""
    results = harness.evaluate_directory(TRACES_DIR)
    summary = MetricsCalculator.compute_benchmark(results)
    return summary.model_dump()


@app.get("/api/traces")
async def get_all_traces():
    """Returns evaluation results and details for all test traces."""
    results = harness.evaluate_directory(TRACES_DIR)
    return [r.model_dump() for r in results]


@app.get("/api/trace/{trace_id}")
async def get_trace_details(trace_id: str):
    """Retrieve full raw trace content and evaluation result for a trace ID."""
    trace_path = os.path.join(TRACES_DIR, f"{trace_id}.json")
    if not os.path.exists(trace_path):
        # Try finding without extension if needed
        matching = [f for f in os.listdir(TRACES_DIR) if f.startswith(trace_id) and f.endswith(".json")]
        if matching:
            trace_path = os.path.join(TRACES_DIR, matching[0])
        else:
            raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found.")

    with open(trace_path, "r", encoding="utf-8") as f:
        raw_trace = json.load(f)

    trace = AgentTrace.model_validate(raw_trace)
    eval_result = harness.evaluate_trace(trace)

    return {
        "raw_trace": raw_trace,
        "evaluation": eval_result.model_dump(),
    }


@app.post("/api/eval")
async def evaluate_custom_trace(trace_data: Dict[str, Any]):
    """Evaluate an arbitrary agent trace payload on-the-fly."""
    try:
        trace = AgentTrace.model_validate(trace_data)
        eval_result = harness.evaluate_trace(trace)
        return eval_result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid agent trace schema: {str(e)}")


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
