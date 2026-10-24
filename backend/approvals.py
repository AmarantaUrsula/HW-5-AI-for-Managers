"""Human-in-the-loop payment approval, with simulated two-factor auth over $50.

When Accounting calls pay_invoice or pay_rent, PydanticAI pauses the run and
returns DeferredToolRequests. This module shows the human the exact payment
(fetched through the MCP tool preview_payment) and asks for:
  factor 1: typing YES and their name
  factor 2 (amount > $50): a one-time code delivered "out of band" to
            output/2fa/one_time_code.txt. This stands in for a text or
            authenticator app.
On approval, it signs that exact payment with the session secret, which only
the MCP server knows, so the pay tool will accept it. The agents never see the
secret or the code. With no terminal attached, every payment is denied.
"""

from __future__ import annotations

import asyncio
import hmac
import secrets
import sys
from pathlib import Path
from typing import Awaitable, Callable

from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolApproved, ToolDenied

from mcp_server.approval import TWO_FACTOR_THRESHOLD_USD, payment_message, sign

from .models import ApprovalDecision

TWO_FA_DIR = Path(__file__).resolve().parent.parent / "output" / "2fa"
PAY_TOOLS = {"pay_invoice": ("invoice", "invoice_id"), "pay_rent": ("rent", "lease_id")}

PreviewFn = Callable[[str, int, str], Awaitable[dict]]


class HumanApprover:
    def __init__(self, secret: str, preview: PreviewFn, interactive: bool | None = None,
                 ask: Callable[[str], str] = input, max_code_tries: int = 3) -> None:
        self.secret = secret
        self.preview = preview
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self.ask = ask
        self.max_code_tries = max_code_tries

    async def _ask(self, prompt: str) -> str:
        return (await asyncio.to_thread(self.ask, prompt)).strip()

    async def decide(self, requests: DeferredToolRequests, requested_by: str, deps=None
                     ) -> tuple[DeferredToolResults, list[ApprovalDecision]]:
        results = DeferredToolResults()
        decisions: list[ApprovalDecision] = []
        for call in requests.approvals:
            args = call.args_as_dict()
            approved, decision = await self._decide_one(call.tool_name, args, requested_by)
            decisions.append(decision)
            results.approvals[call.tool_call_id] = approved
        for call in requests.calls:  # no external tools exist, so just deny these
            results.calls[call.tool_call_id] = ToolDenied("External tool calls are not supported.")
        return results, decisions

    async def _decide_one(self, tool_name: str, args: dict, requested_by: str):
        if tool_name not in PAY_TOOLS:
            d = ApprovalDecision(tool_name=tool_name, kind="unknown", ref_id=-1, approved=False,
                                 reason="Only payment tools can be approved.")
            return ToolDenied(d.reason), d
        kind, id_field = PAY_TOOLS[tool_name]
        ref_id = int(args.get(id_field, -1))
        account = args.get("account") or "checking"
        p = await self.preview(kind, ref_id, account)

        def deny(reason: str, **extra):
            d = ApprovalDecision(tool_name=tool_name, kind=kind, ref_id=ref_id, amount=p.get("amount"),
                                 payee=p.get("payee"), approved=False, reason=reason, **extra)
            return ToolDenied(f"Payment denied: {reason}"), d

        if "error" in p:
            return deny(p["error"])
        if not p["payable"]:
            why = "not enough cash (no negative balances)" if not p["enough_cash"] else f"status is {p['status']}"
            return deny(f"pay tool precheck refused: {why}")
        if not self.interactive:
            return deny("no human is available to approve (non-interactive run)")

        print("\n" + "=" * 64)
        print(f"PAYMENT APPROVAL REQUIRED  (requested by the {requested_by} agent)")
        print(f"  {tool_name}: {kind} #{ref_id} to {p['payee']}")
        print(f"  Amount: ${p['amount']:,.2f}   due {p['due']}{'  (OVERDUE)' if p['overdue'] else ''}   shop date {p['today']}")
        print(f"  {account}: ${p['balance_before']:,.2f} -> ${p['balance_after']:,.2f}")
        print("=" * 64)
        if (await self._ask("Approve this payment? Type YES to approve, anything else to deny: ")) != "YES":
            return deny("human declined")
        name = await self._ask("Approver name: ")
        if not name:
            return deny("no approver name given")

        factor = "1fa"
        if p["amount"] > TWO_FACTOR_THRESHOLD_USD:
            code = f"{secrets.randbelow(10**6):06d}"
            TWO_FA_DIR.mkdir(parents=True, exist_ok=True)
            code_file = TWO_FA_DIR / "one_time_code.txt"
            code_file.write_text(f"Campus Customs one-time approval code: {code}\n", encoding="utf-8")
            print(f"Two-factor required (over ${TWO_FACTOR_THRESHOLD_USD:.0f}). "
                  f"A one-time code was sent to {code_file.relative_to(TWO_FA_DIR.parent.parent)}.")
            try:
                for attempt in range(1, self.max_code_tries + 1):
                    if hmac.compare_digest(await self._ask("Enter the 6-digit code: "), code):
                        factor = "2fa"
                        break
                    print(f"Wrong code ({attempt}/{self.max_code_tries}).")
                else:
                    return deny("two-factor code not verified", approved_by=name)
            finally:
                code_file.unlink(missing_ok=True)

        token = sign(self.secret, payment_message(kind, ref_id, p["amount"], p["due"], account, name, factor))
        d = ApprovalDecision(tool_name=tool_name, kind=kind, ref_id=ref_id, amount=p["amount"],
                             payee=p["payee"], approved=True, approved_by=name, factor=factor,
                             reason="human approved" + (" with two-factor code" if factor == "2fa" else ""))
        override = {**args, id_field: ref_id, "account": account, "approved_by": name,
                    "approval_factor": factor, "approval_token": token}
        return ToolApproved(override_args=override), d
