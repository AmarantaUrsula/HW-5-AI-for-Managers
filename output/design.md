# Campus Customs agent desk: dashboard design

The React + Vite + TypeScript board lives in `frontend/` and starts with `npm run dev`. It talks to the FastAPI backend at `http://localhost:8000`, set by `VITE_API_BASE` in `frontend/.env`. The backend allows the Vite origin `http://localhost:5173`.

The design follows one rule: **every mark on the screen should carry information** (Tufte's *data-ink*). There are no cards, shadows, gradients, icons or illustrations. Structure comes from alignment, thin rules and type weight. Colour is used only where it encodes something.

---

## 1. Layout

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ Campus Customs agent desk  shop date 2026-08-31  checking $3,400.00  tickets 3 open ·    │  ← one-line status strip
│ 0 resolved  awaiting approval 1  API connected                         [Reset database]  │
├──────────────────────┬─────────────────────────────────────────────┬─────────────────────┤
│ TICKETS              │ AGENT ACTIVITY · TICKET 102                  │ APPROVALS           │
│ # Request  Status St │ Time   Agent  Said / did          Tools used │ P-0001 rent 1 ...   │
│ 101 ...            ○ │ 09:08  ▌DSK   Triage: KI-RENT-ROUTINE →      │ Pay   $2,400.00     │
│▌102 ...            ○ │ 09:08  ▌FAC   Picked up the ticket.          │ checking 3,400→1,000│
│ 103 ...            ○ │ 09:08  ▌FAC                 check_rent_due(…)│ [name][Send 2FA]    │
│                      │ 09:08  ▌FAC   Hands off to accounting: “…”   │ [code] [Approve][Deny]│
│ Ticket 102 · detail  │ 09:08    ▌ACC Prepared a payment … P-0001    │ CASH                │
│ [Run agent team]     │ …                                            │ checking $3,400.00  │
│                      │ WHAT EACH AGENT DID                          │ ▁▁▁▁▔▔ step line    │
│ AGENTS (legend)      │ Agent      Did                Outcome        │ paid / still owed   │
└──────────────────────┴─────────────────────────────────────────────┴─────────────────────┘
      ~25%                              ~48%                                ~27%
```

The three columns follow the order of the work:
- **Left: choose.** The ticket list, the selected ticket's details, the **Run agent team** button, and the agent legend.
- **Centre: watch.** The live activity feed for the selected ticket's latest run. Below it, **What each agent did**, a one-row-per-agent summary.
- **Right: decide.** Pending **Approvals**, the only place a person acts on money. Below them, **Cash**.

The **status strip** at the top puts the five numbers a desk manager watches on one line: shop date, checking balance, open and resolved counts, approvals waiting, and API status. They stay visible while scrolling any column.

*Why:* the eye moves left to right, from what to work on, to what the agents are doing, to what needs me. Nothing important is hidden behind a click or a modal. The only collapsed element is a ticket's raw notes.

## 2. Density and readability

- **Tables, not cards.** Tickets, the feed, the agent summary, payments and obligations are all plain tables. They have a dark rule under the header and hairline rules (`#dcdcdc`) between rows, with no boxes. Many rows fit on one screen.
- **13 px system font, 11 px uppercase section labels** in grey. Section labels rank below the data they label.
- **Tabular numbers** (`font-variant-numeric: tabular-nums`) and right-aligned money, so amounts line up and can be compared down a column.
- **Monospace only for machine things:** tool calls with their arguments (`check_rent_due(lease_id=1)`), SKUs and raw statuses. Human sentences stay in the proportional font, so it's always clear which text the agent said and which was a tool call.
- **Plain-language feed:** each audit event becomes one sentence, such as "Hands off to accounting: …", "Prepared a payment for human approval: rent 1, $2,400.00 … Not paid yet." or "Approved P-0001: paid $2,400.00 … checking $3,400.00 → $1,000.00."
- **Polling, not reloading:** the board refreshes every 1.5 s while agents run and every 5 s otherwise, so the feed grows in place.

## 3. How the agents read differently

Each agent has **three redundant cues**, so no one depends on colour vision:

| Agent | Code | Colour (Okabe–Ito) | Tier |
|---|---|---|---|
| Boss | `BOS` | vermillion `#D55E00` | Tier 3 |
| IT Director | `ITD` | reddish purple `#CC79A7` | Tier 2 |
| Inventory | `INV` | blue `#0072B2` | Staff |
| Accounting | `ACC` | bluish green `#009E73` | Staff |
| Facilities | `FAC` | orange `#E69F00` | Staff |
| Customer Service | `CSV` | sky blue `#56B4E9` | Staff |
| Desk triage | `DSK` | grey | Router |
| Human | `HUM` | black | Approver |

- **Colour:** a 4 px coloured bar to the left of the code. The **Okabe–Ito palette** was designed to stay distinguishable for protanopia, deuteranopia and tritanopia, and it has no red/green pair.
- **Code:** a fixed 3-letter monospace code (`FAC`, `ACC`, …), which is readable in greyscale or print. For the light colours (orange and sky blue), the code is drawn in dark grey with only the bar coloured, to keep text contrast high.
- **Position:** feed rows are **indented by delegation depth**, so a hand-off chain like FAC → ACC shows as a step to the right without needing colour.
- **Legend:** the left column lists every agent with its tier.

Colour is used **only** for agent identity and for error text. Status, selection and money use type weight, symbols and position instead.

## 4. How resolved tickets show up

- The **State** column uses a symbol and a word: `○ open` or `✓ resolved`. The meaning never depends on colour, so there's no red/green.
- A resolved row turns **grey**, which pushes it into the background, while its state cell stays **bold black**. Finished work recedes but stays easy to confirm.
- The raw status (`waiting on approval`, `in progress`, …) sits next to it in monospace, so open tickets show *why* they're open. While agents work, it reads `agents running…`.
- A ticket is marked resolved when its run finishes and **nothing on it is waiting for a human**. If a payment is pending, the ticket waits, and the detail panel says "waiting on your approval of P-0001". The Run button is disabled then and for resolved tickets, so a second run can't prepare the same payment again.
- The top strip counts open and resolved tickets.

## 5. How cash shows up

- **One large number:** the checking balance, the only large type on the page because it's the number that matters most. After an approved payment it shows the change ("−$2,400.00 since start"). The same balance is repeated in the top strip.
- **A word-sized step line** (a Tufte *sparkline*): one 220×34 px line with no axes, gridlines or fill. It steps down once per approved payment, with a dot on the current value, so you can see at a glance that cash only goes down.
- **Paid table:** start balance, each approved payment (−amount), and the running balance. This is the exact numbers behind the line.
- **Still owed table:** each open obligation with its due date and "(overdue)" in words, a ruled total of **Cash after all obligations**, and **Waiting for approval**. These make it clear before you click Approve whether the money covers everything.

## 6. Approvals: functional elements only

- Each pending payment shows who asked (the agent), the amount, the payee, the due date, and the balance before and after.
- **The only filled (black) buttons** on the page are **Run agent team** and **Approve and pay $X**, the two actions that cost money or tokens. Everything else is an outline button.
- The Approve button is **disabled until the rules are met**: a name is entered, and for payments over $50, a 6-digit code has been requested and typed. "Over $50: two-factor required. Code sent to output/2fa/<payment id>_code.txt." says why.
- Errors from the backend appear in red text under the row, for example "Two-factor check failed: Wrong code (1/3)" or "Pay tool refused: not enough cash".
- The agents only **prepare** payments. Cash changes only through this panel (`POST /api/payments/{id}/approve`).

## 7. What was left out, and why

- **No decorative chrome:** no logo, hero, icons, avatars, shadows, rounded cards, background tints or animations. None of them carry data.
- **No pie charts or gauges for cash.** There's only one account and a handful of payments, so a number, a step line and a table say it exactly.
- **No colour-coded status pills.** Words and symbols carry status, which works for every reader and in greyscale.
