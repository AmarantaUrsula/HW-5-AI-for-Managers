"""Desk dispatcher: the tiered workflow.

For each open ticket, the dispatcher calls the MCP tool triage_ticket, which
matches the ticket to a known issue using live database facts:
  Tier 1: a routine known issue goes straight to the first staff member on its
          route (no director)
  Tier 2: blocked or multi-team work goes to the IT Director, who assigns the
          minimum staff
  Tier 3: a cash conflict goes to the Boss
Only the staff on a ticket's route can be pulled in. Staff escalate to the IT
Director, and the IT Director escalates to the Boss.
"""

from __future__ import annotations

import json

from fastmcp import Client

from .agents import Team
from .models import AgentReport, DeskRunSummary, Role, TicketDispatch

TIER_ROLE = {2: Role.IT_DIRECTOR, 3: Role.BOSS}


def _brief(tri: dict) -> str:
    return json.dumps({k: tri[k] for k in ("ticket_id", "known_issue", "title", "tier", "route",
                                            "known_solution", "tools", "escalation_reasons", "facts")})


def _prompt(tri: dict) -> str:
    tid, route = tri["ticket_id"], tri["route"]
    if tri["tier"] == 1:
        nxt = route[1:]
        return (
            f"Tier 1, sent directly to you. Ticket {tid} is a routine known issue {tri['known_issue']} "
            f"({tri['title']}). Known solution: {tri['known_solution']} "
            f"Route (the only staff allowed on this ticket, in order): {' -> '.join(route)}. "
            + (f"Do your step, then delegate to {nxt[0]} for theirs. " if nxt else "You're the only one on the route. ")
            + "Whoever finishes the last step sets the ticket status with update_ticket. "
            "Escalate to it_director only if something the known solution doesn't cover comes up. "
            f"Triage: {_brief(tri)}"
        )
    who = "IT Director" if tri["tier"] == 2 else "Boss"
    return (
        f"Tier {tri['tier']} escalation to you as {who}. Ticket {tid}: {tri['title']}. "
        f"Why it was escalated: {'; '.join(tri['escalation_reasons']) or 'no known solution'}. "
        f"Suggested route (assign only these staff unless a tool result shows otherwise): {' -> '.join(route) or 'none'}. "
        f"Known solution: {tri['known_solution']} Set the final ticket status with update_ticket. "
        f"Triage: {_brief(tri)}"
    )


async def run_desk(team: Team, client: Client, ticket_ids: list[int] | None = None) -> DeskRunSummary:
    async def call(tool: str, args: dict | None = None) -> dict:
        return (await client.call_tool(tool, args or {})).data

    queue = (await call("list_open_tickets"))["open_tickets"]
    ids = [t["id"] for t in queue if ticket_ids is None or t["id"] in ticket_ids]
    cash = await call("get_cash_position")
    results: list[TicketDispatch] = []

    for tid in ids:
        tri = await call("triage_ticket", {"ticket_id": tid})
        tier, route = tri["tier"], tri["route"]
        owner = Role(route[0]) if tier == 1 else TIER_ROLE[tier]
        await team.log_event("dispatch", ticket_id=tid, detail={**{k: tri[k] for k in (
            "ticket_id", "known_issue", "tier", "route", "escalation_reasons")}, "sent_to": owner.value})
        print(f"Ticket {tid}: {tri['known_issue']} -> Tier {tier} -> {owner.value} (route: {', '.join(route) or 'none'})")

        report = await team.run_agent(owner, _prompt(tri), allowed_roles=frozenset(Role(r) for r in route),
                                      ticket_id=tid)
        status = (await call("get_ticket", {"ticket_id": tid})).get("status")
        results.append(TicketDispatch(
            ticket_id=tid, known_issue=tri["known_issue"], tier=tier, first_owner=owner.value, route=route,
            escalation_reasons=tri["escalation_reasons"], final_status=status,
            report=report if isinstance(report, AgentReport) else None))

    after = await call("get_cash_position")
    return DeskRunSummary(session_id=team.services.session_id, shop_date=cash["today"], tickets=results,
                          cash_after_run=after["total_cash"], token_cost_usd=round(team.services.budget.spent_usd, 6))
