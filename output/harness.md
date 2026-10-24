# Campus Customs agent harness (final, Problem 9)

This is the reference guide for the Campus Customs agent system. It covers the **tables**, the **MCP tools**, the **agents** (the five roles plus the IT Director), the **API routes**, the **dashboard**, and the **safety rules**. It ends with the results of the full Problem 9 run.

## Contents
1. [How to run it](#1-how-to-run-it)
2. [Databases and tables](#2-databases-and-tables)
3. [MCP tools](#3-mcp-tools-mcp_serverserverpy)
4. [Agents](#4-agents-backend)
5. [Tiered workflow](#5-tiered-workflow-staff-first-directors-only-when-needed)
6. [Audit trail](#6-audit-trail-outputaudit_trailjson)
7. [API routes](#7-api-routes-backendmainpy-at-httplocalhost8000)
8. [Dashboard](#8-dashboard-frontend-at-httplocalhost5173)
9. [Safety rules](#9-safety-rules)
10. [Problem 9 results](#10-problem-9-results-full-run-after-reset)
11. [File map](#11-file-map)

---

## 1. How to run it

```bash
cd hw5/backend && uvicorn main:app --reload --port 8000     # API (starts the MCP server itself)
cd hw5/frontend && npm run dev                               # board at http://localhost:5173
```

- **Fresh run:** click **Reset database** on the board, which calls `POST /api/reset`. You can also run `./reset_db.sh` from the terminal.
- **Terminal-only run:** `python3 -m backend.run`. It resets the DB itself and asks for payment approvals in the terminal.
- **Model:** every AI call uses **gpt-6-luna through Portkey** with `PORTKEY_API_KEY`, which lives in `AI for managers/.env`. `llm.py` refuses any other model.

## 2. Databases and tables

| File | Role |
|---|---|
| `data/campus_customs.db` | **Original.** Never modified. |
| `data/campus_customs_new.db` | **Working copy.** All updates go here. It's reset from the original before every full run. |

| Table | Fields | Why it matters to the agents |
|---|---|---|
| `desk` | `date_today`, `notes` | `date_today` (**2026-08-31**) is "today": it decides what's overdue and dates every payment. |
| `inventory` | `sku`, `name`, `size`, `qty`, `location` (PK `sku`+`size`) | Whether an order can be filled from stock, and the shortfall. |
| `pricing` | `sku`, `unit_cost`, `list_price` | Prices orders, and sets the floor for any discount (`unit_cost`). |
| `vendors` | `id`, `name`, `specialty`, `lead_days` | Which vendor restocks an item, and how many days it takes. |
| `leases` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | Rent, the biggest fixed obligation. `next_due` moves forward one month when rent is paid. |
| `cash_accounts` | `name`, `balance`, `date` | The only cash (checking). It never goes up (no revenue is modeled) and never goes negative. |
| `payments` | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | Every approved payment, with the human approver. |
| `invoices` | `id`, `vendor_id`→`vendors`, `amount`, `due_date`, `status`, `description` | An `open` invoice blocks that vendor from shipping. Overdue means `due_date` < today. |
| `tickets` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`→`leases`, `invoice_id`→`invoices`, `status`, `notes`, `created_at` | The work queue. The links point to the rows each ticket depends on. |

How the three tickets link to other tables:

```
101 customer_order  ── sku CC-TEE-WHITE/S ──► inventory (0), pricing ($8/$28) ── invoice_id 501 ──► invoices ($840, open) ──► vendors 1 Bulldog (5 days)
102 rent_notice     ── lease_id 1 ─────────► leases ($2,400, next_due 2026-09-02)
103 price_override  ── sku CC-HOOD-NAVY/M ─► inventory (8 of 20), pricing ($22/$58); restock would come from Bulldog
payments.kind + ref_id ──► the invoice or lease that was paid
```

## 3. MCP tools (`mcp_server/server.py`)

All shop data goes through this FastMCP server, which uses `data/campus_customs_new.db`. The agents, the API, the approval step and the vibe coder (through `.mcp.json`) all use it. There's no second path. Tools return only database values, and an `error` if a row is missing.

| # | Tool | Tables | Reads / writes | Main ticket |
|---|---|---|---|---|
| 1 | `check_stock_and_price` | inventory, pricing | read | **103**: 8 of 20 hoodies on hand. The $22 cost is the floor for a discount. |
| 2 | `check_vendor_can_ship` | vendors, invoices, desk | read | **101**: Bulldog is blocked by open invoice 501. Earliest arrival 2026-09-05 once paid. |
| 3 | `check_rent_due` | leases, desk, cash_accounts | read | **102**: $2,400 due 2026-09-02 (in 2 days), and checking covers it. |
| 4 | `list_open_tickets` | tickets | read | The queue (dispatcher) |
| 5 | `list_tickets` | tickets | read (with `state` open or resolved) | The board's ticket list |
| 6 | `get_ticket` | tickets | read | All |
| 7 | `update_ticket` | tickets, desk | **writes** the status and a dated note | All |
| 8 | `list_vendors` | vendors, invoices | read | 101 and 103: pick the vendor by specialty |
| 9 | `quote_bulk_discount` | pricing, inventory | read | 103: price, margin, largest discount without a loss |
| 10 | `get_cash_position` | cash_accounts, invoices, vendors, leases, desk | read | 101 and 102: cash vs everything owed |
| 11 | `preview_payment` | invoices, vendors, leases, cash_accounts, desk | read | Shows the human the exact payment |
| 12 | `pay_invoice` | invoices, vendors, cash_accounts, payments, desk | **writes** payments, invoices.status=paid, cash_accounts.balance | 101 (only with a signed human approval) |
| 13 | `pay_rent` | leases, cash_accounts, payments, desk | **writes** payments, leases.next_due +1 month, cash_accounts.balance | 102 (only with a signed human approval) |
| 14 | `draft_message` | tickets, desk | writes a **file** to `output/drafts/` and **never sends** it | 101 and 103 replies |
| 15 | `list_known_issues` | none (playbook `known_issues.py`) | read | Tier routing |
| 16 | `triage_ticket` | tickets, inventory, invoices, vendors, leases, cash_accounts, desk | read | Tier routing for every ticket |

## 4. Agents (`backend/`)

The agents are built with **PydanticAI**. Each role has a code file in `backend/agents/` and a prompt in `backend/prompts/`, and the data types are in `backend/models.py`.
- **Tools:** each agent sees only its role's MCP tools, plus `delegate(to, request)`.
- **Delegation:** any agent can delegate to any other (full connectivity), up to 3 levels deep. On a ticket, staff can only pull in staff who are on that ticket's route.

The five roles the assignment asked for:

| Agent | Tier | Job | MCP tools |
|---|---|---|---|
| **Boss** | 3 | Takes escalations only: cash conflicts (obligations > cash) and priority calls. Sets priorities, and Accounting asks the human. | list_open_tickets, get_ticket, triage_ticket, list_known_issues, get_cash_position, update_ticket |
| **Inventory** | staff | Stock, shortfalls, the restock vendor, whether it can ship, arrival dates. | get_ticket, check_stock_and_price, list_vendors, check_vendor_can_ship, update_ticket |
| **Accounting** | staff | Cash position. The **only** role with pay tools, and it only *prepares* payments. | get_ticket, get_cash_position, preview_payment, pay_invoice, pay_rent, check_vendor_can_ship, quote_bulk_discount, update_ticket |
| **Facilities** | staff | Lease and rent notices. Hands payment to Accounting. | get_ticket, check_rent_due, update_ticket |
| **Customer Service** | staff | Replies to requesters as **drafts only**, plus discount quotes. | get_ticket, check_stock_and_price, quote_bulk_discount, draft_message, update_ticket |

Added in Problem 6:

| Agent | Tier | Job | MCP tools |
|---|---|---|---|
| **IT Director** | 2 | Allocates ticket types and volume to the staff. Takes blocked or multi-team tickets and assigns the minimum staff. | list_open_tickets, get_ticket, triage_ticket, list_known_issues, update_ticket |

**Agent loop** (`backend/agents/base.py`, `Team.run_agent`) runs these steps:
1. Steps through `agent.iter()` one node at a time.
2. Writes an audit entry for each step.
3. Checks the $500 budget before every model request.
4. On a pay-tool call, PydanticAI pauses the run with `DeferredToolRequests`. The approver decides, and the run resumes.

There are two approvers:
- **Dashboard** (`PendingApprover`): saves the payment as *pending* and doesn't pay it.
- **Terminal** (`HumanApprover`): asks the person at the keyboard.

## 5. Tiered workflow: staff first, directors only when needed

`backend/workflow.py` (`run_desk`) runs `triage_ticket` on each ticket, which matches it against the known-issue playbook in `mcp_server/known_issues.py`:

```
Tier 1  routine known issue, no blocker ─► first staff member on the route (no director); last one closes the ticket
        something unexpected? ─► escalate to IT Director
Tier 2  blocked / multi-team / unknown ─► IT Director assigns the minimum staff from the route
        cash conflict or priority call? ─► escalate to Boss
Tier 3  obligations exceed cash ─► Boss sets priorities
```

| Known issue | Type | Tier | Route |
|---|---|---|---|
| KI-ORDER-INSTOCK | customer_order | 1 | customer_service |
| KI-ORDER-RESTOCK | customer_order | 1 | inventory → customer_service |
| KI-ORDER-VENDOR-BLOCKED | customer_order | 2 | inventory → accounting → customer_service |
| KI-RENT-ROUTINE | rent_notice | 1 | facilities → accounting |
| KI-RENT-OVERDUE | rent_notice | 2 | facilities → accounting → customer_service |
| KI-DISCOUNT-INSTOCK | price_override | 1 | customer_service |
| KI-DISCOUNT-SHORTFALL | price_override | 2 | inventory → customer_service |
| any ticket with accounting on its route, when obligations > cash | — | 3 | Boss |

**Resolving tickets:**
- A ticket is marked `resolved` when its run finishes and nothing on it is waiting for a human.
- If a payment is pending, the ticket is resolved when that payment is approved.
- A denied payment sends the ticket back to `in_progress`.

## 6. Audit trail: `output/audit_trail.json`

The audit trail is an append-only JSON array. Nothing ever wipes it, and every run adds to it. It has one entry per agent-loop step, with these fields:
- **Ids:** `session_id`, `run_id`, `parent_run_id`, **`ticket_id`**
- **Who:** `agent`, `delegated_by`, `depth`, `step`
- **What happened:** `event`, one of dispatch, run_start, model_request, model_response, end_node, run_end, delegation, approval_decision, error, plus the human events (reset, 2fa_code_sent, approval_rejected, payment_approved, payment_denied, payment_refused)
- **Content:** the prompt or text, `tool_calls` (name and args), `tool_results`, and `output`
- **Usage:** the run's tokens, the session's cost, the budget, and whether it has ratcheted

Signed approval tokens and 2FA codes are **never** logged.

## 7. API routes (`backend/main.py`, at http://localhost:8000)

- `GET  /api/health`: checks the API is up and how many MCP tools it can reach (16).
- `GET  /api/tickets`: all three tickets, each **open or resolved**.
- `POST /api/tickets/{id}/run`: **runs the agent team on that ticket** in the background, and returns a `session_id`.
- `GET  /api/tickets/{id}/summary`: **what each agent did** on the latest run: routing, tools, hand-offs, payments prepared, and its report.
- `GET  /api/runs`, `GET /api/runs/{session_id}`: run status (running, done or error) and the run summary.
- `GET  /api/events?since=&limit=&ticket_id=&session_id=`: **recent agent events**, with what each agent said and the tools it used. The board polls this.
- `GET  /api/payments?status=`: payments the agents prepared (pending), plus approved, denied, failed and void ones.
- `POST /api/payments/{id}/request-code`: sends the one-time **2FA code**, written to `output/2fa/<id>_code.txt`.
- `POST /api/payments/{id}/approve`, body `{approved_by, code}`: **a human approves, and this is the only route that changes cash.**
- `POST /api/payments/{id}/deny`, body `{denied_by, reason}`: a human declines, and no money moves.
- `GET  /api/cash`: **balances from `cash_accounts`**, plus obligations and the pending-approval total.
- `POST /api/reset`: **resets the working DB to the original values**. It voids pending payments and keeps the audit trail.

Only payments for invoices and rent exist. Vendor purchases, such as restock orders, aren't in the database.

## 8. Dashboard (`frontend/`, at http://localhost:5173)

The board is built with React + Vite + TypeScript. It talks to `http://localhost:8000` (set in `frontend/.env`), and the backend's CORS allows `http://localhost:5173`. The design is described in `output/design.md`:
- **Layout:** a status strip on top, then three columns: *choose* (tickets), *watch* (live agent feed and per-agent summary), and *decide* (approvals and cash).
- **Agents:** Okabe–Ito colours, which are safe for colour-blind readers, plus 3-letter codes, plus indentation by delegation depth.
- **Ticket state:** `○ open` or `✓ resolved`, shown in words and symbols, not red and green.
- **Cash:** a large balance, a word-sized step line, a paid table and a still-owed table.
- **Only two filled buttons:** Run agent team and Approve and pay.

| Board feature | Route |
|---|---|
| List the tickets | `GET /api/tickets` |
| Start the agent team on a ticket | `POST /api/tickets/{id}/run` |
| Live agent activity | `GET /api/events` (every 1.5 s while running) |
| Summary per agent | `GET /api/tickets/{id}/summary` |
| Approve or deny with 2FA | `/api/payments…` |
| Checking balance | `GET /api/cash` |
| Reset | `POST /api/reset` |

## 9. Safety rules

The full rules are in `RULES.md`. These are the ones the code enforces:
1. **Payments need human approval, with 2FA over $50.**
   - **Agents only prepare payments.** A pay-tool call pauses the run, and on the dashboard it becomes a *pending* payment.
   - **Cash moves only after a human acts.** That means `POST /api/payments/{id}/approve` on the board, or a YES plus name plus code in the terminal. Over **$50**, a one-time 6-digit code is also required. It's sent to a separate file, expires in 5 minutes, and allows 3 tries.
   - **Approvals can't be faked.** The approval is signed with a secret that changes every session and that only the runner and the MCP server know. The pay tool refuses anything unsigned, so agents (and the vibe coder) can't forge or self-approve a payment.
2. **No negative balances.** The pay tool refuses if there isn't enough cash. Cash only goes out, because no revenue is modeled.
3. **No real contact.** No tool can email, call or text anyone. `draft_message` only saves files marked "DRAFT — NOT SENT", and a human decides whether to send.
4. **One path to shop data.** Everything goes through the MCP server. No second shop tool exists.
5. **Today is `desk.date_today`.** Lead times come from `vendors.lead_days`. A vendor with an open invoice won't ship.
6. **Token budget of $500.** `backend/budget.py` prices every call: gpt-6-luna costs $0.20 per million input tokens and $0.75 per million output, from genai-prices.
   - **At 80%:** it ratchets down, cutting the output cap from 4,096 to 1,024 tokens and switching to `HW5_RATCHET_MODEL`. That stays gpt-6-luna, because only that model is allowed.
   - **At 100%:** the run stops.
   - **Per-run limits:** each run is also capped at 25 model requests and 3 levels of delegation.
7. **Don't send every specialist on every ticket.** Tiered routing and route enforcement in `delegate` limit who's involved.
8. **Reset before a full run.** The original DB is never modified.
9. **No invented data.** Missing rows return an `error`, and the prompts say "unknown" instead of guessing.

## 10. Problem 9 results (full run after reset)

| | Value |
|---|---|
| Starting checking (after `POST /api/reset`, 2026-10-24 09:42:57 EDT) | **$3,400.00** |
| Ticket 101 resolved: P-0003, invoice 501 to Bulldog Print Co, approved by Liza with 2FA | −$840.00 → $2,560.00 |
| Ticket 102 resolved: P-0004, rent for lease 1 to Elm City Properties, approved by Liza with 2FA | −$2,400.00 → $160.00 |
| Ticket 103 resolved: no pay or purchase (draft offer only) | $0.00 → $160.00 |
| **Ending checking** | **$160.00**, which **matches `cash_accounts`** in `data/campus_customs_new.db` ✓ |

**Routing:**
- **101:** Tier 2, IT Director → inventory, accounting and customer_service.
- **102:** Tier 1, straight to facilities → accounting.
- **103:** Tier 2, IT Director → inventory and customer_service.
- No ticket reached the Boss.

**Cost:** about $0.017 in tokens for the three runs ($0.0070 + $0.0027 + $0.0076).

**Where the details are:**
- **Itemized ledger, and Expected vs Actual for each ticket:** `output/desk_tickets.html`
- **Per-ticket outcomes and contributions:** `output/resolved_tickets.json`
- **Board screenshots:** `output/resolved_board.html`

**All three reports** are generated from the database and audit trail by `scripts/build_problem9_reports.py`, which stops with an error if the cash doesn't reconcile.

**Gaps the run exposed:**
- The Customer Service drafts showed internal details (the overdue invoice, plus unit cost and margin on 103).
- Accounting sometimes calls the pay tool twice. The duplicate is matched to the same pending payment, so nothing was paid twice.
- The next rent ($2,400, due 2026-10-02) can't be covered by the $160 left.

## 11. File map

```
hw5/
├─ data/campus_customs.db, campus_customs_new.db     original + working copy
├─ mcp_server/server.py, approval.py, known_issues.py, README.md
├─ backend/  main.py (API) · run.py (CLI) · workflow.py (tiers) · agents/ · prompts/ · models.py
│            payments.py · approvals.py · audit.py · budget.py · mcp_client.py
├─ frontend/ React + Vite + TS board (src/App.tsx, components/)
├─ scripts/build_problem9_reports.py
├─ output/   harness.md · design.md · desk_tickets.html · resolved_tickets.json · resolved_board.html
│            audit_trail.json · pending_payments.json · p9_start_snapshot.json · drafts/ · screenshots/ · 2fa/
├─ RULES.md · AI_prompts.md · hw5_log.txt · .mcp.json · llm.py · reset_db.sh · requirements.txt
```
