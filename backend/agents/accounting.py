"""Accounting: cash position and the only role with payment tools (human approval + 2FA required)."""

from ..models import Role
from .base import RoleSpec

SPEC = RoleSpec(
    role=Role.ACCOUNTING,
    prompt_file="accounting.md",
    mcp_tools=frozenset({"get_ticket", "get_cash_position", "preview_payment", "pay_invoice", "pay_rent", "check_vendor_can_ship", "quote_bulk_discount", "update_ticket"}),
)
