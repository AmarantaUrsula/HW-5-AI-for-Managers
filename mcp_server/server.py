"""Campus Customs MCP server (FastMCP).

Every HW5 agent gets its tools from this server. All tools read and write the
working copy data/campus_customs_new.db, never the original. Tools only report
what is in the database. If a row is missing, they return an error instead of
guessing.
"""

import calendar
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
from approval import TWO_FACTOR_THRESHOLD_USD, payment_message, verify
from known_issues import KNOWN_ISSUES, TIER_OWNER, UNKNOWN_ISSUE

HW5_DIR = Path(__file__).resolve().parent.parent
DB_PATH = HW5_DIR / "data" / "campus_customs_new.db"
DRAFTS_DIR = HW5_DIR / "output" / "drafts"
TICKET_STATUSES = {
    "open", "in_progress", "waiting_on_vendor", "waiting_on_approval",
    "waiting_on_customer", "resolved",
}

mcp = FastMCP("campus-customs")


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _today(conn: sqlite3.Connection) -> date:
    """Shop 'today' comes from desk.date_today, not the real calendar."""
    row = conn.execute("SELECT date_today FROM desk").fetchone()
    return date.fromisoformat(row["date_today"])


@mcp.tool
def check_stock_and_price(sku: str, size: str, qty_requested: int) -> dict:
    """Check whether an order for a SKU and size can be filled from stock, and its pricing.

    Reads inventory and pricing. Returns qty on hand, the shortfall against
    qty_requested, unit cost (the floor for any discount), and list price.
    """
    with _connect() as conn:
        item = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()
        if item is None:
            return {"error": f"No inventory row for sku={sku!r} size={size!r}."}
        price = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
        if price is None:
            return {"error": f"No pricing row for sku={sku!r}."}

    on_hand = item["qty"]
    return {
        "sku": item["sku"],
        "name": item["name"],
        "size": item["size"],
        "location": item["location"],
        "qty_requested": qty_requested,
        "qty_on_hand": on_hand,
        "can_fill_from_stock": on_hand >= qty_requested,
        "shortfall": max(qty_requested - on_hand, 0),
        "unit_cost": price["unit_cost"],
        "list_price": price["list_price"],
        "list_total": round(price["list_price"] * qty_requested, 2),
        "min_unit_price_no_loss": price["unit_cost"],
    }


@mcp.tool
def check_vendor_can_ship(vendor_id: int) -> dict:
    """Check whether a vendor will ship new product, and when it would arrive.

    Reads vendors, invoices, and desk. A vendor with any open (unpaid) invoice
    will not ship. Overdue = due_date before desk.date_today. Earliest arrival
    = today + vendors.lead_days, which only applies once the vendor can ship.
    """
    with _connect() as conn:
        today = _today(conn)
        vendor = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()
        if vendor is None:
            return {"error": f"No vendor with id={vendor_id}."}
        open_invoices = conn.execute(
            "SELECT id, amount, due_date, description FROM invoices "
            "WHERE vendor_id = ? AND status = 'open' ORDER BY due_date",
            (vendor_id,),
        ).fetchall()

    invoices = [
        {
            "invoice_id": inv["id"],
            "amount": inv["amount"],
            "due_date": inv["due_date"],
            "description": inv["description"],
            "days_overdue": max((today - date.fromisoformat(inv["due_date"])).days, 0),
            "overdue": date.fromisoformat(inv["due_date"]) < today,
        }
        for inv in open_invoices
    ]
    can_ship = not invoices
    return {
        "today": today.isoformat(),
        "vendor_id": vendor["id"],
        "vendor_name": vendor["name"],
        "specialty": vendor["specialty"],
        "lead_days": vendor["lead_days"],
        "can_ship": can_ship,
        "blocking_open_invoices": invoices,
        "amount_to_unblock": round(sum(i["amount"] for i in invoices), 2),
        "earliest_arrival_if_ordered_today": (
            (today + timedelta(days=vendor["lead_days"])).isoformat() if can_ship else None
        ),
        "earliest_arrival_if_unblocked_today": (
            today + timedelta(days=vendor["lead_days"])
        ).isoformat(),
    }


