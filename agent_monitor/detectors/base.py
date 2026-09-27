"""
agent_monitor.detectors.base

Abstract base class for all failure mode detectors.
Provides standardized detection interface and utility helpers.
"""

from abc import ABC, abstractmethod
from typing import List
from agent_monitor.models import AgentTrace, DetectedIssue, FailureCategory


class BaseDetector(ABC):
    """Abstract base class for all failure mode detectors."""

    def __init__(self, name: str, category: FailureCategory):
        self.name = name
        self.category = category

    @abstractmethod
    def detect(self, trace: AgentTrace) -> List[DetectedIssue]:
        """Analyze an agent trace and return a list of detected issues."""
        pass
