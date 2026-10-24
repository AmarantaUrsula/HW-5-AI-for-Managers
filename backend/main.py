"""FastAPI backend for the Campus Customs React dashboard.

Start it from the backend/ folder:
    cd hw5/backend
    uvicorn main:app --reload --port 8000
(or from hw5/: python3 -m uvicorn backend.main:app --reload --port 8000)

Rules this API keeps:
  * Shop data only through the campus-customs MCP server (rule 13).
  * Agents only PREPARE payments. Cash changes only in POST /api/payments/{id}/approve,
    after a human clicks Approve, with a one-time 2FA code over $50.
  * The pay tool refuses anything that would make a balance negative.
  * Every agent step goes to output/audit_trail.json, append-only.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import shutil
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HW5_DIR = Path(__file__).resolve().parent.parent
if str(HW5_DIR) not in sys.path:  # lets `uvicorn main:app` work from inside backend/
    sys.path.insert(0, str(HW5_DIR))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from pydantic_ai.mcp import MCPToolset  # noqa: E402

from backend.agents import ROLE_SPECS, Services, Team  # noqa: E402
from backend.audit import AUDIT_PATH, AuditTrail  # noqa: E402
from backend.budget import BudgetExceeded, BudgetGuard  # noqa: E402
from backend.mcp_client import make_mcp_client  # noqa: E402
from backend.models import TicketsResponse  # noqa: E402
from backend.payments import PendingApprover, PendingStore, TwoFactor  # noqa: E402
from backend.workflow import run_desk  # noqa: E402
from llm import portkey_settings  # noqa: E402
from mcp_server.approval import TWO_FACTOR_THRESHOLD_USD, payment_message, sign  # noqa: E402

ORIGINAL_DB = HW5_DIR / "data" / "campus_customs.db"
WORKING_DB = HW5_DIR / "data" / "campus_customs_new.db"
PAY_TOOL = {"invoice": ("pay_invoice", "invoice_id"), "rent": ("pay_rent", "lease_id")}
# A ticket is "resolved" once its agent run has finished and nothing on it is waiting for a human.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@asynccontextmanager
async def lifespan(app: FastAPI):
    secret = secrets.token_hex(32)  # only the MCP server and this process know it; agents never see it
    client = make_mcp_client(secret)
    _, model = portkey_settings()
    async with client:
        app.state.mcp = client
        app.state.secret = secret
        app.state.audit = AuditTrail()
        app.state.budget = BudgetGuard(model=model, ratchet_model=model)  # $500 cap for the server's lifetime
        app.state.pending = PendingStore()
        app.state.two_factor = TwoFactor()
        app.state.runs: dict[str, dict] = {}
        app.state.run_lock = asyncio.Lock()
        yield


app = FastAPI(title="Campus Customs desk API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


async def mcp_call(app_: FastAPI, tool: str, args: dict[str, Any] | None = None, *, raise_404: bool = True) -> dict:
    result = (await app_.state.mcp.call_tool(tool, args or {})).data
    if raise_404 and isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


async def human_event(app_: FastAPI, event: str, ticket_id: int | None, detail: dict) -> None:
    """Audit entries for human actions taken on the dashboard."""
    from backend.audit import now
    from backend.models import AuditEntry, UsageRecord
    b = app_.state.budget
    await app_.state.audit.append(AuditEntry(
        timestamp=now(), session_id="dashboard", run_id="dashboard", ticket_id=ticket_id, agent="human",
        event=event, detail=detail,
        usage=UsageRecord(session_cost_usd=round(b.spent_usd, 6), budget_usd=b.budget_usd, ratcheted=b.ratcheted)))


# ---------------------------------------------------------------- health and tickets

@app.get("/api/health")
async def health(request: Request) -> dict:
    tools = await request.app.state.mcp.list_tools()
    return {"ok": True, "mcp_tools": len(tools)}


@app.get("/api/tickets", response_model=TicketsResponse)
async def get_tickets(request: Request) -> dict:
    """Every ticket, and whether it's open or resolved (MCP tool list_tickets)."""
    return await mcp_call(request.app, "list_tickets")


# ---------------------------------------------------------------- run the agent team on one ticket

