# Problem 2: Study the Campus Customs database

Source: `data/campus_customs.db` (SQLite, original values). Read-only study; nothing was changed.

## "Today" and cash

| Item | Value |
|---|---|
| Today (`desk.date_today`) | **2026-08-31** |
| Cash (`cash_accounts.checking`) | **$3,400.00** |
| Payments made so far (`payments`) | none (table is empty) |

Cash only goes out, because revenue isn't modeled. Every payment permanently reduces the $3,400.

## Tables

| Table | Rows | What it holds |
|---|---|---|
| `desk` | 1 | The shop's "today" date (2026-08-31) |
| `inventory` | 10 | Stock by SKU and size, with aisle location |
| `pricing` | 4 | Unit cost and list price per SKU |
| `vendors` | 3 | Suppliers with specialty and `lead_days` |
| `leases` | 1 | Shop lease: rent and next due date |
| `cash_accounts` | 1 | Checking balance |
| `payments` | 0 | Ledger of approved payments (kind, ref_id, amount, account, paid_at, approved_by) |
| `invoices` | 1 | Vendor bills and their status |
| `tickets` | 3 | Open work items to resolve |

How the tables link: `invoices.vendor_id` → `vendors.id`, `tickets.invoice_id` → `invoices.id`, and `tickets.lease_id` → `leases.id`. Tickets and inventory/pricing are matched by `sku` and `size`. Payment rows point to what they paid through `kind` and `ref_id`.

## Inventory and pricing

| SKU | Name | S | M | L | XL | OS | Unit cost | List price | Margin per unit |
|---|---|---|---|---|---|---|---|---|---|
| CC-HOOD-NAVY | Basic Hoodie Big Yale | 4 | 8 | 14 | 6 | | $22.00 | $58.00 | $36.00 |
| CC-TEE-WHITE | Classic Bulldog Tee | **0** | 5 | 3 | 2 | | $8.00 | $28.00 | $20.00 |
| CC-HAT-BLUE | Yale Cap | | | | | 40 | $6.00 | $22.00 | $16.00 |
| CC-MUG-CREST | Crest Mug | | | | | **0** | $3.50 | $14.00 | $10.50 |

Out of stock: **Tee size S** and **Crest Mug**.

## Vendors

| ID | Vendor | Specialty | Lead days | Open invoices |
|---|---|---|---|---|
| 1 | Bulldog Print Co | apparel reprint | 5 | **#501: $840, overdue** |
| 2 | Elm City Gifts | mugs and small goods | 3 | none |
| 3 | QuickShip CT | local courier | 1 | none |

## Money owed

| Item | Amount | Due | Status as of 2026-08-31 |
|---|---|---|---|
| Invoice 501, Bulldog Print Co ("Rush reprint CC-TEE-WHITE S") | $840.00 | 2026-08-28 | **Overdue by 3 days.** Bulldog won't ship anything new until it's paid. |
| Lease 1, Chapel Street shop rent (Elm City Properties) | $2,400.00 | 2026-09-02 | Due in 2 days, not overdue yet |
| **Total** | **$3,240.00** | | Leaves **$160.00** of the $3,400 |

## Open tickets

| Ticket | Type | Requester | Request | What blocks it or matters |
|---|---|---|---|---|
| 101 | customer_order | Tauhid Zaman | 1 Bulldog tee, size S | Tee S stock is 0. The reprint is on invoice 501, which is overdue, so Bulldog won't ship until it's paid. After payment, the 5-day lead time puts arrival around **2026-09-05** at the earliest. |
| 102 | rent_notice | Elm City Properties | Rent due in 2 days | $2,400 is due 2026-09-02. Paying it needs your approval, and checking can cover it. |
| 103 | price_override | Yale AI Club | 20 hoodies, size M, with a bulk discount | Only **8** size M in stock, so **12 short**. A reprint would come from Bulldog, which is blocked by invoice 501. The discount must stay above the $22 unit cost. |

## Key constraints

1. **Cash is tight.** Paying invoice 501 and the rent together costs $3,240 and leaves $160. Reprinting 12 hoodies at the $22 unit cost would be $264, so all three ($3,504) can't be paid from $3,400. This assumes the vendor charges the unit cost listed in `pricing`.
2. **Invoice 501 blocks Bulldog.** Bulldog won't ship anything until 501 is paid, and that affects both tickets 101 and 103.
3. **Every payment needs your approval.** Each one must also be recorded in `payments`, mark the invoice or lease as paid, and reduce the checking balance. If cash is short, the payment is refused.
4. **No real outreach.** Messages to customers, the landlord or vendors are drafts saved in `hw5/` and never sent.
