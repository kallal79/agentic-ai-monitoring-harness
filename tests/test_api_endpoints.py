"""
tests/test_api_endpoints.py

Integration tests for FastAPI REST API endpoints:
- /api/benchmark (including economics)
- /api/traces
- /api/trace/{trace_id}
- /api/trace/{trace_id}/dag
- /api/trace/{trace_id}/otel
- /api/policies and /api/policies/toggle
- /api/compare
"""

import pytest
from fastapi.testclient import TestClient
from dashboard.app import app

client = TestClient(app)


def test_api_benchmark_endpoint():
    res = client.get("/api/benchmark")
    assert res.status_code == 200
    data = res.json()
    assert "total_traces" in data
    assert "macro_precision" in data
    assert "macro_recall" in data
    assert "macro_f1" in data
    assert "economics" in data
    assert data["economics"]["total_tokens_consumed"] > 0
    assert data["economics"]["total_cost_usd"] > 0


def test_api_traces_endpoint():
    res = client.get("/api/traces")
    assert res.status_code == 200
    traces = res.json()
    assert len(traces) == 30
    first = traces[0]
    assert "cost_profile" in first
    assert "total_tokens" in first["cost_profile"]
    assert "total_cost_usd" in first["cost_profile"]


def test_api_trace_details_endpoint():
    res = client.get("/api/trace/trace_01_healthy_devops")
    assert res.status_code == 200
    data = res.json()
    assert "raw_trace" in data
    assert "evaluation" in data
    assert "profile" in data
    assert "dag" in data
    assert "policy_report" in data


def test_api_trace_dag_endpoint():
    res = client.get("/api/trace/trace_01_healthy_devops/dag")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0


def test_api_trace_otel_endpoint():
    res = client.get("/api/trace/trace_01_healthy_devops/otel")
    assert res.status_code == 200
    data = res.json()
    assert "spans" in data
    assert len(data["spans"]) > 0


def test_api_policies_endpoints():
    res = client.get("/api/policies")
    assert res.status_code == 200
    policies = res.json()
    assert len(policies) >= 6

    # Test policy toggle
    rule_id = policies[0]["rule_id"]
    toggle_res = client.post("/api/policies/toggle", json={"rule_id": rule_id, "is_enabled": False})
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_enabled"] is False

    # Restore
    client.post("/api/policies/toggle", json={"rule_id": rule_id, "is_enabled": True})


def test_api_compare_endpoint():
    res = client.post(
        "/api/compare",
        json={"trace_a_id": "trace_01_healthy_devops", "trace_b_id": "trace_05_looping_exact_search"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "score_delta" in data
    assert "divergence_step" in data
    assert len(data["step_diffs"]) > 0
