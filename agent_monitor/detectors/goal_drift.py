"""
agent_monitor.detectors.goal_drift

Detector for goal drift and semantic trajectory diversion in agent traces:
- Actions and thoughts diverging from the initial stated goal
- Persistent tangents into unrelated semantic domains
- Loss of task alignment across multi-step execution
"""

import math
import re
from typing import Dict, List, Set
from agent_monitor.detectors.base import BaseDetector
from agent_monitor.models import AgentTrace, DetectedIssue, FailureCategory, Severity

# Common stopwords to exclude from semantic vector matching
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "could", "did", "do", "does", "doing", "down",
    "during", "each", "few", "for", "from", "further", "had", "has", "have",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me",
    "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on",
    "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out",
    "over", "own", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while",
    "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself",
    "yourselves", "will", "can", "need", "want", "please", "help", "tool", "call",
    "step", "check", "run", "let", "first", "next", "also", "using"
}


def _extract_keywords(text: str) -> Set[str]:
    """Extract informative lowercase keywords, excluding common stopwords."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    return {w for w in words if w not in STOPWORDS}


def _calculate_cosine_similarity(set1: Set[str], set2: Set[str]) -> float:
    """Calculate overlap similarity between two keyword sets."""
    if not set1 or not set2:
        return 0.0
    common = len(set1 & set2)
    return common / math.sqrt(len(set1) * len(set2))


class GoalDriftDetector(BaseDetector):
    """Detects when an agent loses alignment with the original user objective."""

    def __init__(self, drift_threshold: float = 0.08, min_drifting_steps: int = 2):
        super().__init__(name="GoalDriftDetector", category=FailureCategory.GOAL_DRIFT)
        self.drift_threshold = drift_threshold
        self.min_drifting_steps = min_drifting_steps

    def detect(self, trace: AgentTrace) -> List[DetectedIssue]:
        issues: List[DetectedIssue] = []
        goal = trace.goal
        if not goal or len(trace.steps) < 2:
            return issues

        goal_keywords = _extract_keywords(goal)
        if not goal_keywords:
            return issues

        # Track per-step semantic relevance to the original goal
        step_scores: List[float] = []
        step_keywords_list: List[Set[str]] = []

        for step in trace.steps:
            # Combine thought, action, and tool parameters
            step_text = f"{step.thought} {step.action}"
            if step.tool_call:
                step_text += f" {step.tool_call.tool_name} {str(step.tool_call.parameters)}"

            step_keywords = _extract_keywords(step_text)
            step_keywords_list.append(step_keywords)

            # Measure overlap with goal keywords
            sim = _calculate_cosine_similarity(goal_keywords, step_keywords)
            step_scores.append(sim)

        # Detect sustained zero/low relevance streak
        drifting_streak_start: Optional[int] = None
        drifting_steps: List[int] = []

        for idx, (score, step) in enumerate(zip(step_scores, trace.steps)):
            # Check if this step is disconnected from goal
            # (allowing step 1 some setup slack, but later steps should maintain relevance or logical progression)
            is_disconnected = score < self.drift_threshold

            if is_disconnected:
                # Also check if it shares context with the previous step (if previous step was already drifting)
                if drifting_streak_start is None:
                    drifting_streak_start = step.step_index
                drifting_steps.append(step.step_index)
            else:
                if len(drifting_steps) >= self.min_drifting_steps:
                    # Drift happened in an earlier segment
                    break
                # Reset if relevance restored quickly
                drifting_streak_start = None
                drifting_steps = []

        if len(drifting_steps) >= self.min_drifting_steps:
            start_step = drifting_steps[0]
            # Gather foreign keywords introduced during drifting steps
            drift_keywords: Set[str] = set()
            for s_idx in drifting_steps:
                drift_keywords |= step_keywords_list[s_idx - 1]
            unrelated_topics = list(drift_keywords - goal_keywords)[:6]

            issues.append(
                DetectedIssue(
                    category=self.category,
                    severity=Severity.HIGH if len(drifting_steps) >= 3 else Severity.MEDIUM,
                    step_index=start_step,
                    title="Goal Drift Detected",
                    description=(
                        f"Agent trajectory diverged from original goal '{goal[:60]}...' starting at "
                        f"step {start_step}. Continued drifting for {len(drifting_steps)} consecutive steps "
                        f"focusing on unrelated topics: {', '.join(unrelated_topics)}."
                    ),
                    confidence=min(0.75 + (0.08 * len(drifting_steps)), 0.95),
                    evidence={
                        "goal": goal,
                        "goal_keywords": list(goal_keywords),
                        "drifting_step_indices": drifting_steps,
                        "unrelated_topics": unrelated_topics,
                        "relevance_scores": [round(s, 3) for s in step_scores],
                    },
                    recommendation="Inject periodic goal-anchoring prompts into the agent loop to maintain task focus.",
                )
            )

        return issues
