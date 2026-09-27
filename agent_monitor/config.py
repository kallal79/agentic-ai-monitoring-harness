"""
agent_monitor.config

Configuration schemas and default threshold settings for agent monitoring detectors,
scoring rules, and security enforcement policies.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class LoopingDetectorConfig(BaseModel):
    consecutive_threshold: int = Field(default=2, description="Consecutive identical tool calls threshold")
    cycle_max_length: int = Field(default=3, description="Maximum period length for repeating oscillation cycles")
    semantic_thought_threshold: float = Field(default=0.85, description="Token Jaccard similarity threshold for thought stagnation")


class ToolMisuseDetectorConfig(BaseModel):
    allow_unregistered_tools: bool = Field(default=False, description="Whether to permit tools not present in catalog")
    strict_type_checking: bool = Field(default=True, description="Enforce strict argument type validation")


class HallucinationDetectorConfig(BaseModel):
    min_claim_confidence: float = Field(default=0.85, description="Minimum confidence for ungrounded claim flagging")
    check_numerical_facts: bool = Field(default=True, description="Verify numerical and metric assertions")
    check_failed_observation_synthesis: bool = Field(default=True, description="Flag positive claims on empty/error observations")


class GoalDriftDetectorConfig(BaseModel):
    drift_threshold: float = Field(default=0.08, description="Minimum cosine topic relevance with goal")
    min_drifting_steps: int = Field(default=2, description="Consecutive low-relevance steps before flagging drift")


class SecurityPolicyConfig(BaseModel):
    blocked_commands: List[str] = Field(
        default_factory=lambda: [
            r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f*|-rf|-fr)\s+([/~*]|\.\.)",
            r"\b(mkfs|dd\s+if=/dev/zero|fdisk)\b",
            r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
            r"\b(sudo\s+su|chmod\s+777\s+/|chown\s+root\b)",
            r"\b(curl|wget)\b.*\|\s*(bash|sh|python)\b",
            r"/dev/tcp/\d+\.\d+\.\d+\.\d+|\bnc\s+-e\s+/bin/sh\b",
            r"\b(DROP\s+DATABASE|DROP\s+TABLE|TRUNCATE\s+TABLE)\b",
        ]
    )
    restricted_file_patterns: List[str] = Field(
        default_factory=lambda: [
            r"(/etc/shadow|/etc/sudoers|id_rsa|\.aws/credentials|\.env\b|kube/config)",
        ]
    )


class MonitorConfig(BaseModel):
    looping: LoopingDetectorConfig = Field(default_factory=LoopingDetectorConfig)
    tool_misuse: ToolMisuseDetectorConfig = Field(default_factory=ToolMisuseDetectorConfig)
    hallucination: HallucinationDetectorConfig = Field(default_factory=HallucinationDetectorConfig)
    goal_drift: GoalDriftDetectorConfig = Field(default_factory=GoalDriftDetectorConfig)
    security: SecurityPolicyConfig = Field(default_factory=SecurityPolicyConfig)


DEFAULT_MONITOR_CONFIG = MonitorConfig()
