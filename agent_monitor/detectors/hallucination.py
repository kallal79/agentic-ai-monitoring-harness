"""
agent_monitor.detectors.hallucination

Detector for hallucinated claims in agent reasoning and final responses:
- Assertions of specific facts/metrics/entities unsupported by any tool observation
- Claims synthesized following tool failures or empty observation results
- Direct factual contradictions between agent synthesis and observation data
"""

import json
import re
from typing import Any, Dict, List, Set, Tuple
from agent_monitor.detectors.base import BaseDetector
from agent_monitor.models import AgentTrace, DetectedIssue, FailureCategory, Severity

# Regex patterns for extracting specific verifiable factual assertions
NUMERICAL_FACT_PATTERN = re.compile(
    r"""
    (?:\$|€|£)?\b\d+(?:[\.,]\d+)?\b(?:\s*(?:%|ms|s|gb|mb|kb|tb|m|k|billion|million|users|records|errors|queries|requests|fps|ghz))?
    """,
    re.VERBOSE | re.IGNORECASE,
)

ENTITY_CODE_PATTERN = re.compile(
    r"\b(?:[A-Z][a-zA-Z0-9_-]{3,}|(?:user|cust|err|order|tx|item|server)-[a-zA-Z0-9_-]+)\b"
)

ERROR_KEYWORDS = ["error", "exception", "failed", "failure", "not found", "timeout", "refused", "empty"]


def _extract_text_from_obs(obs: Any) -> str:
    """Normalize any observation structure into a searchable text string."""
    if obs is None:
        return ""
    if isinstance(obs, (str, int, float, bool)):
        return str(obs).strip()
    try:
        return json.dumps(obs, default=str)
    except Exception:
        return str(obs)


def _is_obs_error_or_empty(obs: Any) -> Tuple[bool, str]:
    """Check if observation represents an explicit error or zero-result state."""
    text = _extract_text_from_obs(obs).strip()
    if not text or text in ["{}", "[]", "null", "none"]:
        return True, "empty result"
    lower = text.lower()
    for kw in ERROR_KEYWORDS:
        if kw in lower:
            return True, f"contains '{kw}'"
    return False, ""


class HallucinationDetector(BaseDetector):
    """Detects unsupported factual claims, fabricated metrics, and contradictory conclusions."""

    def __init__(self, min_claim_confidence: float = 0.85):
        super().__init__(name="HallucinationDetector", category=FailureCategory.HALLUCINATION)
        self.min_claim_confidence = min_claim_confidence

    def detect(self, trace: AgentTrace) -> List[DetectedIssue]:
        issues: List[DetectedIssue] = []

        # 1. Build observation corpus and trace history
        observation_texts: List[str] = []
        has_failed_tools = False
        all_obs_empty_or_failed = True

        for step in trace.steps:
            obs_text = _extract_text_from_obs(step.observation)
            if obs_text:
                observation_texts.append(obs_text)
                is_err, _ = _is_obs_error_or_empty(step.observation)
                if is_err:
                    has_failed_tools = True
                else:
                    all_obs_empty_or_failed = False
            else:
                has_failed_tools = True

        full_corpus = " ".join(observation_texts).lower()
        goal_text = (trace.goal or "").lower()
        allowed_context = full_corpus + " " + goal_text

        # 2. Check for Hallucinated Final Response when tool calls failed or returned nothing
        final_resp = (trace.final_response or "").strip()
        if final_resp and trace.steps:
            if all_obs_empty_or_failed and len(final_resp.split()) > 15:
                # Agent answered with confident factual paragraphs despite getting zero successful observations
                # Check if response asserts positive findings
                positive_claim_words = ["found", "shows that", "confirmed", "the revenue is", "total of", "success", "active", "the result is"]
                has_positive_assert = any(w in final_resp.lower() for w in positive_claim_words)
                if has_positive_assert:
                    issues.append(
                        DetectedIssue(
                            category=self.category,
                            severity=Severity.HIGH,
                            step_index=None,
                            title="Fabricated Final Synthesis on Failed/Empty Observations",
                            description=(
                                "The agent asserted conclusive factual results in its final response, "
                                "even though every tool observation in the trace was empty or an error."
                            ),
                            confidence=0.95,
                            evidence={
                                "final_response_snippet": final_resp[:180] + ("..." if len(final_resp) > 180 else ""),
                                "observation_count": len(observation_texts),
                                "observation_status": "All observations failed or were empty",
                            },
                            recommendation="Ensure the agent gracefully informs the user when tool retrieval fails instead of improvising.",
                        )
                    )

            # 3. Check for specific ungrounded numerical figures and entities in final response
            final_numbers = set(NUMERICAL_FACT_PATTERN.findall(final_resp))
            ungrounded_numbers: List[str] = []

            # Filter trivial numbers (e.g. single digit step references like 1, 2)
            for num in final_numbers:
                num_clean = num.strip().lower()
                if num_clean in ["1", "2", "3", "0", "first", "second"]:
                    continue
                # If number does not appear in observation corpus or goal
                if num_clean not in allowed_context:
                    # Also check digits only (e.g. '$4.2m' -> '4.2')
                    digits_match = re.search(r"\d+(?:\.\d+)?", num_clean)
                    if digits_match and digits_match.group(0) not in allowed_context:
                        ungrounded_numbers.append(num.strip())

            if len(ungrounded_numbers) >= 2:
                issues.append(
                    DetectedIssue(
                        category=self.category,
                        severity=Severity.HIGH,
                        step_index=None,
                        title=f"Ungrounded Quantitative Claims ({len(ungrounded_numbers)} facts)",
                        description=(
                            f"Agent final response cited {len(ungrounded_numbers)} quantitative values "
                            f"({', '.join(ungrounded_numbers[:5])}) that do not exist in any tool observation or the original goal."
                        ),
                        confidence=0.92,
                        evidence={
                            "ungrounded_values": ungrounded_numbers[:8],
                            "response_excerpt": final_resp[:150],
                        },
                        recommendation="Ground all numerical and metric assertions in explicit tool observation outputs.",
                    )
                )

        # 4. Step-level Hallucination Check in Thoughts
        for step in trace.steps:
            if not step.thought:
                continue

            # If previous step had an error or empty result, did this thought hallucinate success?
            if step.step_index > 1:
                prev_step = trace.steps[step.step_index - 2]
                prev_obs = _extract_text_from_obs(prev_step.observation)
                prev_is_err, err_reason = _is_obs_error_or_empty(prev_step.observation)

                thought_lower = step.thought.lower()
                if prev_is_err and ("now that i have the data" in thought_lower or "the data shows that" in thought_lower or "based on the above successful" in thought_lower):
                    issues.append(
                        DetectedIssue(
                            category=self.category,
                            severity=Severity.HIGH,
                            step_index=step.step_index,
                            title="Hallucinated Fact in Reasoning Step",
                            description=(
                                f"Agent thought at step {step.step_index} assumed successful data retrieval, "
                                f"contradicting previous step observation ({err_reason})."
                            ),
                            confidence=0.88,
                            evidence={
                                "step": step.step_index,
                                "thought": step.thought[:140],
                                "previous_observation": prev_obs[:140],
                            },
                            recommendation="Condition intermediate reasoning on explicit verification of tool return status.",
                        )
                    )

        return issues
