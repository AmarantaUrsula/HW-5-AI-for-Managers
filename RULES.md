# HW5 — Campus Customs shop rules and conventions

Database: `data/campus_customs.db` (SQLite)

1. **"Today"** is `desk.date_today`. Use this date, not the real calendar date, to decide what is overdue.
2. **Vendor lead times** come from `vendors.lead_days`.
3. **Unpaid invoices block shipping.** A vendor will not ship new product while they have an open (unpaid) invoice.
4. **Payments need human approval.** No payment is made without explicit approval from the user. When a payment is made:
   - insert a row into `payments` (kind, ref_id, amount, account, paid_at = desk.date_today, approved_by)
   - update the paid item (e.g. `invoices.status` → `paid`, or `leases.next_due` advanced)
   - subtract the amount from `cash_accounts.balance`
5. **No negative balances.** If the account doesn't have enough cash, the pay tool must refuse the payment.
6. **Cash only goes out.** Revenue isn't modeled, so no money comes in. Never add to `cash_accounts.balance`. Every payment permanently reduces the cash left for later obligations.
7. **No real outreach.** Never email customers or contact real vendors. Any message to a customer or vendor is only a draft and stays on board (saved in `hw5/`), never sent.
8. **Use the working copy and reset it before a full run.** All updates go to `data/campus_customs_new.db`. The original `data/campus_customs.db` is never modified. Before any full run that resolves the tickets, run `./reset_db.sh` to copy the original over the working copy.
9. **AI calls go through Portkey.** Every LLM call uses `PORTKEY_API_KEY` via `llm.get_client()`. The key is read from `AI for managers/.env`, and the model is set in `hw5/.env`. Never fall back to another key, and never print or copy the key.
10. **One model for every agent: `gpt-6-luna`** through Portkey, to keep multi-agent token use down. `llm.get_client()` refuses any other model.
11. **Two-factor approval over $50.** No agent may contact a customer, or authorize, initiate or ask for a money movement over $50, without human two-factor approval. Agents only save drafts and never send them. Payments over $50 need a human's YES and name plus a one-time code.
12. **Token budget of $500 at most.** Agent token spend is capped at $500 per session. At 80% it ratchets down: smaller output caps, and `HW5_RATCHET_MODEL`, which stays gpt-6-luna under rule 10. At $500 the run stops.
13. **One path to shop data.** Agents get shop facts only through the MCP server, never by querying the database directly or through a second tool.
14. **Tiered routing: staff first.** Every open ticket goes through `triage_ticket`.
    - **Tier 1:** routine known issues go straight to the IT staff on the route.
    - **Tier 2:** blocked, multi-team or unknown tickets go to the IT Director, who assigns the minimum staff.
    - **Tier 3:** cash conflicts go to the Boss.
    Don't send every specialist on every ticket. Staff can only pull in staff on the ticket's route, and the `delegate` tool enforces it.
15. **On the dashboard, agents only prepare payments.** In API runs, a pay-tool call becomes a pending payment. Cash changes only when a human clicks Approve (`POST /api/payments/{id}/approve`), with a one-time 2FA code over $50.
