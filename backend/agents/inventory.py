"""Inventory: stock on hand, shortfalls, which vendor restocks, and whether it can ship."""

from ..models import Role
from .base import RoleSpec

SPEC = RoleSpec(
    role=Role.INVENTORY,
    prompt_file="inventory.md",
    mcp_tools=frozenset({"get_ticket", "check_stock_and_price", "list_vendors", "check_vendor_can_ship", "update_ticket"}),
)
