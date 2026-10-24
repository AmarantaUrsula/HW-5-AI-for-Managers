"""IT Director: Tier 2. Takes blocked or multi-team tickets and assigns the minimum staff."""

from ..models import Role
from .base import RoleSpec

SPEC = RoleSpec(
    role=Role.IT_DIRECTOR,
    prompt_file="it_director.md",
    mcp_tools=frozenset({"list_open_tickets", "get_ticket", "triage_ticket", "list_known_issues", "update_ticket"}),
)