async def _run_ticket(app_: FastAPI, run: dict) -> None:
    async def preview(kind: str, ref_id: int, account: str) -> dict:
        return await mcp_call(app_, "preview_payment", {"kind": kind, "ref_id": ref_id, "account": account},
                              raise_404=False)

    services = Services(session_id=run["session_id"], mcp=MCPToolset(app_.state.mcp), audit=app_.state.audit,
                        budget=app_.state.budget, approver=PendingApprover(app_.state.pending, preview))
    team = Team(services, ROLE_SPECS)
    try:
        summary = await run_desk(team, app_.state.mcp, [run["ticket_id"]])
        run.update(status="done", summary=summary.model_dump(mode="json"))
        run["resolution"] = await _resolve_if_clear(app_, run["ticket_id"], f"Agent run {run['session_id']} finished.")
    except BudgetExceeded as exc:
        run.update(status="stopped", error=str(exc))
    except Exception as exc:  # surface to the dashboard instead of dying silently
        run.update(status="error", error=f"{type(exc).__name__}: {exc}")
        await team.log_event("error", ticket_id=run["ticket_id"], detail={"error": run["error"]})
    finally:
        run["finished_at"] = _now()
        app_.state.run_lock.release()


def _pending_for(app_: FastAPI, ticket_id: int) -> list[dict]:
    return [p for p in app_.state.pending.items if p.get("ticket_id") == ticket_id and p["status"] == "pending"]


async def _resolve_if_clear(app_: FastAPI, ticket_id: int, why: str) -> dict:
    """Mark the ticket resolved once its run is done and no payment on it is waiting for a human."""
    waiting = _pending_for(app_, ticket_id)
    if waiting:
        return {"resolved": False, "waiting_on": [p["id"] for p in waiting]}
    upd = await mcp_call(app_, "update_ticket", {"ticket_id": ticket_id, "status": "resolved",
                                                 "note": f"{why} Nothing is waiting on a human; marked resolved."},
                         raise_404=False)
    return {"resolved": "error" not in upd, "ticket_update": upd}


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int, request: Request) -> dict:
    """Start the agent team on one ticket (triage, then Tier 1 staff, IT Director, or Boss). Runs in the background."""
    app_ = request.app
    ticket = await mcp_call(app_, "get_ticket", {"ticket_id": ticket_id})
    if ticket["status"] == "resolved":
        raise HTTPException(409, f"Ticket {ticket_id} is already resolved.")
    if app_.state.run_lock.locked():
        raise HTTPException(409, "Another agent run is in progress. Wait for it to finish.")
    await app_.state.run_lock.acquire()
    run = {"session_id": uuid.uuid4().hex[:12], "ticket_id": ticket_id, "status": "running",
           "started_at": _now(), "finished_at": None, "summary": None, "error": None, "resolution": None}
    app_.state.runs[run["session_id"]] = run
    run["_task"] = asyncio.create_task(_run_ticket(app_, run))
    return {k: v for k, v in run.items() if not k.startswith("_")}


@app.get("/api/runs")
async def list_runs(request: Request) -> list[dict]:
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in request.app.state.runs.values()]


@app.get("/api/runs/{session_id}")
async def get_run(session_id: str, request: Request) -> dict:
    run = request.app.state.runs.get(session_id)
    if run is None:
        raise HTTPException(404, f"No run {session_id}.")
    return {k: v for k, v in run.items() if not k.startswith("_")}


# ---------------------------------------------------------------- recent agent events

def _event_view(i: int, e: dict) -> dict:
    said = e.get("text")
    if said is None and e["event"] == "run_end":
        out = e.get("output") or {}
        said = out.get("recommendation") if isinstance(out, dict) else None
    return {
        "index": i, "timestamp": e["timestamp"], "session_id": e["session_id"], "run_id": e["run_id"],
        "ticket_id": e.get("ticket_id"), "agent": e["agent"], "delegated_by": e.get("delegated_by"),
        "depth": e.get("depth", 0), "event": e["event"], "said": said,
        "tools_used": [{"tool": c["tool_name"], "args": c.get("args")} for c in e.get("tool_calls", [])
                       if c["tool_name"] != "final_result"],
        "tool_results": [{"tool": r["tool_name"], "result": r.get("content")} for r in e.get("tool_results", [])],
        "detail": e.get("detail") or {},
    }


