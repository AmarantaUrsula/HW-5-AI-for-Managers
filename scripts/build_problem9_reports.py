"""Build the Problem 9 reports from the real run, not from memory.

    cd hw5 && python3 scripts/build_problem9_reports.py

Reads data/campus_customs_new.db, output/audit_trail.json, output/pending_payments.json,
and output/p9_start_snapshot.json. Writes:
  output/desk_tickets.html   (fills each ticket's Actual section and the Cash tab; Expected is untouched)
  output/resolved_tickets.json
  output/resolved_board.html (screenshots in output/screenshots/)
Stops with an error if the cash itemization doesn't reconcile with cash_accounts.
"""

import html
import json
import re
import sqlite3
from pathlib import Path

HW5 = Path(__file__).resolve().parent.parent
OUT = HW5 / "output"
SESSIONS = {101: "373b7f2dcb44", 102: "910d070c6c28", 103: "6f6ddfcfa974"}
PAYMENT_FOR = {101: "P-0003", 102: "P-0004", 103: None}
NAMES = {"dispatcher": "Desk triage", "it_director": "IT Director", "inventory": "Inventory",
         "accounting": "Accounting", "facilities": "Facilities", "customer_service": "Customer Service",
         "boss": "Boss", "human": "Human"}
CODES = {"dispatcher": "DSK", "it_director": "ITD", "inventory": "INV", "accounting": "ACC",
         "facilities": "FAC", "customer_service": "CSV", "boss": "BOS", "human": "HUM"}
e = html.escape


def money(x: float) -> str:
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


# ------------------------------------------------------------------ load the real data
db = sqlite3.connect(HW5 / "data" / "campus_customs_new.db")
db.row_factory = sqlite3.Row
cash_rows = [dict(r) for r in db.execute("SELECT * FROM cash_accounts")]
payments_rows = [dict(r) for r in db.execute("SELECT * FROM payments ORDER BY id")]
tickets = {r["id"]: dict(r) for r in db.execute("SELECT * FROM tickets")}
invoice_501 = dict(db.execute("SELECT * FROM invoices WHERE id = 501").fetchone())
lease_1 = dict(db.execute("SELECT * FROM leases WHERE id = 1").fetchone())
audit = json.loads((OUT / "audit_trail.json").read_text())
pending = {p["id"]: p for p in json.loads((OUT / "pending_payments.json").read_text())}
start = json.loads((OUT / "p9_start_snapshot.json").read_text())
start_balance = next(a["balance"] for a in start["cash_accounts"] if a["name"] == "checking")
end_balance = next(a["balance"] for a in cash_rows if a["name"] == "checking")


def run_entries(tid: int) -> list[dict]:
    return [x for x in audit if x["session_id"] == SESSIONS[tid]]


def agent_facts(tid: int) -> dict:
    run = run_entries(tid)
    dispatch = next(x["detail"] for x in run if x["event"] == "dispatch")
    agents: dict[str, dict] = {}
    for x in run:
        if x["agent"] == "dispatcher":
            continue
        a = agents.setdefault(x["agent"], {"agent": x["agent"], "asked_by": x.get("delegated_by"), "tools": [],
                                           "delegated": [], "prepared": [], "report": None})
        for c in x["tool_calls"]:
            if c["tool_name"] not in ("final_result", "delegate"):
                a["tools"].append(c["tool_name"])
        if x["event"] == "delegation":
            a["delegated"].append({"to": x["detail"]["to"], "request": x["detail"]["request"]})
        if x["event"] == "approval_decision":
            a["prepared"].append(x["detail"]["reason"])
        if x["event"] == "run_end":
            a["report"] = x["output"]
    costs = [x["usage"]["session_cost_usd"] for x in run]
    return {"dispatch": dispatch, "agents": agents, "token_cost_usd": round(max(costs) - min(costs), 4),
            "started": run[0]["timestamp"], "ended": run[-1]["timestamp"]}


