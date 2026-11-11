"""Armada MCP Server.

Exposes Armada node management as MCP tools for AI agents.
Runs as a stdio-based MCP server that translates tool calls into
Armada REST API requests on localhost.

Usage:
    python -m armada_ai.mcp_server
    armada mcp
"""
import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP

ARMADA_API = os.environ.get("ARMADA_API", "http://127.0.0.1:9100")
NODE_NAME = os.environ.get("ARMADA_NODE_NAME", "")
TOKEN_FILE = os.path.expanduser("~/.armada/token")

_self_cache: dict[str, Any] = {}


def _read_token() -> str:
    try:
        return open(TOKEN_FILE).read().strip()
    except FileNotFoundError:
        return ""


def _api(method: str, path: str, body: dict | None = None) -> Any:
    url = f"{ARMADA_API}{path}"
    headers = {"Content-Type": "application/json"}
    token = _read_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}", "detail": error_body}
    except (urllib.error.URLError, OSError) as e:
        return {"error": "connection_failed", "detail": str(e)}


def _get_self() -> dict[str, Any]:
    if _self_cache:
        return _self_cache
    if not NODE_NAME:
        return {}
    nodes = _api("GET", "/api/nodes")
    if isinstance(nodes, dict) and "error" in nodes:
        return {}
    for n in nodes:
        if n.get("name") == NODE_NAME:
            detail = _api("GET", f"/api/nodes/{n['id']}")
            if isinstance(detail, dict) and "node" in detail:
                _self_cache.update(detail["node"])
            return _self_cache
    return {}


mcp = FastMCP(
    "armada",
    instructions=(
        "Armada node management tools. Use these to spawn child nodes, "
        "send tasks, monitor status, and manage the agent tree. "
        "spawn_node automatically inherits the parent's agent_type and project."
    ),
)


@mcp.tool()
def get_my_info() -> str:
    """Get this node's own info: ID, name, agent_type, project, parent_id, status."""
    info = _get_self()
    if not info:
        return json.dumps({"error": "Not running as an Armada node (ARMADA_NODE_NAME not set)"})
    return json.dumps({
        "id": info.get("id"),
        "name": info.get("name"),
        "agent_type": info.get("agent_type"),
        "project_label_id": info.get("project_label_id"),
        "project_label_name": info.get("project_label_name"),
        "parent_id": info.get("parent_id"),
        "status": info.get("status"),
    })


@mcp.tool()
def spawn_node(
    name: str,
    project_label_id: str | None = None,
    agent_type: str | None = None,
    initial_prompt: str | None = None,
) -> str:
    """Spawn a child node under this node.

    Inherits agent_type and project_label_id from the parent by default.
    Only override agent_type if explicitly requested by the user.

    Args:
        name: Descriptive name for the child node (e.g. "test-writer", "reviewer").
        project_label_id: Project to assign. Defaults to parent's project.
        agent_type: Agent type ("opencode", "claude", "bash"). Defaults to parent's type.
        initial_prompt: Optional prompt to send to the agent after creation.

    Returns:
        JSON with the created node's id, name, and details.
    """
    me = _get_self()
    if not agent_type:
        agent_type = me.get("agent_type", "opencode")
    if not project_label_id:
        project_label_id = me.get("project_label_id", "")

    body: dict[str, Any] = {
        "name": name,
        "project_label_id": project_label_id,
        "agent_type": agent_type,
    }
    parent_id = me.get("id")
    if parent_id is not None:
        body["parent_id"] = parent_id
    if initial_prompt:
        body["initial_prompt"] = initial_prompt

    return json.dumps(_api("POST", "/api/nodes", body))


@mcp.tool()
async def send_task(node_id: int, command: str, delay: int = 2) -> str:
    """Send a command to a node's terminal.

    Waits `delay` seconds before sending to allow tmux to initialize.

    Args:
        node_id: Target node ID.
        command: The command or text to send.
        delay: Seconds to wait before sending (default 2). Set to 0 to skip.

    Returns:
        JSON confirmation.
    """
    if delay > 0:
        await asyncio.sleep(delay)
    return json.dumps(_api("POST", f"/api/nodes/{node_id}/send", {"command": command}))


@mcp.tool()
def kill_node(node_id: int) -> str:
    """Kill a node and all its descendants (cascade delete).

    Args:
        node_id: The node ID to kill.

    Returns:
        JSON confirmation.
    """
    return json.dumps(_api("DELETE", f"/api/nodes/{node_id}"))


@mcp.tool()
def get_tree() -> str:
    """Get the full hierarchical node tree with status and latest message per node."""
    return json.dumps(_api("GET", "/api/tree"))