@app.get("/api/events")
async def recent_events(since: int = 0, limit: int = 50, ticket_id: int | None = None,
                        session_id: str | None = None) -> dict:
    """Recent agent events (what each agent said and which tools it used). Poll with ?since=<next_since>."""
    entries = json.loads(AUDIT_PATH.read_text(encoding="utf-8")) if AUDIT_PATH.exists() else []
    picked = [
        _event_view(i, e) for i, e in enumerate(entries)
        if i >= since and e["event"] not in ("model_request", "end_node")
        and (ticket_id is None or e.get("ticket_id") == ticket_id)
        and (session_id is None or e["session_id"] == session_id)
    ]
    return {"events": picked[-limit:], "next_since": len(entries), "total": len(entries)}


@app.get("/api/tickets/{ticket_id}/summary")
async def ticket_summary(ticket_id: int, session_id: str | None = None) -> dict:
    """What each agent did on a ticket in its latest run (or the given session): tools, hand-offs, and report."""
    entries = json.loads(AUDIT_PATH.read_text(encoding="utf-8")) if AUDIT_PATH.exists() else []
    mine = [e for e in entries if e.get("ticket_id") == ticket_id and e["agent"] not in ("human",)]
    if session_id is None:
        sessions = [e["session_id"] for e in mine if e["event"] == "dispatch"]
        if not sessions:
            return {"ticket_id": ticket_id, "session_id": None, "dispatch": None, "agents": []}
        session_id = sessions[-1]
    run = [e for e in mine if e["session_id"] == session_id]
    dispatch = next((e["detail"] for e in run if e["event"] == "dispatch"), None)
    agents: dict[str, dict] = {}
    for e in run:
        if e["agent"] == "dispatcher":
            continue
        a = agents.setdefault(e["agent"], {"agent": e["agent"], "delegated_by": e.get("delegated_by"),
                                           "tools_used": {}, "handed_off_to": [], "payments_prepared": [],
                                           "report": None, "steps": 0})
        a["steps"] += e["event"] == "model_response"
        for c in e.get("tool_calls", []):
            if c["tool_name"] not in ("final_result", "delegate"):
                a["tools_used"][c["tool_name"]] = a["tools_used"].get(c["tool_name"], 0) + 1
        if e["event"] == "delegation":
            a["handed_off_to"].append(e["detail"].get("to"))
        if e["event"] == "approval_decision":
            a["payments_prepared"].append(e["detail"])
        if e["event"] == "run_end":
            a["report"] = e.get("output")
    humans = [ _event_view(i, e) for i, e in enumerate(entries)
               if e.get("ticket_id") == ticket_id and e["agent"] == "human" and e["timestamp"] >= (run[0]["timestamp"] if run else "")]
    return {"ticket_id": ticket_id, "session_id": session_id, "dispatch": dispatch,
            "agents": [{**a, "tools_used": [{"tool": k, "calls": v} for k, v in a["tools_used"].items()]}
                       for a in agents.values()],
            "human_actions": [{"event": h["event"], "timestamp": h["timestamp"], "detail": h["detail"]} for h in humans]}


# ---------------------------------------------------------------- payments: human approves, cash changes here

class ApproveBody(BaseModel):
    approved_by: str
    code: str | None = None  # one-time 2FA code, required over $50


class DenyBody(BaseModel):
    denied_by: str
    reason: str = "denied on dashboard"


def _pending_or_404(request: Request, pid: str) -> dict:
    item = request.app.state.pending.get(pid)
    if item is None:
        raise HTTPException(404, f"No payment {pid}.")
    return item


@app.get("/api/payments")
async def list_payments(request: Request, status: str | None = None) -> list[dict]:
    """Payments the agents prepared (pending), plus approved, denied, failed, and void ones."""
    return [p for p in request.app.state.pending.items if status is None or p["status"] == status]


@app.post("/api/payments/{pid}/request-code")
async def request_code(pid: str, request: Request) -> dict:
    """Send a one-time 2FA code for a payment over $50 (simulated: written to output/2fa/<payment id>_code.txt)."""
    item = _pending_or_404(request, pid)
    if item["status"] != "pending":
        raise HTTPException(409, f"{pid} is {item['status']}, not pending.")
    sent = request.app.state.two_factor.issue(pid)
    await human_event(request.app, "2fa_code_sent", item.get("ticket_id"), {"payment": pid, **sent})
    return {"payment": pid, **sent}


