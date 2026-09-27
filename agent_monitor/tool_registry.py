"""
agent_monitor.tool_registry

Catalog of registered tool schemas, argument definitions, parameter types,
and validation utilities for observing agent tool calls.
"""

from typing import Any, Dict, List, Optional


class ParameterSpec:
    def __init__(
        self,
        name: str,
        expected_type: type,
        required: bool = True,
        description: str = "",
        min_length: Optional[int] = None,
        allowed_values: Optional[List[Any]] = None,
    ):
        self.name = name
        self.expected_type = expected_type
        self.required = required
        self.description = description
        self.min_length = min_length
        self.allowed_values = allowed_values


class ToolSpec:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: List[ParameterSpec],
        is_sensitive: bool = False,
    ):
        self.name = name
        self.description = description
        self.parameters = {p.name: p for p in parameters}
        self.is_sensitive = is_sensitive


DEFAULT_TOOL_REGISTRY: Dict[str, ToolSpec] = {
    "web_search": ToolSpec(
        name="web_search",
        description="Search the web for up-to-date information.",
        parameters=[
            ParameterSpec("query", str, required=True, min_length=2, description="Search query string"),
            ParameterSpec("max_results", int, required=False, description="Max number of items to return"),
        ],
    ),
    "fetch_url": ToolSpec(
        name="fetch_url",
        description="Fetch HTML or JSON content from a public URL.",
        parameters=[
            ParameterSpec("url", str, required=True, min_length=8, description="Target URL"),
        ],
    ),
    "execute_bash": ToolSpec(
        name="execute_bash",
        description="Execute a bash/shell command in the workspace container.",
        parameters=[
            ParameterSpec("command", str, required=True, min_length=1, description="Shell command string"),
            ParameterSpec("timeout", int, required=False, description="Execution timeout in seconds"),
        ],
        is_sensitive=True,
    ),
    "read_file": ToolSpec(
        name="read_file",
        description="Read the contents of a local file.",
        parameters=[
            ParameterSpec("path", str, required=True, min_length=1, description="File path to read"),
        ],
    ),
    "write_file": ToolSpec(
        name="write_file",
        description="Write or overwrite contents into a local file.",
        parameters=[
            ParameterSpec("path", str, required=True, min_length=1, description="File path to write"),
            ParameterSpec("content", str, required=True, description="Content string"),
        ],
        is_sensitive=True,
    ),
    "sql_query": ToolSpec(
        name="sql_query",
        description="Execute a SQL statement against an internal database.",
        parameters=[
            ParameterSpec("query", str, required=True, min_length=5, description="SQL query statement"),
            ParameterSpec("database", str, required=True, min_length=1, description="Target database identifier"),
        ],
        is_sensitive=True,
    ),
    "send_email": ToolSpec(
        name="send_email",
        description="Send an email to a verified recipient.",
        parameters=[
            ParameterSpec("recipient", str, required=True, min_length=3, description="Recipient email address"),
            ParameterSpec("subject", str, required=True, min_length=1, description="Subject line"),
            ParameterSpec("body", str, required=True, min_length=1, description="Email body content"),
        ],
        is_sensitive=True,
    ),
    "calculate": ToolSpec(
        name="calculate",
        description="Evaluate a mathematical expression safely.",
        parameters=[
            ParameterSpec("expression", str, required=True, min_length=1, description="Mathematical expression"),
        ],
    ),
    "customer_crm_lookup": ToolSpec(
        name="customer_crm_lookup",
        description="Retrieve customer profile and ticket history by customer_id.",
        parameters=[
            ParameterSpec("customer_id", str, required=True, min_length=3, description="Unique customer ID"),
        ],
    ),
    "server_metrics": ToolSpec(
        name="server_metrics",
        description="Query server infrastructure metrics like CPU, RAM, or latency.",
        parameters=[
            ParameterSpec("metric_name", str, required=True, min_length=2, description="Target metric name"),
            ParameterSpec("timeframe", str, required=False, description="e.g. 1h, 24h, 7d"),
        ],
    ),
}
