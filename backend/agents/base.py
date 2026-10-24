"""Shared agent loop for the Campus Customs team.

Every role is a PydanticAI Agent that:
  * runs on gpt-6-luna through Portkey (llm.portkey_settings)
  * reaches shop data only through the campus-customs MCP server, limited to its role's tools
  * can `delegate` to any other role (full connectivity), up to MAX_DEPTH levels deep
  * logs every agent-loop step to output/audit_trail.json
  * pauses for a human on payment tools (see backend/approvals.py)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from pydantic_ai import Agent, DeferredToolRequests, RunContext, UsageLimits
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from llm import PORTKEY_BASE_URL, portkey_settings

from ..approvals import PAY_TOOLS, HumanApprover
from ..audit import AuditTrail, describe_request, describe_response, now
from ..budget import BudgetGuard, UsageTracker
from ..models import AgentReport, AuditEntry, Role, UsageRecord

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
MAX_DEPTH = 3            # boss -> specialist -> specialist -> specialist
MAX_REQUESTS_PER_RUN = 25
MAX_APPROVAL_ROUNDS = 3
DIRECTORS = frozenset({Role.IT_DIRECTOR, Role.BOSS})


@dataclass
class RoleSpec:
    role: Role
    prompt_file: str
    mcp_tools: frozenset[str]
    output_type: type = AgentReport


@dataclass
class Services:
    session_id: str
    mcp: MCPToolset
    audit: AuditTrail
    budget: BudgetGuard
    approver: HumanApprover
    team: "Team" = None  # type: ignore[assignment]


@dataclass
class TeamDeps:
    services: Services
    role: Role
    run_id: str
    depth: int = 0
    delegated_by: Role | None = None
    parent_run_id: str | None = None
    delegation_path: tuple[Role, ...] = field(default_factory=tuple)
    allowed_roles: frozenset[Role] | None = None  # this ticket's route (None = no limit)
    ticket_id: int | None = None


def _make_model(name: str) -> OpenAIChatModel:
    api_key, _ = portkey_settings()
    client = AsyncOpenAI(api_key=api_key, base_url=PORTKEY_BASE_URL)
    return OpenAIChatModel(name, provider=OpenAIProvider(openai_client=client))


async def delegate(ctx: RunContext[TeamDeps], to: Role, request: str) -> str:
    """Hand a focused task to another Campus Customs agent and get its report back.

    to: one of boss, it_director, inventory, accounting, facilities, customer_service (not yourself).
    request: what you need, including ticket id and any sku/size/qty/invoice_id/lease_id.
    """
    d = ctx.deps
    if to == d.role:
        return "Delegation refused: you can't delegate to yourself."
    if d.depth >= MAX_DEPTH:
        return f"Delegation refused: depth limit {MAX_DEPTH} reached. Finish with the facts you have."
    if (d.allowed_roles is not None and to not in d.allowed_roles and to not in DIRECTORS
            and d.role not in DIRECTORS):
        allowed = ", ".join(sorted(r.value for r in d.allowed_roles))
        return (f"Delegation refused: {to.value} is not on this ticket's route ({allowed}). "
                "If you really need them, escalate to it_director.")
    if to in d.delegation_path:
        return f"Delegation refused: {to.value} is already working on this chain ({' -> '.join(r.value for r in d.delegation_path)})."
    team = d.services.team
    await team.log(d, event="delegation", detail={"to": to.value, "request": request})
    # The route follows the ticket. Directors aren't limited by it, and a director
    # delegating to someone outside the route adds them to it (logged as a delegation).
    allowed = d.allowed_roles if (d.allowed_roles is None or to in DIRECTORS) else d.allowed_roles | {to}
    output = await team.run_agent(to, request, depth=d.depth + 1, delegated_by=d.role,
                                  parent_run_id=d.run_id, delegation_path=d.delegation_path + (d.role,),
                                  allowed_roles=allowed, ticket_id=d.ticket_id)
    return output.model_dump_json()


class Team:
    def __init__(self, services: Services, specs: list[RoleSpec]) -> None:
        self.services = services
        services.team = self
        self.specs = {s.role: s for s in specs}
        _, self.model_name = portkey_settings()
        self._models: dict[str, OpenAIChatModel] = {}
        self.agents = {s.role: self._build(s) for s in specs}

    def _model(self, name: str) -> OpenAIChatModel:
        if name not in self._models:
            self._models[name] = _make_model(name)
        return self._models[name]

    def _build(self, spec: RoleSpec) -> Agent:
        allowed = spec.mcp_tools
        toolset = self.services.mcp.filtered(lambda ctx, td: td.name in allowed)
        if allowed & PAY_TOOLS.keys():
            toolset = toolset.approval_required(lambda ctx, td, args: td.name in PAY_TOOLS)
        return Agent(
            self._model(self.model_name),
            name=spec.role.value,
            instructions=(PROMPTS_DIR / spec.prompt_file).read_text(encoding="utf-8"),
            deps_type=TeamDeps,
            output_type=[spec.output_type, DeferredToolRequests],
            toolsets=[toolset],
            tools=[delegate],
            retries=2,
        )

    async def log_event(self, event: str, *, run_id: str = "dispatcher", agent: str = "dispatcher",
                        **fields: Any) -> None:
        """Audit entries that aren't an agent step (e.g. the dispatcher's routing decisions)."""
        b = self.services.budget
        await self.services.audit.append(AuditEntry(
            timestamp=now(), session_id=self.services.session_id, run_id=run_id, agent=agent,
            event=event, usage=UsageRecord(session_cost_usd=round(b.spent_usd, 6), budget_usd=b.budget_usd,
                                           ratcheted=b.ratcheted), **fields))

    async def log(self, deps: TeamDeps, *, event: str, step: int = 0, usage=None, **fields: Any) -> None:
        b = self.services.budget
        u = UsageRecord(session_cost_usd=round(b.spent_usd, 6), budget_usd=b.budget_usd, ratcheted=b.ratcheted)
        if usage is not None:
            u.run_requests, u.run_input_tokens, u.run_output_tokens = usage.requests, usage.input_tokens, usage.output_tokens
        await self.services.audit.append(AuditEntry(
            timestamp=now(), session_id=self.services.session_id, run_id=deps.run_id,
            parent_run_id=deps.parent_run_id, ticket_id=deps.ticket_id, agent=deps.role.value, delegated_by=deps.delegated_by,
            depth=deps.depth, step=step, event=event, usage=u, **fields))

    async def run_agent(self, role: Role, prompt: str, *, depth: int = 0, delegated_by: Role | None = None,
                        parent_run_id: str | None = None, delegation_path: tuple[Role, ...] = (),
                        allowed_roles: frozenset[Role] | None = None, ticket_id: int | None = None) -> Any:
        """The agent loop: iterate node by node, audit each step, pause for human approvals."""
        agent, budget = self.agents[role], self.services.budget
        deps = TeamDeps(self.services, role, uuid.uuid4().hex[:12], depth, delegated_by,
                        parent_run_id, delegation_path, allowed_roles, ticket_id)
        tracker = UsageTracker(budget)
        await self.log(deps, event="run_start", prompt=prompt, model=budget.current_model(),
                       detail={"allowed_roles": sorted(r.value for r in allowed_roles) if allowed_roles else None})

        history, deferred, step = None, None, 0
        for _round in range(MAX_APPROVAL_ROUNDS + 1):
            model_name = budget.current_model()
            async with agent.iter(
                prompt if history is None else None, deps=deps, message_history=history,
                deferred_tool_results=deferred, model=self._model(model_name),
                # Portkey's Azure gpt-6-luna only allows function tools on chat completions
                # with reasoning_effort='none' (this also keeps token use down).
                model_settings={"max_tokens": budget.max_tokens(), "openai_reasoning_effort": "none"},
                usage_limits=UsageLimits(request_limit=MAX_REQUESTS_PER_RUN),
            ) as run:
                async for node in run:
                    step += 1
                    tracker.update(run.usage)
                    if Agent.is_model_request_node(node):
                        budget.check()  # stop before spending past the $ cap
                        text, results = describe_request(node.request)
                        await self.log(deps, event="model_request", step=step, model=model_name,
                                       prompt=text, tool_results=results, usage=run.usage)
                    elif Agent.is_call_tools_node(node):
                        text, calls = describe_response(node.model_response)
                        await self.log(deps, event="model_response", step=step, model=model_name,
                                       text=text, tool_calls=calls, usage=run.usage)
                    elif Agent.is_end_node(node):
                        await self.log(deps, event="end_node", step=step, usage=run.usage)
                result = run.result
            tracker.update(result.usage)
            output = result.output

            if not isinstance(output, DeferredToolRequests):
                await self.log(deps, event="run_end", step=step, output=output.model_dump(mode="json"),
                               usage=result.usage)
                return output

            # Paused on payment tools: ask the human, then resume the same conversation.
            deferred, decisions = await self.services.approver.decide(output, requested_by=role.value, deps=deps)
            for dec in decisions:
                await self.log(deps, event="approval_decision", step=step, detail=dec.model_dump(mode="json"))
            history = result.all_messages()

        await self.log(deps, event="error", step=step, detail={"error": "too many approval rounds"})
        return AgentReport(role=role, ticket_ids=[], findings=[], blocked_on=["Stopped after too many approval rounds."],
                           recommendation="A human should review this ticket.")
