# Campus Customs MCP server

**What it's for:** this is the only path to shop data. Every HW5 agent (Boss, IT Director, Inventory, Accounting, Facilities, Customer Service), the desk dispatcher, the FastAPI backend (`backend/main.py`), and the vibe coder get their tools here. Nobody queries the database directly. The tools return only what's in the database and give an `error` if a row doesn't exist.

**Database:** `data/campus_customs_new.db`, the working copy. The original `data/campus_customs.db` is never touched. Reset the working copy with `./reset_db.sh`, or `python3 -m backend.run` resets it automatically.

**Built with:** FastMCP (`fastmcp-slim[server]` 4.0.10). The vibe coder starts it through `.mcp.json`. The agents start it from `backend/run.py`. You can also run it by hand with `python3 mcp_server/server.py` (stdio).

## Tools (16)

| Tool | Inputs | Tables | What it does |
|---|---|---|---|
| `list_open_tickets` | none | tickets | Lists the tickets that aren't resolved |
| `list_tickets` | none | tickets | Every ticket (open and resolved) with `state` = open or resolved. Used by the dashboard API |
| `get_ticket` | `ticket_id` | tickets | One ticket with its links (sku, size, qty, lease_id, invoice_id) |
| `update_ticket` | `ticket_id`, `status`, `note` | tickets, desk | **Writes.** Sets the status and adds a dated note |
| `check_stock_and_price` | `sku`, `size`, `qty_requested` | inventory, pricing | Qty on hand, shortfall, unit cost, list price |
| `list_vendors` | none | vendors, invoices | Each vendor's specialty, lead days, open invoices, and whether it can ship |
| `check_vendor_can_ship` | `vendor_id` | vendors, invoices, desk | Invoices blocking shipment, days overdue, and earliest arrival |
| `quote_bulk_discount` | `sku`, `size`, `qty`, `discount_pct` | pricing, inventory | Discounted price, margin, the largest discount without a loss, and the shortfall. Approves nothing |
| `check_rent_due` | `lease_id` | leases, desk, cash_accounts | Rent, due date, days until due or overdue, and whether cash covers it |
| `get_cash_position` | none | cash_accounts, invoices, vendors, leases, desk | Cash on hand, every obligation, and the cash left after all of them |
| `preview_payment` | `kind`, `ref_id`, `account` | invoices or leases, cash_accounts, desk | Amount, payee, balance before and after, whether 2FA is needed. Moves no money |
| `pay_invoice` | `invoice_id`, `account`, plus the approval fields | invoices, cash_accounts, payments, desk | **Writes.** Pays an open invoice |
| `pay_rent` | `lease_id`, `account`, plus the approval fields | leases, cash_accounts, payments, desk | **Writes.** Pays one month of rent and moves `next_due` forward one month |
| `list_known_issues` | none | none | The known-issue playbook (`known_issues.py`): routine patterns, tier, staff route, known solution |
| `triage_ticket` | `ticket_id` | tickets, inventory, invoices, vendors, leases, cash_accounts, desk | Matches a ticket to a known issue using live data. Returns the **tier** (1 = staff directly, 2 = IT Director, 3 = Boss), the minimum route, and escalation reasons |
| `draft_message` | `ticket_id`, `recipient`, `subject`, `body` | tickets, desk | Saves a draft to `output/drafts/`. **Never sent** |

## Payment safety
- **Human approval, with 2FA over $50:** `pay_invoice` and `pay_rent` only work with a human-approval signature (`approval.py`) from that run's approval step. Payments over $50 also need the human's two-factor code.
- **No negative balances:** if there isn't enough cash, the pay tool refuses.
- **Records:** every payment adds a `payments` row, marks the invoice paid or moves the lease due date, and lowers `cash_accounts.balance`.
- **Vibe coder:** without the run's approval secret, every payment is refused.
- **Dashboard:** in the API (`backend/main.py`), agents only *prepare* payments. The pay tool runs only from `POST /api/payments/{id}/approve`, after a human clicks Approve, with 2FA over $50.
