"""Facilities: the lease, landlord, and rent due dates."""

from ..models import Role
from .base import RoleSpec

SPEC = RoleSpec(
    role=Role.FACILITIES,
    prompt_file="facilities.md",
    mcp_tools=frozenset({"get_ticket", "check_rent_due", "update_ticket"}),
)
