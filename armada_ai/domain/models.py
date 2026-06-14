from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    PENDING = "pending"
    ERROR = "error"
    DEAD = "dead"

    @classmethod
    def valid_transitions(cls) -> set[str]:
        return {"idle", "active", "pending", "error"}


class AgentType(str, Enum):
    AUTO = "auto"
    BASH = "bash"
    OPENCODE = "opencode"
    CLAUDE = "claude"


@dataclass(frozen=True)
class ProjectLabel:
    id: str
    name: str
    path: str

    def __getitem__(self, key: str) -> str:
        return getattr(self, key)

    def get(self, key: str, default=None) -> str | None:
        return getattr(self, key, default)


@dataclass(frozen=True)
class StatusReport:
    id: int
    node_id: int
    status: str
    message: str | None
    timestamp: str


@dataclass
class Node:
    id: int
    name: str
    colour: str
    status: str = AgentStatus.IDLE.value
    agent_type: str = AgentType.AUTO.value
    parent_id: int | None = None
    project_label_id: str | None = None
    project_label_name: str | None = None
    project_path: str | None = None
    tmux_pane_id: str | None = None
    tmux_session_id: str | None = None
    created_at: str | None = None
    killed_at: str | None = None
    hidden_at: str | None = None
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost: float = 0.0
    log_count: int = 0
    children: list[Node] = field(default_factory=list)
    latest_message: str | None = None
    latest_report_time: str | None = None
    latest_options: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Node:
        return cls(
            id=row["id"],
            name=row["name"],
            colour=row.get("colour", "#8b949e"),
            status=row.get("status", AgentStatus.IDLE.value),
            agent_type=row.get("agent_type", AgentType.AUTO.value),
            parent_id=row.get("parent_id"),
            project_label_id=row.get("project_label_id"),
            project_label_name=row.get("project_label_name"),
            project_path=row.get("project_path"),
            tmux_pane_id=row.get("tmux_pane_id"),
            tmux_session_id=row.get("tmux_session_id"),
            created_at=row.get("created_at"),
            killed_at=row.get("killed_at"),
            hidden_at=row.get("hidden_at"),
            total_tokens_in=row.get("total_tokens_in", 0),
            total_tokens_out=row.get("total_tokens_out", 0),
            total_cost=row.get("total_cost", 0.0),
            log_count=row.get("log_count", 0),
            latest_message=row.get("latest_message"),
            latest_report_time=row.get("latest_report_time"),
            latest_options=row.get("latest_options"),
        )

    def is_dead(self) -> bool:
        return self.status == AgentStatus.DEAD.value

    def is_alive(self) -> bool:
        return self.status != AgentStatus.DEAD.value and self.killed_at is None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def as_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "colour": self.colour,
            "status": self.status,
            "agent_type": self.agent_type,
            "parent_id": self.parent_id,
            "project_label_id": self.project_label_id,
            "project_label_name": self.project_label_name,
            "created_at": self.created_at,
            "killed_at": self.killed_at,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_cost": self.total_cost,
            "log_count": self.log_count,
            "latest_message": self.latest_message,
            "latest_report_time": self.latest_report_time,
            "latest_options": self.latest_options,
            "tmux_session_id": self.tmux_session_id,
        }


@dataclass(frozen=True)
class CreateNodeRequest:
    name: str | None
    project_label_id: str
    agent_type: str = AgentType.AUTO.value
    parent_id: int | None = None
    initial_prompt: str | None = None

    def validate_name(self, existing_names: set[str]) -> CreateNodeRequest | str:
        if self.name and len(self.name) > 100:
            return "Node name must be 100 characters or fewer"
        if self.name and self.name in existing_names:
            return f"Node '{self.name}' already exists"
        return self


@dataclass(frozen=True)
class AgentReportRequest:
    name: str
    status: str = AgentStatus.IDLE.value
    message: str | None = None
    tokens: dict[str, int] | None = None
    cost: float | None = None
    client_ts: float = 0.0

    def validate(self) -> str | None:
        if not self.name:
            return "name is required"
        if self.status not in AgentStatus.valid_transitions():
            return f"Invalid status: {self.status}"
        return None


@dataclass(frozen=True)
class PatchNodeRequest:
    action: str
    parent_id: int | None = None
    name: str | None = None