@app.post("/api/payments/{pid}/approve")
async def approve_payment(pid: str, body: ApproveBody, request: Request) -> dict:
    """A human clicked Approve. This is the only route that changes cash."""
    app_ = request.app
    item = _pending_or_404(request, pid)
    if item["status"] != "pending":
        raise HTTPException(409, f"{pid} is {item['status']}, not pending.")
    name = body.approved_by.strip()
    if not name:
        raise HTTPException(400, "approved_by is required.")

    p = await mcp_call(app_, "preview_payment", {"kind": item["kind"], "ref_id": item["ref_id"],
                                                  "account": item["account"]})
    factor = "1fa"
    if p["amount"] > TWO_FACTOR_THRESHOLD_USD:
        ok, msg = app_.state.two_factor.verify(pid, body.code)
        if not ok:
            await human_event(app_, "approval_rejected", item.get("ticket_id"), {"payment": pid, "reason": msg})
            raise HTTPException(401, f"Two-factor check failed: {msg}")
        factor = "2fa"

    tool, id_field = PAY_TOOL[item["kind"]]
    token = sign(app_.state.secret, payment_message(item["kind"], item["ref_id"], p["amount"], p["due"],
                                                    item["account"], name, factor))
    result = await mcp_call(app_, tool, {id_field: item["ref_id"], "account": item["account"], "approved_by": name,
                                         "approval_factor": factor, "approval_token": token}, raise_404=False)
    if not result.get("paid"):
        app_.state.pending.update(pid, status="failed", decided_by=name, decided_at=_now(), factor=factor,
                                  reason=result.get("reason"), result=result)
        await human_event(app_, "payment_refused", item.get("ticket_id"), {"payment": pid, **result})
        raise HTTPException(409, f"Pay tool refused: {result.get('reason')}")

    item = app_.state.pending.update(pid, status="approved", decided_by=name, decided_at=_now(), factor=factor,
                                     reason="approved on dashboard", result=result)
    await human_event(app_, "payment_approved", item.get("ticket_id"), {"payment": pid, **result})
    resolution = None
    if item.get("ticket_id"):
        resolution = await _resolve_if_clear(
            app_, item["ticket_id"],
            f"Payment {pid} approved by {name} ({factor}) on the dashboard: ${result['amount']:.2f} to "
            f"{result['payee']}; {item['account']} ${result['balance_before']:.2f} -> ${result['balance_after']:.2f}.")
    return {"payment": item, "resolution": resolution}


@app.post("/api/payments/{pid}/deny")
async def deny_payment(pid: str, body: DenyBody, request: Request) -> dict:
    item = _pending_or_404(request, pid)
    if item["status"] != "pending":
        raise HTTPException(409, f"{pid} is {item['status']}, not pending.")
    item = request.app.state.pending.update(pid, status="denied", decided_by=body.denied_by, decided_at=_now(),
                                            reason=body.reason)
    await human_event(request.app, "payment_denied", item.get("ticket_id"), {"payment": pid, "reason": body.reason})
    ticket_update = None
    if item.get("ticket_id"):  # denied: the ticket isn't done, so it goes back to a person to follow up
        ticket_update = await mcp_call(request.app, "update_ticket", {
            "ticket_id": item["ticket_id"], "status": "in_progress",
            "note": f"Payment {pid} denied by {body.denied_by}: {body.reason}. Needs follow-up."}, raise_404=False)
    return {"payment": item, "ticket_update": ticket_update}


# ---------------------------------------------------------------- cash and reset

@app.get("/api/cash")
async def cash(request: Request) -> dict:
    """Current balances from cash_accounts, plus what's owed and what's waiting for approval."""
    pos = await mcp_call(request.app, "get_cash_position")
    pending = [p for p in request.app.state.pending.items if p["status"] == "pending"]
    return {"today": pos["today"], "accounts": pos["accounts"], "total_cash": pos["total_cash"],
            "obligations": pos["obligations"], "cash_after_all_obligations": pos["cash_after_all_obligations"],
            "pending_approval_total": round(sum(p["amount"] for p in pending), 2)}


@app.post("/api/reset")
async def reset(request: Request) -> dict:
    """Copy the original DB over the working copy for a fresh run. The audit trail is kept, and pending payments are voided."""
    app_ = request.app
    if app_.state.run_lock.locked():
        raise HTTPException(409, "An agent run is in progress. Reset after it finishes.")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    voided = app_.state.pending.void_pending("database reset")
    await human_event(app_, "reset", None, {"voided_pending_payments": voided})
    tickets = await mcp_call(app_, "list_tickets")
    cash_now = await mcp_call(app_, "get_cash_position")
    return {"reset": True, "voided_pending_payments": voided, "open_tickets": tickets["open"],
            "total_cash": cash_now["total_cash"]}
