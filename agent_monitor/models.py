"""
agent_monitor.models

Core data structures and schemas for Agentic AI Monitoring & Evaluation.
Validates agent traces, detector outputs, scoring results, and ground truth labels.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class FailureCategory(str, Enum):
    LOOPING = "looping"
    TOOL_MISUSE = "tool_misuse"
    HALLUCINATION = "hallucination"
    GOAL_DRIFT = "goal_drift"
    UNSAFE_ACTION = "unsafe_action"


class ToolCall(BaseModel):
    """Represents a tool execution invocation by an agent."""
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class TraceStep(BaseModel):
    """A discrete step in an agent's trajectory: thought -> action -> tool call -> observation."""
    step_index: int
    thought: str = ""
    action: str = ""
    tool_call: Optional[ToolCall] = None
    observation: Optional[Union[str, Dict[str, Any], List[Any], int, float, bool]] = None
    timestamp: Optional[str] = None
    step_duration_ms: Optional[float] = None
    tokens_used: Optional[Dict[str, int]] = None


class GroundTruth(BaseModel):
    """Ground truth labeling for benchmark evaluation (precision, recall, F1)."""
    is_passing: bool
    failures: List[FailureCategory] = Field(default_factory=list)
    notes: Optional[str] = None


class TraceMetadata(BaseModel):
    """Metadata describing the agent environment, sandbox limits, and permissions."""
    agent_id: Optional[str] = "agent-generic"
    agent_name: Optional[str] = "Autonomous Assistant"
    domain: Optional[str] = "general"
    model_name: Optional[str] = "gpt-4o"
    framework: Optional[str] = "langchain-react"
    total_tokens: Optional[int] = None
    allowed_tools: Optional[List[str]] = None
    security_policy: Optional[Dict[str, Any]] = None


class AgentTrace(BaseModel):
    """Structured representation of an agent's end-to-end execution trace."""
    trace_id: str
    goal: str
    steps: List[TraceStep] = Field(default_factory=list)
    final_response: Optional[str] = None
    metadata: TraceMetadata = Field(default_factory=TraceMetadata)
    ground_truth: Optional[GroundTruth] = None


class DetectedIssue(BaseModel):
    """A flagged problematic behavior discovered by a detector."""
    category: FailureCategory
    severity: Severity
    step_index: Optional[int] = None
    title: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    recommendation: Optional[str] = None


class TraceScore(BaseModel):
    """Explainable scoring metrics for an evaluated trace."""
    composite_score: float = Field(ge=0.0, le=100.0)
    reliability_score: float = Field(ge=0.0, le=100.0)
    safety_score: float = Field(ge=0.0, le=100.0)
    factuality_score: float = Field(ge=0.0, le=100.0)
    status: str  # "PASS", "WARNING", "FAIL"
    deduction_summary: List[Dict[str, Any]] = Field(default_factory=list)
    explanation: str = ""


class EvaluationResult(BaseModel):
    """Comprehensive evaluation report for a single trace."""
    trace_id: str
    goal: str
    step_count: int
    issues: List[DetectedIssue] = Field(default_factory=list)
    score: TraceScore
    detected_failures: List[FailureCategory] = Field(default_factory=list)
    ground_truth: Optional[GroundTruth] = None
    evaluation_timestamp: str = ""
    latency_ms: float = 0.0
