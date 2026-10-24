"""Boss: Tier 3. Takes only escalations with a cash conflict, and sets priorities with a human."""

from ..models import Role
from .base import RoleSpec

SPEC = RoleSpec(
    role=Role.BOSS,
    prompt_file="boss.md",
    mcp_tools=frozenset({"list_open_tickets", "get_ticket", "triage_ticket", "list_known_issues", "get_cash_position", "update_ticket"}),
)
