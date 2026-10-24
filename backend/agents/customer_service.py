"""Customer Service: replies to requesters as drafts only (never sent), plus discount quotes."""

from ..models import Role
from .base import RoleSpec

SPEC = RoleSpec(
    role=Role.CUSTOMER_SERVICE,
    prompt_file="customer_service.md",
    mcp_tools=frozenset({"get_ticket", "check_stock_and_price", "quote_bulk_discount", "draft_message", "update_ticket"}),
)
