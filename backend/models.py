"""Data types shared by the Campus Customs agent team."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Role(str, Enum):
    BOSS = "boss"
    INVENTORY = "inventory"
    ACCOUNTING = "accounting"
    FACILITIES = "facilities"
    CUSTOMER_SERVICE = "customer_service"
    IT_DIRECTOR = "it_director"


# ---------------------------------------------------------------- agent outputs

class AgentReport(BaseModel):
    """What a specialist agent hands back to whoever delegated to it."""

    role: Role
    ticket_ids: list[int] = Field(description="Tickets this report is about.")
    findings: list[str] = Field(description="Facts from MCP tool results, with the numbers. Never guesses.")
    actions_taken: list[str] = Field(default_factory=list, description="Tool calls that changed something (ticket updates, drafts, payments).")
    drafts_saved: list[str] = Field(default_factory=list, description="Paths of draft messages saved (never sent).")
    blocked_on: list[str] = Field(default_factory=list, description="What is still blocking, e.g. a human approval that was denied or an open invoice.")
    recommendation: str = Field(description="One or two sentences: what should happen next and why.")


class TicketDispatch(BaseModel):
    """How one ticket moved through the tiered workflow in a run."""

    ticket_id: int
    known_issue: str | None
    tier: int = Field(description="1 = staff direct, 2 = IT Director, 3 = Boss")
    first_owner: str
    route: list[str] = Field(description="The only staff allowed on this ticket, unless a director adds one.")
    escalation_reasons: list[str] = Field(default_factory=list)
    final_status: str | None = None
    report: AgentReport | None = None


class DeskRunSummary(BaseModel):
    """What the dispatcher returns for a run over the open tickets."""

    session_id: str
    shop_date: str
    tickets: list[TicketDispatch]
    cash_after_run: float | None = None
    token_cost_usd: float = 0.0


# ---------------------------------------------------------------- audit trail

class ToolCallRecord(BaseModel):
    tool_call_id: str | None = None
    tool_name: str
    args: Any = None


class ToolResultRecord(BaseModel):
    tool_call_id: str | None = None
    tool_name: str
    content: Any = None
    is_retry: bool = False


class UsageRecord(BaseModel):
    run_requests: int = 0
    run_input_tokens: int = 0
    run_output_tokens: int = 0
    session_cost_usd: float = 0.0
    budget_usd: float = 0.0
    ratcheted: bool = False


class AuditEntry(BaseModel):
    """One line of output/audit_trail.json: a single agent-loop step or event."""

    timestamp: str
    session_id: str
    run_id: str
    parent_run_id: str | None = None
    ticket_id: int | None = None
    agent: str = Field(description="Agent role, or 'dispatcher' for routing events.")
    delegated_by: Role | None = None
    depth: int = 0
    step: int = 0
    event: str = Field(description="dispatch | run_start | model_request | model_response | end_node | run_end | delegation | approval_decision | error")
    model: str | None = None
    prompt: str | None = None
    text: str | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    tool_results: list[ToolResultRecord] = Field(default_factory=list)
    output: Any = None
    detail: dict[str, Any] = Field(default_factory=dict)
    usage: UsageRecord = Field(default_factory=UsageRecord)


# ---------------------------------------------------------------- approvals

class ApprovalDecision(BaseModel):
    """A human's decision on one payment tool call. The signed token is never stored here."""

    tool_name: str
    kind: str
    ref_id: int
    amount: float | None = None
    payee: str | None = None
    approved: bool
    approved_by: str | None = None
    factor: str | None = Field(default=None, description="'1fa' or '2fa'")
    reason: str


# ---------------------------------------------------------------- API (backend/main.py)

class TicketOut(BaseModel):
    id: int
    type: str
    requester: str
    subject: str
    status: str = Field(description="Raw tickets.status, e.g. open, waiting_on_approval, resolved.")
    state: str = Field(description="'resolved' if status is resolved, otherwise 'open'.")
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    lease_id: int | None = None
    invoice_id: int | None = None
    notes: str | None = None
    created_at: str


class TicketsResponse(BaseModel):
    tickets: list[TicketOut]
    count: int
    open: int
    resolved: int