@mcp.tool
def check_rent_due(lease_id: int) -> dict:
    """Check a lease's rent: amount, due date, days until due or overdue, and whether cash covers it.

    Reads leases, desk, and cash_accounts. This tool does not pay anything.
    Payments need human approval.
    """
    with _connect() as conn:
        today = _today(conn)
        lease = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if lease is None:
            return {"error": f"No lease with id={lease_id}."}
        accounts = conn.execute("SELECT name, balance, date FROM cash_accounts").fetchall()

    due = date.fromisoformat(lease["next_due"])
    rent = lease["monthly_rent"]
    return {
        "today": today.isoformat(),
        "lease_id": lease["id"],
        "space_name": lease["space_name"],
        "landlord": lease["landlord"],
        "monthly_rent": rent,
        "next_due": lease["next_due"],
        "days_until_due": (due - today).days,
        "overdue": due < today,
        "cash_accounts": [
            {
                "account": a["name"],
                "balance": a["balance"],
                "can_cover_rent": a["balance"] >= rent,
                "balance_after_rent": round(a["balance"] - rent, 2),
            }
            for a in accounts
        ],
    }


# ---------------------------------------------------------------- tickets

@mcp.tool
def list_open_tickets() -> dict:
    """List every ticket that is not resolved, oldest first.

    Reads tickets. This is the agents' work queue.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, type, requester, subject, status, created_at FROM tickets "
            "WHERE status != 'resolved' ORDER BY created_at"
        ).fetchall()
    return {"open_tickets": [dict(r) for r in rows], "count": len(rows)}


@mcp.tool
def list_tickets() -> dict:
    """List every ticket (open and resolved) with its type, requester, subject, and status.

    Reads tickets. state is 'resolved' when status = 'resolved', and 'open' for every other status.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, type, requester, subject, sku, size, qty, lease_id, invoice_id, status, notes, created_at "
            "FROM tickets ORDER BY id"
        ).fetchall()
    tickets = [dict(r) | {"state": "resolved" if r["status"] == "resolved" else "open"} for r in rows]
    return {"tickets": tickets, "count": len(tickets),
            "open": sum(t["state"] == "open" for t in tickets),
            "resolved": sum(t["state"] == "resolved" for t in tickets)}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Get one ticket with every field, including its links (sku, size, qty, lease_id, invoice_id).

    Reads tickets.
    """
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        return {"error": f"No ticket with id={ticket_id}."}
    return dict(row)


@mcp.tool
def update_ticket(ticket_id: int, status: str, note: str) -> dict:
    """Set a ticket's status and append a dated note explaining why.

    Writes tickets. Allowed statuses: open, in_progress, waiting_on_vendor,
    waiting_on_approval, waiting_on_customer, resolved.
    """
    if status not in TICKET_STATUSES:
        return {"error": f"Status must be one of {sorted(TICKET_STATUSES)}."}
    if not note.strip():
        return {"error": "A note explaining the change is required."}
    with _connect() as conn:
        today = _today(conn)
        row = conn.execute("SELECT status, notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"error": f"No ticket with id={ticket_id}."}
        notes = ((row["notes"] or "") + f"\n[{today.isoformat()}] {status}: {note.strip()}").strip()
        conn.execute("UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, notes, ticket_id))
        conn.commit()
    return {"ticket_id": ticket_id, "old_status": row["status"], "new_status": status, "notes": notes}


# ---------------------------------------------------------------- vendors and pricing

@mcp.tool
def list_vendors() -> dict:
    """List every vendor with its specialty, lead days, and open (unpaid) invoice total.

    Reads vendors and invoices. Use the specialty to pick which vendor restocks
    an item. A vendor with open invoices will not ship.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT v.id, v.name, v.specialty, v.lead_days, "
            "COUNT(i.id) AS open_invoices, COALESCE(SUM(i.amount), 0) AS open_amount "
            "FROM vendors v LEFT JOIN invoices i ON i.vendor_id = v.id AND i.status = 'open' "
            "GROUP BY v.id ORDER BY v.id"
        ).fetchall()
    return {"vendors": [dict(r) | {"can_ship": r["open_invoices"] == 0} for r in rows]}