def human_actions(tid: int) -> list[dict]:
    return [x for x in audit if x["agent"] == "human" and x.get("ticket_id") == tid
            and x["timestamp"] >= start["taken_at"][:10]
            and x["timestamp"] > "2026-10-24T13:42:57"]


FACTS = {tid: agent_facts(tid) for tid in SESSIONS}
HUMANS = {tid: human_actions(tid) for tid in SESSIONS}

# ------------------------------------------------------------------ cash reconciliation (must match the DB)
ledger = []
running = start_balance
for tid in (101, 102, 103):
    pid = PAYMENT_FOR[tid]
    if pid:
        p = pending[pid]
        assert p["status"] == "approved", f"{pid} is {p['status']}"
        r = p["result"]
        assert abs(r["balance_before"] - running) < 0.005, f"{pid} balance_before {r['balance_before']} != running {running}"
        running = round(running - r["amount"], 2)
        assert abs(r["balance_after"] - running) < 0.005
        row = next(x for x in payments_rows if x["kind"] == p["kind"] and x["ref_id"] == p["ref_id"])
        ledger.append({"ticket_id": tid, "change": -r["amount"], "balance_after": running, "payment": pid,
                       "payments_row_id": row["id"], "kind": p["kind"], "ref_id": p["ref_id"], "payee": r["payee"],
                       "approved_by": p["decided_by"], "factor": p["factor"], "approved_at": p["decided_at"]})
    else:
        ledger.append({"ticket_id": tid, "change": 0.0, "balance_after": running, "payment": None})
assert abs(running - end_balance) < 0.005, f"ledger ends at {running}, cash_accounts says {end_balance}"
assert abs(start_balance - sum(p["amount"] for p in payments_rows) - end_balance) < 0.005
assert all(t["status"] == "resolved" for t in tickets.values()), "not every ticket is resolved"

# ------------------------------------------------------------------ hand-checked comparison notes
COMPARE = {
    101: [
        ("match", "Triage gave KI-ORDER-VENDOR-BLOCKED, Tier 2, and sent it to the IT Director, as expected."),
        ("match", "Only the expected route was used: inventory, accounting and customer_service. Facilities and the Boss weren't involved."),
        ("match", "Inventory found 0 on hand (short 1), Bulldog blocked by invoice 501 ($840, 3 days overdue), and earliest arrival 2026-09-05."),
        ("match", "Accounting called get_cash_position and preview_payment, then pay_invoice, which prepared P-0003 ($840). A human approved it with 2FA, and checking went $3,400.00 → $2,560.00."),
        ("differs", "Accounting called pay_invoice twice. The second call matched the same pending payment, so only one payment (P-0003) existed and only one was paid."),
        ("differs", "Expected the final status waiting_on_vendor. It's resolved, because the board now marks a ticket resolved once its run is done and nothing waits on a human. The tee itself still arrives 2026-09-05 at the earliest."),
        ("differs", "The customer draft mentions the invoice and the payment approval to Tauhid. The prompt asks Customer Service not to expose internal money matters. It's a draft that was never sent, so a human can edit it."),
    ],
    102: [
        ("match", "Triage gave KI-RENT-ROUTINE, Tier 1, and sent it **straight to Facilities**. No IT Director and no Boss, as expected."),
        ("match", "Facilities ran check_rent_due(1): $2,400, due 2026-09-02, in 2 days. It handed off only to Accounting."),
        ("match", "Accounting ran preview_payment, then pay_rent, which prepared P-0004 ($2,400). A human approved it with 2FA, and checking went $2,560.00 → $160.00."),
        ("match", "Lease 1 next_due moved 2026-09-02 → 2026-10-02, and the ticket is resolved."),
        ("differs", "Accounting called pay_rent twice. The duplicate matched the same pending P-0004, so it was paid once."),
    ],
    103: [
        ("match", "Triage gave KI-DISCOUNT-SHORTFALL, Tier 2, and sent it to the IT Director. Only inventory and customer_service were used, with **no Accounting and no Facilities**."),
        ("match", "Inventory found 8 on hand, short 12. Bulldog was still blocked, because 501 wasn't paid yet when 103 ran at 09:43. Earliest arrival 2026-09-05 if unblocked."),
        ("match", "Customer Service ran quote_bulk_discount and saved a draft. No money moved, and the ticket resolved at the end of the run."),
        ("differs", "Customer Service proposed **no discount** ($58 list, $1,160 for 20), where a discount above the $22 cost was expected. That's allowed, because the price stays above cost, but the club asked for a discount."),
        ("differs", "The draft shows the club the internal unit cost, the margin and the overdue invoice. It shouldn't. A human must edit it before sending."),
        ("differs", "Customer Service delegated back to Inventory to recheck facts, an extra step that was allowed by the route. Inventory's reply included a confusing line ('only 4 units are short'). The ticket note and the draft still use the correct numbers (8 on hand, short 12)."),
    ],
}
OUTCOME = {
    101: "Invoice 501 ($840) was paid after human 2FA approval, so Bulldog Print Co can ship the size S reprint (earliest 2026-09-05). A customer update draft is saved for Tauhid Zaman (not sent).",
    102: "Rent of $2,400 for lease 1 was paid after human 2FA approval. The next rent is due 2026-10-02.",
    103: "No money moved. 8 hoodies are on hand and 12 are short. A no-discount offer ($58 each, $1,160 for 20) was saved as a draft for the Yale AI Club, pending human review (not sent).",
}


