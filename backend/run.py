"""Run the Campus Customs desk: triage every open ticket and send it to Tier 1 staff, the IT Director, or the Boss.

    cd hw5
    python3 -m backend.run                    # full run: resets the working DB first (rule 8)
    python3 -m backend.run --no-reset         # continue on the current working DB
    python3 -m backend.run --tickets 102      # only some tickets
    python3 -m backend.run --non-interactive  # deny every payment automatically

Payments pause for a human in this terminal (2FA over $50). Every agent-loop
step is appended to output/audit_trail.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import shutil
import sys
import uuid
from pathlib import Path

from pydantic_ai.mcp import MCPToolset

from llm import portkey_settings

from .agents import ROLE_SPECS, Services, Team
from .approvals import HumanApprover
from .audit import AuditTrail
from .budget import BudgetExceeded, BudgetGuard
from .mcp_client import make_mcp_client
from .workflow import run_desk

HW5_DIR = Path(__file__).resolve().parent.parent
ORIGINAL_DB = HW5_DIR / "data" / "campus_customs.db"
WORKING_DB = HW5_DIR / "data" / "campus_customs_new.db"


def reset_working_db() -> None:
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    print(f"Reset {WORKING_DB.relative_to(HW5_DIR)} from the original.")


def mcp_client(approval_secret: str):
    return make_mcp_client(approval_secret)


async def main(args: argparse.Namespace) -> int:
    if not args.no_reset:
        reset_working_db()

    _, model = portkey_settings()
    secret = secrets.token_hex(32)
    client = mcp_client(secret)

    async def preview(kind: str, ref_id: int, account: str) -> dict:
        res = await client.call_tool("preview_payment", {"kind": kind, "ref_id": ref_id, "account": account})
        return res.data

    budget = BudgetGuard(model=model, ratchet_model=os.environ.get("HW5_RATCHET_MODEL", model))
    services = Services(
        session_id=uuid.uuid4().hex[:12],
        mcp=MCPToolset(client),
        audit=AuditTrail(),
        budget=budget,
        approver=HumanApprover(secret, preview, interactive=False if args.non_interactive else None),
    )
    team = Team(services, ROLE_SPECS)

    print(f"Session {services.session_id}: model={model} via Portkey, budget=${budget.budget_usd:.2f}")
    async with client:
        try:
            summary = await run_desk(team, client, args.tickets)
        except BudgetExceeded as exc:
            print(f"STOPPED: {exc}")
            return 2

    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    print(f"Token spend this session: ${budget.spent_usd:.4f} "
          f"({budget.input_tokens} in / {budget.output_tokens} out). Audit: output/audit_trail.json")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-reset", action="store_true", help="don't reset the working DB first")
    p.add_argument("--tickets", type=int, nargs="*", help="only these ticket ids")
    p.add_argument("--non-interactive", action="store_true", help="deny all payment approvals")
    sys.exit(asyncio.run(main(p.parse_args())))