@mcp.tool
def quote_bulk_discount(sku: str, size: str, qty: int, discount_pct: float) -> dict:
    """Price a bulk order at a given discount and check it stays above unit cost.

    Reads pricing and inventory. Doesn't approve or send anything. It only
    shows the numbers so a human can decide.
    """
    if qty <= 0 or not 0 <= discount_pct < 100:
        return {"error": "qty must be > 0 and discount_pct must be between 0 and 100."}
    with _connect() as conn:
        price = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
        item = conn.execute(
            "SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
    if price is None or item is None:
        return {"error": f"No pricing/inventory for sku={sku!r} size={size!r}."}
    unit_price = round(price["list_price"] * (1 - discount_pct / 100), 2)
    cost = price["unit_cost"]
    return {
        "sku": sku, "size": size, "qty": qty, "discount_pct": discount_pct,
        "list_price": price["list_price"], "unit_cost": cost,
        "discounted_unit_price": unit_price,
        "order_total": round(unit_price * qty, 2),
        "margin_per_unit": round(unit_price - cost, 2),
        "total_margin": round((unit_price - cost) * qty, 2),
        "above_cost": unit_price > cost,
        "max_discount_pct_without_loss": round((1 - cost / price["list_price"]) * 100, 2),
        "qty_on_hand": item["qty"],
        "shortfall": max(qty - item["qty"], 0),
    }


# ---------------------------------------------------------------- cash and payments

@mcp.tool
def get_cash_position() -> dict:
    """Show cash on hand and every money obligation (open invoices and rent), with what is left after.

    Reads cash_accounts, invoices, leases, desk. Cash only goes out, because
    revenue isn't modeled.
    """
    with _connect() as conn:
        today = _today(conn)
        accounts = [dict(a) for a in conn.execute("SELECT name, balance, date FROM cash_accounts")]
        invoices = conn.execute(
            "SELECT i.id, v.name AS vendor, i.amount, i.due_date, i.description "
            "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.status = 'open' ORDER BY i.due_date"
        ).fetchall()
        leases = conn.execute("SELECT id, space_name, landlord, monthly_rent, next_due FROM leases").fetchall()
    obligations = [
        {"kind": "invoice", "ref_id": i["id"], "payee": i["vendor"], "amount": i["amount"],
         "due": i["due_date"], "overdue": date.fromisoformat(i["due_date"]) < today,
         "description": i["description"]}
        for i in invoices
    ] + [
        {"kind": "rent", "ref_id": l["id"], "payee": l["landlord"], "amount": l["monthly_rent"],
         "due": l["next_due"], "overdue": date.fromisoformat(l["next_due"]) < today,
         "description": f"Rent for {l['space_name']}"}
        for l in leases
    ]
    obligations.sort(key=lambda o: o["due"])
    total_cash = sum(a["balance"] for a in accounts)
    total_due = sum(o["amount"] for o in obligations)
    return {
        "today": today.isoformat(),
        "accounts": accounts,
        "total_cash": round(total_cash, 2),
        "obligations": obligations,
        "total_obligations": round(total_due, 2),
        "cash_after_all_obligations": round(total_cash - total_due, 2),
    }


def _payment_target(conn: sqlite3.Connection, kind: str, ref_id: int) -> dict | None:
    if kind == "invoice":
        r = conn.execute(
            "SELECT i.id, i.amount, i.due_date, i.status, v.name AS payee FROM invoices i "
            "JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?", (ref_id,)
        ).fetchone()
        return r and {"amount": r["amount"], "due": r["due_date"], "payee": r["payee"],
                      "payable": r["status"] == "open", "status": r["status"]}
    if kind == "rent":
        r = conn.execute(
            "SELECT id, monthly_rent, next_due, landlord FROM leases WHERE id = ?", (ref_id,)
        ).fetchone()
        return r and {"amount": r["monthly_rent"], "due": r["next_due"], "payee": r["landlord"],
                      "payable": True, "status": "due"}
    return None


@mcp.tool
def preview_payment(kind: str, ref_id: int, account: str = "checking") -> dict:
    """Preview a payment before asking a human: amount, payee, cash before and after, and whether 2FA is required.

    kind is 'invoice' (ref_id = invoices.id) or 'rent' (ref_id = leases.id).
    Reads invoices/vendors or leases, cash_accounts, and desk. Moves no money.
    """
    with _connect() as conn:
        today = _today(conn)
        target = _payment_target(conn, kind, ref_id)
        acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    if target is None:
        return {"error": f"No {kind!r} with id={ref_id} (kind must be 'invoice' or 'rent')."}
    if acct is None:
        return {"error": f"No cash account named {account!r}."}
    amount, balance = target["amount"], acct["balance"]
    return {
        "today": today.isoformat(), "kind": kind, "ref_id": ref_id, "payee": target["payee"],
        "amount": amount, "due": target["due"], "status": target["status"],
        "overdue": date.fromisoformat(target["due"]) < today,
        "account": account, "balance_before": balance,
        "balance_after": round(balance - amount, 2),
        "enough_cash": balance >= amount,
        "payable": target["payable"] and balance >= amount,
        "requires_human_approval": True,
        "requires_two_factor": amount > TWO_FACTOR_THRESHOLD_USD,
    }


def _add_one_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _pay(kind: str, ref_id: int, account: str, approved_by: str,
         approval_factor: str, approval_token: str) -> dict:
    secret = os.environ.get("HW5_APPROVAL_SECRET", "")
    if not secret:
        return {"refused": True, "reason": "No approval channel is configured, so payments are disabled in this session."}
    with _connect() as conn:
        today = _today(conn)
        target = _payment_target(conn, kind, ref_id)
        acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if target is None or acct is None:
            return {"refused": True, "reason": f"Unknown {kind} {ref_id} or account {account!r}."}
        amount, balance = target["amount"], acct["balance"]
        if not target["payable"]:
            return {"refused": True, "reason": f"{kind} {ref_id} is not payable (status={target['status']})."}
        if amount > TWO_FACTOR_THRESHOLD_USD and approval_factor != "2fa":
            return {"refused": True, "reason": f"${amount:.2f} is over ${TWO_FACTOR_THRESHOLD_USD:.2f}; human two-factor approval required."}
        msg = payment_message(kind, ref_id, amount, target["due"], account, approved_by, approval_factor)
        if not approved_by.strip() or not verify(secret, msg, approval_token):
            return {"refused": True, "reason": "No valid human approval for this exact payment."}
        if balance < amount:
            return {"refused": True, "reason": f"Not enough cash: {account} has ${balance:.2f}, payment is ${amount:.2f}. No negative balances."}

        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (kind, ref_id, amount, account, today.isoformat(), approved_by),
        )
        if kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
            updated = {"invoice_status": "paid"}
        else:
            new_due = _add_one_month(date.fromisoformat(target["due"])).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, ref_id))
            updated = {"lease_next_due": new_due}
        new_balance = round(balance - amount, 2)
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
                     (new_balance, today.isoformat(), account))
        conn.commit()
    return {
        "paid": True, "payment_id": cur.lastrowid, "kind": kind, "ref_id": ref_id,
        "payee": target["payee"], "amount": amount, "account": account,
        "paid_at": today.isoformat(), "approved_by": approved_by, "approval_factor": approval_factor,
        "balance_before": balance, "balance_after": new_balance, **updated,
    }