# ------------------------------------------------------------------ desk_tickets.html: Actual sections
def actual_html(tid: int) -> str:
    f = FACTS[tid]
    d = f["dispatch"]
    rows = []
    order = [a for a in f["agents"].values()]
    for i, a in enumerate(order, 1):
        tools = ", ".join(f"<code>{e(t)}</code>" for t in a["tools"]) or "—"
        did = []
        for dl in a["delegated"]:
            did.append(f"Delegated to <b>{e(NAMES[dl['to']])}</b>: “{e(dl['request'][:180])}{'…' if len(dl['request']) > 180 else ''}”")
        for pr in a["prepared"]:
            did.append(f"Payment {e(pr)}")
        rep = a["report"] or {}
        if rep.get("drafts_saved"):
            did.append("Saved draft (not sent): <code>" + e(rep["drafts_saved"][-1]) + "</code>")
        if rep.get("recommendation"):
            did.append("Reported: " + e(rep["recommendation"]))
        who = f'<span class="role{" it" if a["agent"] == "it_director" else ""}">{e(NAMES[a["agent"]])}</span>'
        if a["asked_by"]:
            who += f'<br><span class="sub">asked by {e(NAMES[a["asked_by"]])}</span>'
        rows.append(f"<tr><td>{i}</td><td>{who}</td><td>{'<br>'.join(did) or '—'}</td><td>{tools}</td></tr>")
    hums = HUMANS[tid]
    hum_lines = []
    for h in hums:
        dt = h["detail"]
        if h["event"] == "2fa_code_sent":
            hum_lines.append(f"{h['timestamp'][11:19]} UTC: 2FA code sent for {e(dt['payment'])}")
        elif h["event"] == "payment_approved":
            hum_lines.append(f"{h['timestamp'][11:19]} UTC: <b>{e(dt['approved_by'])} approved {e(dt['payment'])}</b> ({e(dt['approval_factor'])}): "
                             f"paid {money(dt['amount'])} to {e(dt['payee'])}, checking {money(dt['balance_before'])} → {money(dt['balance_after'])}")
        else:
            hum_lines.append(f"{h['timestamp'][11:19]} UTC: {e(h['event'])} {e(json.dumps(dt))}")
    if not hum_lines:
        hum_lines.append("None needed. No payment was prepared on this ticket.")
    t = tickets[tid]
    tier_cls = {1: "tier1", 2: "tier2", 3: "tier3"}[d["tier"]]
    cmp_items = "".join(
        f'<li class="{k}"><b>{"✓ Matches" if k == "match" else "≠ Differs"}:</b> {e(txt).replace("**", "")}</li>'
        for k, txt in COMPARE[tid])
    return f'''  <div class="card actual-filled">
    <h3>Actual</h3>
    <p class="sub">Full run after reset · session <code>{SESSIONS[tid]}</code> · shop date 2026-08-31 · {f["started"][11:19]}–{f["ended"][11:19]} UTC · tokens ${f["token_cost_usd"]:.4f} (gpt-6-luna via Portkey)</p>
    <div class="route"><span class="tier {tier_cls}">Tier {d["tier"]} → {e(NAMES[d["sent_to"]])}</span> Desk triage ran <code>triage_ticket({tid})</code> and got <code>{e(d["known_issue"])}</code>. Route: <b>{" → ".join(e(r) for r in d["route"])}</b>.</div>

    <h4>Agents that worked, what they delegated, and the tools they used</h4>
    <table>
      <tr><th>#</th><th>Agent</th><th>What it did / delegated</th><th>MCP tools used (in order)</th></tr>
      {"".join(rows)}
    </table>

    <h4>Human approvals</h4>
    <div class="gate"><ul>{"".join(f"<li>{x}</li>" for x in hum_lines)}</ul></div>

    <h4>End state (from data/campus_customs_new.db)</h4>
    <div class="end"><ul>
      <li>Ticket {tid}: <b>{e(t["status"])}</b>.</li>
      <li>Outcome: {e(OUTCOME[tid])}</li>
    </ul></div>

    <h4>Expected vs Actual</h4>
    <ul class="compare">{cmp_items}</ul>
  </div>
'''


