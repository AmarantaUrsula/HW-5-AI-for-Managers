"""Dashboard payment flow: agents prepare payments, and only a human click moves cash.

In API mode, an agent's pay_invoice or pay_rent call doesn't pay anything.
PendingApprover records it as a pending payment in output/pending_payments.json,
and the agent is told it's waiting for a human. The money only moves when a
human clicks Approve on the dashboard (POST /api/payments/{id}/approve). Over
$50 that also needs a one-time 2FA code, which comes from a separate request
(simulated as output/2fa/<payment id>_code.txt).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolDenied

from .approvals import PAY_TOOLS
from .models import ApprovalDecision

HW5_DIR = Path(__file__).resolve().parent.parent
PENDING_PATH = HW5_DIR / "output" / "pending_payments.json"
TWO_FA_DIR = HW5_DIR / "output" / "2fa"
CODE_TTL_SECONDS = 300
MAX_CODE_TRIES = 3

PreviewFn = Callable[[str, int, str], Awaitable[dict]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PendingStore:
    """Payments the agents prepared, kept in a JSON file so the dashboard survives a restart."""

    def __init__(self, path: Path = PENDING_PATH) -> None:
        self.path = path
        self.items: list[dict[str, Any]] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else []
        )

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.items, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, pid: str) -> dict | None:
        return next((p for p in self.items if p["id"] == pid), None)

    def find_pending(self, kind: str, ref_id: int) -> dict | None:
        return next((p for p in self.items if p["kind"] == kind and p["ref_id"] == ref_id
                     and p["status"] == "pending"), None)

    def add(self, **fields: Any) -> dict:
        item = {"id": f"P-{len(self.items) + 1:04d}", "status": "pending", "created_at": _now(),
                "decided_by": None, "decided_at": None, "factor": None, "reason": None, "result": None,
                **fields}
        self.items.append(item)
        self._save()
        return item

    def update(self, pid: str, **fields: Any) -> dict:
        item = self.get(pid)
        item.update(fields)
        self._save()
        return item

    def void_pending(self, reason: str) -> int:
        n = 0
        for p in self.items:
            if p["status"] == "pending":
                p.update(status="void", reason=reason, decided_at=_now())
                n += 1
        self._save()
        return n


class PendingApprover:
    """Stands in for HumanApprover in API runs: it turns pay-tool calls into pending payments."""

    def __init__(self, store: PendingStore, preview: PreviewFn) -> None:
        self.store = store
        self.preview = preview

    async def decide(self, requests: DeferredToolRequests, requested_by: str, deps: Any = None
                     ) -> tuple[DeferredToolResults, list[ApprovalDecision]]:
        results, decisions = DeferredToolResults(), []
        for call in requests.approvals:
            args = call.args_as_dict()
            if call.tool_name not in PAY_TOOLS:
                d = ApprovalDecision(tool_name=call.tool_name, kind="unknown", ref_id=-1, approved=False,
                                     reason="Only payment tools can be approved.")
                results.approvals[call.tool_call_id] = ToolDenied(d.reason)
                decisions.append(d)
                continue
            kind, id_field = PAY_TOOLS[call.tool_name]
            ref_id, account = int(args.get(id_field, -1)), args.get("account") or "checking"
            p = await self.preview(kind, ref_id, account)
            base = dict(tool_name=call.tool_name, kind=kind, ref_id=ref_id, amount=p.get("amount"),
                        payee=p.get("payee"), approved=False)
            if "error" in p or not p.get("payable"):
                why = p.get("error") or ("not enough cash (no negative balances)" if not p["enough_cash"]
                                         else f"status is {p['status']}")
                d = ApprovalDecision(**base, reason=f"pay tool precheck refused: {why}")
                results.approvals[call.tool_call_id] = ToolDenied(f"Payment refused: {why}. Nothing was paid.")
            else:
                item = self.store.find_pending(kind, ref_id) or self.store.add(
                    kind=kind, ref_id=ref_id, account=account, amount=p["amount"], payee=p["payee"],
                    due=p["due"], overdue=p["overdue"], requires_two_factor=p["requires_two_factor"],
                    balance_before=p["balance_before"], balance_after=p["balance_after"],
                    ticket_id=getattr(deps, "ticket_id", None), requested_by=requested_by,
                    session_id=getattr(getattr(deps, "services", None), "session_id", None),
                    run_id=getattr(deps, "run_id", None))
                d = ApprovalDecision(**base, reason=f"prepared for human approval as {item['id']}")
                results.approvals[call.tool_call_id] = ToolDenied(
                    f"Payment prepared for human approval as {item['id']}: ${p['amount']:.2f} to {p['payee']}. "
                    "It has NOT been paid yet. A human must approve it on the dashboard"
                    + (" with a 2FA code" if p["requires_two_factor"] else "")
                    + ". Set the ticket to waiting_on_approval and don't request it again.")
            decisions.append(d)
        for call in requests.calls:
            results.calls[call.tool_call_id] = ToolDenied("External tool calls are not supported.")
        return results, decisions


class TwoFactor:
    """One-time codes for dashboard approvals. Only a hash is kept in memory, and the code goes to a separate channel."""

    def __init__(self) -> None:
        self._codes: dict[str, dict] = {}

    @staticmethod
    def _hash(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    def issue(self, pid: str) -> dict:
        code = f"{secrets.randbelow(10**6):06d}"
        self._codes[pid] = {"hash": self._hash(code), "expires": time.time() + CODE_TTL_SECONDS, "tries": 0}
        # One file per payment, so a code for one payment never overwrites another's.
        TWO_FA_DIR.mkdir(parents=True, exist_ok=True)
        path = TWO_FA_DIR / f"{pid}_code.txt"
        issued = datetime.now().strftime("%H:%M:%S")
        path.write_text(f"Campus Customs one-time approval code for {pid} (sent {issued}, valid 5 minutes): {code}\n",
                        encoding="utf-8")
        return {"sent_to": str(path.relative_to(HW5_DIR)), "issued_at": issued, "expires_in_seconds": CODE_TTL_SECONDS}

    def verify(self, pid: str, code: str | None) -> tuple[bool, str]:
        entry = self._codes.get(pid)
        if entry is None:
            return False, "No code was requested for this payment. Request a code first."
        if time.time() > entry["expires"]:
            self._codes.pop(pid, None)
            return False, "The code expired. Request a new one."
        entry["tries"] += 1
        if code and hmac.compare_digest(self._hash(code.strip()), entry["hash"]):
            self._codes.pop(pid, None)
            (TWO_FA_DIR / f"{pid}_code.txt").unlink(missing_ok=True)
            return True, "verified"
        if entry["tries"] >= MAX_CODE_TRIES:
            self._codes.pop(pid, None)
            return False, "Too many wrong codes. Request a new one."
        return False, f"Wrong code ({entry['tries']}/{MAX_CODE_TRIES})."
