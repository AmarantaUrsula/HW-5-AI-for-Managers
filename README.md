# Campus Customs: agent desk (HW5)

This is a multi-agent help desk for **Campus Customs**, a campus merch shop. A FastMCP server is the only path to the shop's SQLite database.

- **Agents:** a PydanticAI team (Boss, IT Director, Inventory, Accounting, Facilities, Customer Service) works the open tickets.
- **Backend:** a FastAPI app runs the agents and handles human payment approvals.
- **Board:** a React board shows the agents working in real time.
- **Model:** every AI call uses **gpt-6-luna through Portkey**.

> Agents only *prepare* payments. Cash changes only when a human approves on the board, and payments over $50 also need a one-time 2FA code. Nothing is ever emailed or sent. Customer messages are saved as drafts in `output/drafts/`.

## 0. Setup (once)

You need Python 3.11+ (tested on 3.13) and Node 20+ (tested on 24).

```bash
git clone <this repo> hw5 && cd hw5
python3 -m pip install -r requirements.txt
cp .env.example .env              # then put your real PORTKEY_API_KEY in .env (never commit it)
cd frontend && npm install && cd ..
```

`.env` holds `PORTKEY_API_KEY` and `PORTKEY_MODEL=gpt-6-luna`. The real `.env` is gitignored, and `llm.py` refuses any model except gpt-6-luna.

## 1. Copy the original DB to the working copy (clean data)

`data/` has two databases:

| File | Purpose |
|---|---|
| `data/campus_customs.db` | **Original.** Never modified. |
| `data/campus_customs_new.db` | **Working copy.** Every agent, tool and approval writes here. |

The working copy in this repo is in its **after-the-run** state: all 3 tickets resolved and checking at $160. That way the outputs in `output/` match it. To get clean data, copy the original over it:

```bash
cp data/campus_customs.db data/campus_customs_new.db      # or: ./reset_db.sh
```

## 2. Start the MCP server

The server is `mcp_server/server.py`, built with FastMCP. It has 16 tools over `data/campus_customs_new.db`. See `mcp_server/README.md`.

```bash
python3 mcp_server/server.py          # stdio server; Ctrl+C to stop
```

You usually don't need to start it by hand:
- **Backend:** the FastAPI backend starts its own copy of the MCP server over stdio at startup, with the per-session approval secret.
- **Vibe coder:** the vibe coder (Claude Code) connects through `.mcp.json` at the repo root, which runs `python3 mcp_server/server.py`. That connection can read and test tools, but **can't pay anything**, because it has no approval secret.

## 3. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

It's served at http://localhost:8000, with interactive docs at http://localhost:8000/docs. The main routes:
- `GET /api/tickets`
- `POST /api/tickets/{id}/run`
- `GET /api/events`
- `GET /api/tickets/{id}/summary`
- `GET /api/payments`
- `POST /api/payments/{id}/request-code` then `/approve` or `/deny`
- `GET /api/cash`
- `POST /api/reset`

The full list is in `output/harness.md` §7.

## 4. Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

This opens http://localhost:5173. The board calls the backend at `http://localhost:8000`, set in `frontend/.env.example`, which is also the default. The backend's CORS allows `http://localhost:5173`.

## 5. Reset the DB before a full three-ticket run

Always start a full run from the original data:

1. Click **Reset database** on the board. It calls `POST /api/reset`, which copies the original DB over the working copy and voids pending payments. The audit trail is kept. (From a terminal: `./reset_db.sh`, or `curl -X POST localhost:8000/api/reset`.)
2. Note the starting checking balance in the top strip: **$3,400.00**.
3. Run each ticket: select **101**, click **Run agent team**, and watch the activity feed. Then do the same for **102** and **103**.
4. **Approve payments as a human.** Under **Approvals**:
   1. Enter your name and click **Send 2FA code**.
   2. Open `output/2fa/<payment id>_code.txt`, for example `output/2fa/P-0001_code.txt`, and type in the 6 digits.
   3. Click **Approve and pay**.
5. Expected result:
   - **101:** invoice 501, −$840.
   - **102:** rent, −$2,400.
   - **103:** no payment.
   - Checking ends at **$160.00**, all three tickets are resolved, and the total matches `cash_accounts`.

There's also a terminal-only run, which resets first and asks for approvals in the terminal:

```bash
python3 -m backend.run
```

## What's where

```
hw5/
├── AI_prompts.md            prompts I typed for each problem
├── requirements.txt  .env.example  .gitignore  .mcp.json  README.md
├── data/                    campus_customs.db (original) · campus_customs_new.db (working copy)
├── mcp_server/              server.py (16 tools) · approval.py · known_issues.py · README.md
├── backend/                 main.py (FastAPI) · models.py · prompts/ (one .md per agent) · agents/ · workflow.py
│                            run.py · payments.py · approvals.py · audit.py · budget.py · mcp_client.py
├── frontend/                React + Vite + TypeScript board
├── output/                  harness.md · mcp_smoke.json · desk_tickets.html · design.md · resolved_tickets.json
│                            resolved_board.html · audit_trail.json · github_url.txt · drafts/ · screenshots/
├── scripts/                 build_problem9_reports.py (regenerates the Problem 9 reports; checks that cash reconciles)
├── llm.py · reset_db.sh · RULES.md · hw5_log.txt (full prompt/response log)
```

- **Rules the agents follow:** `RULES.md`.
- **Full system reference:** `output/harness.md`, covering the tables, MCP tools, agents, API, dashboard and safety rules.
- **Run results:** `output/desk_tickets.html` has the Expected vs Actual sections, the Cash tab and the Reflection tab.