page = (OUT / "desk_tickets.html").read_text()
css_extra = '''
  .actual-filled { border: 2px solid var(--accent); }
  .compare { list-style: none; padding-left: 0; }
  .compare li { padding: 4px 0 4px 10px; border-left: 4px solid var(--line); margin: 4px 0; }
  .compare li.match { border-left-color: var(--ok); }
  .compare li.differs { border-left-color: var(--warn); }
  .cashtbl td.num, .cashtbl th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .cashtbl tr.total td { border-top: 2px solid var(--ink); font-weight: 700; }
'''
if ".actual-filled" not in page:
    page = page.replace("</style>", css_extra + "</style>", 1)
for tid in (101, 102, 103):
    pat = re.compile(rf'(<section class="tab[^"]*" id="t{tid}">.*?)(  <div class="card actual(?:-filled)?">.*?\n  </div>\n)(</section>)', re.S)
    m = pat.search(page)
    assert m, f"Actual section for {tid} not found"
    page = page[:m.start(2)] + actual_html(tid) + page[m.end(2):]


# ------------------------------------------------------------------ Cash tab
def cash_html() -> str:
    rows = [f'<tr><td>Start</td><td>Checking after <code>POST /api/reset</code> ({e(start["taken_at"])})</td><td></td><td class="num"></td><td class="num">{money(start_balance)}</td></tr>']
    for L in ledger:
        tid = L["ticket_id"]
        if L["payment"]:
            why = (f'{e(L["payment"])}: {"invoice" if L["kind"] == "invoice" else "rent for lease"} {L["ref_id"]} to {e(L["payee"])}. '
                   f'Prepared by Accounting, approved by {e(L["approved_by"])} with {e(L["factor"])} at {e(L["approved_at"][11:19])} UTC. '
                   f'Recorded as <code>payments.id = {L["payments_row_id"]}</code>.')
            what = "Pay"
        else:
            why = "No pay or purchase. The discount reply is a draft, and the 12-unit shortfall wasn't reordered (there's no purchase table, and there was no approval)."
            what = "—"
        rows.append(f'<tr><td>Ticket {tid} resolved</td><td>{why}</td><td>{what}</td><td class="num">{money(L["change"]) if L["change"] else "$0.00"}</td><td class="num">{money(L["balance_after"])}</td></tr>')
    rows.append(f'<tr class="total"><td>End</td><td>Ending checking balance (sum of the changes above)</td><td></td><td class="num">{money(end_balance - start_balance)}</td><td class="num">{money(running)}</td></tr>')
    pay_rows = "".join(f'<tr><td>{p["id"]}</td><td>{e(p["kind"])}</td><td>{p["ref_id"]}</td><td class="num">{money(p["amount"])}</td><td>{e(p["account"])}</td><td>{e(p["paid_at"])}</td><td>{e(p["approved_by"])}</td></tr>' for p in payments_rows)
    return f'''<section class="tab" id="cash">
  <div class="card">
    <h3>Cash</h3>
    <p class="sub">Problem 9 full run. Cash only goes out; revenue isn't modeled. Every number below was read from <code>data/campus_customs_new.db</code> and <code>output/pending_payments.json</code> by <code>scripts/build_problem9_reports.py</code>, which stops with an error if the totals don't reconcile.</p>
    <table class="cashtbl">
      <tr><th>Step</th><th>Why (which pay or purchase)</th><th>Type</th><th class="num">Change</th><th class="num">Checking after</th></tr>
      {"".join(rows)}
    </table>

    <h4>Check against the working database</h4>
    <div class="end"><ul>
      <li><code>cash_accounts</code>: checking = <b>{money(end_balance)}</b> (date {e(cash_rows[0]["date"])}). Itemized ending balance = <b>{money(running)}</b>. <b>They match ✓</b></li>
      <li>{money(start_balance)} − {" − ".join(money(p["amount"]) for p in payments_rows)} = {money(start_balance - sum(p["amount"] for p in payments_rows))} ✓</li>
      <li>Invoice 501 status: <b>{e(invoice_501["status"])}</b>. Lease 1 next_due: <b>{e(lease_1["next_due"])}</b>.</li>
      <li>Every payment had human approval with 2FA (over $50), and the balance never went negative.</li>
    </ul></div>

    <h4><code>payments</code> table (working DB)</h4>
    <table class="cashtbl">
      <tr><th>id</th><th>kind</th><th>ref_id</th><th class="num">amount</th><th>account</th><th>paid_at (shop date)</th><th>approved_by</th></tr>
      {pay_rows}
    </table>
    <p class="sub">Looking ahead: the next rent of $2,400 is due 2026-10-02, and only {money(end_balance)} is left. With no revenue modeled, that rent can't be paid. The pay tool would refuse it.</p>
  </div>
</section>'''


