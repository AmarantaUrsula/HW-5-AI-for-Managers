"""The six Campus Customs roles (Boss, IT Director, and four specialists). Each file holds one role's MCP tool list; base.py holds the shared loop."""

from . import accounting, boss, customer_service, facilities, inventory, it_director
from .base import Services, Team

ROLE_SPECS = [boss.SPEC, it_director.SPEC, inventory.SPEC, accounting.SPEC, facilities.SPEC, customer_service.SPEC]

__all__ = ["ROLE_SPECS", "Services", "Team"]