@mcp.tool()
def get_node(node_id: int) -> str:
    """Get detailed info for a node: status, reports history, and children.

    Args:
        node_id: The node ID to inspect.

    Returns:
        JSON with node details, reports array, and children array.
    """
    return json.dumps(_api("GET", f"/api/nodes/{node_id}"))


@mcp.tool()
def list_nodes(include_dead: bool = False) -> str:
    """List all live nodes. Set include_dead=True to include killed nodes.

    Args:
        include_dead: Whether to include dead/killed nodes.

    Returns:
        JSON array of node summaries.
    """
    path = "/api/nodes?include_dead=true" if include_dead else "/api/nodes"
    return json.dumps(_api("GET", path))


@mcp.tool()
def report_status(status: str, message: str) -> str:
    """Report this node's status to Armada.

    Args:
        status: One of "active", "idle", "pending", "error".
        message: Short description (under 10 words). Be specific, not generic.

    Returns:
        JSON confirmation.
    """
    node_name = NODE_NAME
    if not node_name:
        return json.dumps({"error": "Not running as an Armada node (ARMADA_NODE_NAME not set)"})
    if status not in ("active", "idle", "pending", "error"):
        return json.dumps({"error": f"Invalid status '{status}'. Must be active, idle, pending, or error."})
    return json.dumps(_api("POST", "/api/report", {
        "name": node_name,
        "status": status,
        "message": message,
    }))


@mcp.tool()
def list_projects() -> str:
    """List all project labels."""
    return json.dumps(_api("GET", "/api/project-labels"))


@mcp.tool()
def send_message(to_node_id: int, payload: str, msg_type: str = "message") -> str:
    """Send a message to another node's inbox.

    Args:
        to_node_id: Target node ID.
        payload: Message content (JSON string or plain text).
        msg_type: Message type (e.g. "task", "result", "message"). Default "message".

    Returns:
        JSON with the created message details.
    """
    me = _get_self()
    body: dict[str, Any] = {"payload": payload, "type": msg_type}
    if me.get("id"):
        body["from_node_id"] = me["id"]
    return json.dumps(_api("POST", f"/api/nodes/{to_node_id}/messages", body))


@mcp.tool()
def read_inbox(status: str = "pending") -> str:
    """Read messages in this node's inbox.

    Args:
        status: Filter by status: "pending", "delivered", "done", or "all". Default "pending".

    Returns:
        JSON array of messages.
    """
    me = _get_self()
    node_id = me.get("id")
    if not node_id:
        return json.dumps({"error": "Not running as an Armada node"})
    return json.dumps(_api("GET", f"/api/nodes/{node_id}/messages?status={status}&limit=50"))


@mcp.tool()
def ack_message(message_id: int) -> str:
    """Acknowledge a message (mark as done).

    Args:
        message_id: The message ID to acknowledge.

    Returns:
        JSON confirmation.
    """
    return json.dumps(_api("PATCH", f"/api/messages/{message_id}", {"status": "done"}))


@mcp.tool()
def broadcast(payload: str, msg_type: str = "message") -> str:
    """Send a message to all children of this node.

    Args:
        payload: Message content (JSON string or plain text).
        msg_type: Message type. Default "message".

    Returns:
        JSON with count of messages created.
    """
    me = _get_self()
    node_id = me.get("id")
    if not node_id:
        return json.dumps({"error": "Not running as an Armada node"})
    return json.dumps(_api("POST", f"/api/nodes/{node_id}/broadcast", {"payload": payload, "type": msg_type}))


@mcp.tool()
def post_to_queue(payload: str, msg_type: str = "task") -> str:
    """Post a task to the shared work queue for any idle agent to claim.

    Args:
        payload: Task description (JSON string or plain text).
        msg_type: Message type. Default "task".

    Returns:
        JSON with the created task details.
    """
    me = _get_self()
    body: dict[str, Any] = {"payload": payload, "type": msg_type}
    if me.get("id"):
        body["from_node_id"] = me["id"]
    return json.dumps(_api("POST", "/api/queue", body))


@mcp.tool()
def claim_from_queue() -> str:
    """Claim the next available task from the shared work queue.

    Returns:
        JSON with the claimed task details, or empty list if no tasks available.
    """
    me = _get_self()
    node_id = me.get("id")
    if not node_id:
        return json.dumps({"error": "Not running as an Armada node"})
    tasks = _api("GET", "/api/queue?status=pending&limit=1")
    if isinstance(tasks, list) and tasks:
        task_id = tasks[0].get("id")
        if task_id:
            return json.dumps(_api("POST", f"/api/queue/{task_id}/claim", {"node_id": node_id}))
    return json.dumps({"message": "No tasks available"})


def main():
    mcp.run()


if __name__ == "__main__":
    main()