page = re.sub(r'<section class="tab" id="cash">.*?</section>', cash_html(), page, count=1, flags=re.S)
(OUT / "desk_tickets.html").write_text(page)

# ------------------------------------------------------------------ resolved_tickets.json
CONTRIB = {
    101: {
        "it_director": "Took the Tier 2 ticket and delegated to inventory, accounting and customer_service in order. Set the ticket note.",
        "inventory": "Confirmed 0 on hand (short 1), Bulldog blocked by open invoice 501, and earliest arrival 2026-09-05 if paid.",
        "accounting": "Checked cash ($3,400; $160 after all obligations), previewed and prepared payment P-0003 for $840 (not paid by the agent).",
        "customer_service": "Saved a customer update draft for Tauhid Zaman (not sent).",
    },
    102: {
        "facilities": "Tier 1 owner: checked the notice against lease 1 ($2,400 due 2026-09-02, not overdue) and handed off to accounting.",
        "accounting": "Previewed and prepared rent payment P-0004 for $2,400 (not paid by the agent), and set the ticket to waiting_on_approval.",
    },
    103: {
        "it_director": "Took the Tier 2 ticket and delegated to inventory, then customer_service. Set the ticket note.",
        "inventory": "Confirmed 8 on hand, short 12, and the Bulldog block (earliest 2026-09-05 if unblocked). Rechecked when asked by customer_service.",
        "customer_service": "Quoted the bulk order and saved a no-discount offer draft ($58 each, $1,160) for the Yale AI Club (not sent).",
    },
}
resolved = []
for tid in (101, 102, 103):
    f = FACTS[tid]
    L = next(x for x in ledger if x["ticket_id"] == tid)
    approvals = []
    if L["payment"]:
        approvals.append({"payment": L["payment"], "kind": L["kind"], "ref_id": L["ref_id"], "amount": -L["change"],
                          "payee": L["payee"], "approved_by": L["approved_by"], "factor": L["factor"],
                          "approved_at": L["approved_at"], "payments_row_id": L["payments_row_id"]})
    resolved.append({
        "id": tid,
        "subject": tickets[tid]["subject"],
        "requester": tickets[tid]["requester"],
        "final_status": tickets[tid]["status"],
        "session_id": SESSIONS[tid],
        "routing": {"known_issue": f["dispatch"]["known_issue"], "tier": f["dispatch"]["tier"],
                    "sent_to": f["dispatch"]["sent_to"], "route": f["dispatch"]["route"]},
        "outcome": OUTCOME[tid],
        "agents": [
            {"agent": a["agent"], "asked_by": a["asked_by"], "contribution": CONTRIB[tid].get(a["agent"], ""),
             "delegated_to": [d["to"] for d in a["delegated"]], "tools_used": a["tools"],
             "drafts_saved": (a["report"] or {}).get("drafts_saved", [])}
            for a in f["agents"].values()
        ],
        "human_approvals": approvals,
        "cash_change": L["change"],
        "checking_after": L["balance_after"],
        "token_cost_usd": f["token_cost_usd"],
    })