@mcp.tool
def pay_invoice(invoice_id: int, account: str = "checking", approved_by: str = "",
                approval_factor: str = "", approval_token: str = "") -> dict:
    """Pay an open vendor invoice. Only works after a human approves it, with 2FA if over $50.

    Writes payments, invoices (status -> paid), and cash_accounts (balance down).
    Refuses if there isn't enough cash, because balances can't go negative. Leave
    approved_by, approval_factor, and approval_token blank. The human-approval
    step fills them in.
    """
    return _pay("invoice", invoice_id, account, approved_by, approval_factor, approval_token)


@mcp.tool
def pay_rent(lease_id: int, account: str = "checking", approved_by: str = "",
             approval_factor: str = "", approval_token: str = "") -> dict:
    """Pay one month of rent on a lease. Only works after a human approves it, with 2FA if over $50.

    Writes payments, leases (next_due moves forward one month), and
    cash_accounts (balance down). Refuses if there isn't enough cash. Leave the
    approval fields blank. The human-approval step fills them in.
    """
    return _pay("rent", lease_id, account, approved_by, approval_factor, approval_token)


# ---------------------------------------------------------------- drafts (never sent)

@mcp.tool
def draft_message(ticket_id: int, recipient: str, subject: str, body: str) -> dict:
    """Save a DRAFT message about a ticket to output/drafts/. It is never sent.

    Reads tickets to confirm the ticket exists. No email, call, or text goes to
    a customer, vendor, or landlord. A human must review and send it.
    """
    with _connect() as conn:
        today = _today(conn)
        ticket = conn.execute("SELECT id, requester FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if ticket is None:
        return {"error": f"No ticket with id={ticket_id}."}
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", recipient.lower()).strip("_") or "recipient"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = DRAFTS_DIR / f"ticket_{ticket_id}_{slug}_{stamp}.md"
    path.write_text(
        f"<!-- DRAFT — NOT SENT. Human review required before any contact. -->\n"
        f"To: {recipient}\nTicket: {ticket_id}\nShop date: {today.isoformat()}\n"
        f"Subject: {subject}\n\n{body}\n",
        encoding="utf-8",
    )
    return {"draft_saved": str(path.relative_to(HW5_DIR)), "sent": False, "ticket_id": ticket_id,
            "recipient": recipient}


# ---------------------------------------------------------------- triage (tiered routing)

@mcp.tool
def list_known_issues() -> dict:
    """List the known-issue playbook: routine ticket patterns, their tier, which staff handle them, and the known solution.

    Reads no tables. These are routing rules, not shop facts.
    """
    return {"tiers": {"1": "staff (direct)", "2": "it_director", "3": "boss"},
            "known_issues": [{"id": k, **v} for k, v in KNOWN_ISSUES.items()]}


@mcp.tool
def triage_ticket(ticket_id: int) -> dict:
    """Match a ticket to a known issue using live database facts. Returns its tier, the minimum staff route, and any escalation reasons.

    Reads tickets, inventory, invoices, vendors, leases, cash_accounts, desk.
    Tier 1 goes straight to the listed staff, tier 2 to the IT Director, tier 3 to the Boss.
    """
    with _connect() as conn:
        today = _today(conn)
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"error": f"No ticket with id={ticket_id}."}
        cash = conn.execute("SELECT COALESCE(SUM(balance), 0) AS c FROM cash_accounts").fetchone()["c"]
        owed = conn.execute(
            "SELECT (SELECT COALESCE(SUM(amount),0) FROM invoices WHERE status='open') + "
            "(SELECT COALESCE(SUM(monthly_rent),0) FROM leases) AS o").fetchone()["o"]
        facts: dict = {"today": today.isoformat(), "ticket_type": t["type"], "total_cash": cash,
                       "total_obligations": owed, "cash_after_all_obligations": round(cash - owed, 2)}
        reasons: list[str] = []
        key = None

        def stock_short() -> int | None:
            row = conn.execute("SELECT qty FROM inventory WHERE sku = ? AND size = ?",
                               (t["sku"], t["size"])).fetchone()
            if row is None:
                return None
            facts.update(qty_requested=t["qty"], qty_on_hand=row["qty"])
            return max((t["qty"] or 0) - row["qty"], 0)

        if t["type"] == "customer_order":
            short = stock_short()
            if short is None:
                reasons.append("sku/size not found in inventory")
            elif short == 0:
                key = "KI-ORDER-INSTOCK"
            else:
                facts["shortfall"] = short
                inv = t["invoice_id"] and conn.execute(
                    "SELECT i.id, i.amount, i.due_date, i.status, v.name FROM invoices i "
                    "JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?", (t["invoice_id"],)).fetchone()
                if inv and inv["status"] == "open":
                    key = "KI-ORDER-VENDOR-BLOCKED"
                    facts.update(blocking_invoice=inv["id"], invoice_amount=inv["amount"],
                                 invoice_due=inv["due_date"], vendor=inv["name"])
                    reasons.append(f"{inv['name']} blocked by open invoice {inv['id']} (${inv['amount']:.2f}, due {inv['due_date']})")
                    if inv["amount"] > TWO_FACTOR_THRESHOLD_USD:
                        reasons.append(f"unblocking needs a ${inv['amount']:.2f} payment, so human 2FA is required")
                else:
                    key = "KI-ORDER-RESTOCK"
        elif t["type"] == "rent_notice":
            lease = t["lease_id"] and conn.execute(
                "SELECT monthly_rent, next_due FROM leases WHERE id = ?", (t["lease_id"],)).fetchone()
            if not lease:
                reasons.append("no lease linked to this notice")
            else:
                due = date.fromisoformat(lease["next_due"])
                facts.update(rent=lease["monthly_rent"], next_due=lease["next_due"], days_until_due=(due - today).days)
                key = "KI-RENT-OVERDUE" if due < today else "KI-RENT-ROUTINE"
                if due < today:
                    reasons.append("rent is overdue")
        elif t["type"] == "price_override":
            short = stock_short()
            if short is None:
                reasons.append("sku/size not found in inventory")
            else:
                key = "KI-DISCOUNT-INSTOCK" if short == 0 else "KI-DISCOUNT-SHORTFALL"
                if short:
                    facts["shortfall"] = short
                    reasons.append(f"requested {t['qty']} but only {facts['qty_on_hand']} on hand (short {short})")
        else:
            reasons.append(f"no known issue for ticket type {t['type']!r}")

    issue = {"id": key, **KNOWN_ISSUES[key]} if key else dict(UNKNOWN_ISSUE)
    tier = issue["tier"]
    if "accounting" in issue["route"] and facts["cash_after_all_obligations"] < 0:
        tier = 3
        reasons.append(f"cash conflict: obligations ${owed:.2f} exceed cash ${cash:.2f}")
    return {
        "ticket_id": ticket_id,
        "known_issue": issue["id"], "title": issue["title"],
        "tier": tier, "handled_by": TIER_OWNER[tier],
        "route": issue["route"],
        "first_owner": issue["route"][0] if tier == 1 and issue["route"] else TIER_OWNER[tier],
        "known_solution": issue["known_solution"], "tools": issue["tools"],
        "escalation_reasons": reasons, "facts": facts,
    }


if __name__ == "__main__":
    mcp.run()