(OUT / "resolved_tickets.json").write_text(json.dumps({
    "run": "Problem 9 full run after reset",
    "shop_date": "2026-08-31",
    "starting_checking": start_balance,
    "ending_checking": end_balance,
    "ending_checking_matches_cash_accounts": abs(running - end_balance) < 0.005,
    "tickets": resolved,
}, indent=2) + "\n")

# ------------------------------------------------------------------ resolved_board.html
shots = "".join(f'''
  <section>
    <h2>Ticket {tid}: {e(tickets[tid]["subject"])} <span class="state">✓ {e(tickets[tid]["status"])}</span></h2>
    <p>{e(OUTCOME[tid])}</p>
    <p class="meta">Tier {FACTS[tid]["dispatch"]["tier"]} → {e(NAMES[FACTS[tid]["dispatch"]["sent_to"]])} · route {" → ".join(FACTS[tid]["dispatch"]["route"])} · session {SESSIONS[tid]}{" · approved " + e(PAYMENT_FOR[tid]) if PAYMENT_FOR[tid] else " · no payment"}</p>
    <a href="screenshots/ticket_{tid}_resolved.jpg"><img src="screenshots/ticket_{tid}_resolved.jpg" alt="React board with ticket {tid} selected and resolved"></a>
  </section>''' for tid in (101, 102, 103))
(OUT / "resolved_board.html").write_text(f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Campus Customs — resolved board</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; background: #fff; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; color: #1a1a1a; }}
  header {{ padding: 16px 28px; border-bottom: 1px solid #ccc; }}
  h1 {{ font-size: 18px; margin: 0 0 4px; }}
  header p {{ margin: 0; color: #555; }}
  main {{ max-width: 1240px; margin: 0 auto; padding: 8px 28px 40px; }}
  section {{ border-top: 1px solid #1a1a1a; margin-top: 24px; padding-top: 10px; }}
  h2 {{ font-size: 16px; margin: 0 0 4px; }}
  .state {{ font-weight: 700; margin-left: 8px; }}
  .meta {{ color: #555; font-size: 12px; margin: 2px 0 8px; font-family: ui-monospace, Menlo, monospace; }}
  img {{ width: 100%; border: 1px solid #ccc; }}
</style></head><body>
<header>
  <h1>Campus Customs: React board with each ticket resolved (Problem 9)</h1>
  <p>Screenshots of the live board (http://localhost:5173) after the full run. Checking {money(start_balance)} → <b>{money(end_balance)}</b>; 3 of 3 tickets resolved. Click a screenshot to open it full size.</p>
</header>
<main>{shots}
</main></body></html>
''')
print(f"OK: start {money(start_balance)} -> end {money(running)} == cash_accounts {money(end_balance)}; all tickets resolved")
