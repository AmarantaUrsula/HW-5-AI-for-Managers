# HW5 — AI Prompts Log

This file records the prompts I typed into the vibe coder (Claude Code) for HW5.
Each problem has its own section with:
- the problem number and title
- at least one prompt I typed
- a follow-up prompt, if one was needed, plus one sentence on what the first
  prompt's result was missing

The full transcript of every prompt and response is in `hw5_log.txt`.

---

## Setup — Project folder, rules, and AI configuration

**Prompt:**
> I am doing a new assignment and I want all the work saved in the folder called hw5

**Follow-up prompts:**
> Ok first, please keep a log in a txt or similar kind of file with all prompts and responses here for Hw 5. Before we get started please note these rules/conventions: -The field desk.date_today is "today" for the shop. use this date to determine what is overdue =vendor lead times come from the vendors table =a vendor will not ship new product while they still have an open unpaid invoice -human approval is required for any payments. points will be deducted if this is not done. if payment is made, make sure to update the relevant table. -if there is not enough cash. the pay tool must refuse- no negative balances

> more rules on this before we proceed: =cash only goes out in this homework - we did not model revenue, so no money comes in =do not email customers or call real vendors. Drafts stay onboard.

> ok please add these rules: -cash only goes out in this homework - we did not model revenue, so no money comes in -before a full run to resolve the tickets, make sure to reset the database to the original values -do NOT email customers or call real vendors. Drafts stay on board

> can you ensure you are using my PORTKEY_API_KEY for AI calls? it can be found here: /Users/Liza/Library/CloudStorage/OneDrive-YaleUniversity

> for this assignment only use gpt-6-luna through Portkey for every agent because multi-agent chats burn tokens fast, ok?

**What was lacking after the first prompt:** The first prompt only set up the
folder, so I followed up to add the shop rules, the database reset, the Portkey
key, and the model choice (gpt-6-luna).

---

## Problem 1: Vibe coder prompts

**Prompt:**
> Please create AI_prompts.md at the start of the assignment and keep it updated as I work. This file is the log of what I typed here in the vibe coder. Make a section for each problem. Each section must include: the problem number and title; at least one prompt I typed; one follow-up prompt if I need it (and one sentence on what was lacking after the first that I had to follow up). Make sure these details are included in this file.

**Follow-up prompt:**
> Actually this most recent set of instructions is Problem 1 and this section should be labeled "Problem 1: Vibe coder prompts"

**What was lacking after the first prompt:** The file was created, but the
AI_prompts.md request was filed under "Setup" instead of being labeled as
Problem 1 with its title.

---

## Problem 2: Study the Campus Customs database

**Prompt:**
> Problem 2 is "Problem 2: Study the Campus Customs database"

**Follow-up prompt:**
> ok let's back up. Open data/campus_customs.db and look through every table and its fields. Copy the original file to data/campus_customs_new.db - later problems update that working copy. Study the three open tickets so you can see how they link to the other tables. Now, start output/harness.md. For each table, list the fields and one short line on why that table matters for the agents. You will keep growing this harness file as we advance this project (aka do future problems).

**What was lacking after the first prompt:** I had only given the title, so the
first result was a general summary. It didn't create the working copy
(campus_customs_new.db) or start output/harness.md with each table's fields and
why it matters for the agents.

---

## Problem 3: Build the MCP server

**Prompt:**
> Problem 3: build the MCP server. Write an MCP server in mcp_server/ using FastMCP. It will talk to data/campus_customs_new.db. You do NOT need to connect or run it in this problem. Every agent in this homework uses the tools in this MCP server. You will add more tools to it later; for now write three tools you know we will need for the tickets in the database. Keep the names clear. Never invent data, only use information in the database. In output/harness.md, list each of your three MCP tools. For every tool include: which tables it reads, which ticket it helps unlock (101, 102, or 103), and one sentence on why that tool is the right one for that ticket. Values like "reads inventory" score low so please tie the tool to the ticket. Also, add a short mcp_server/README.md file that explains what the MCP server is for, which database file it uses, and the three tools it has.

**Follow-up prompt:** none yet.

---

## Problem 4: Add the MCP server to the vibe coder and test each tool

**Prompt:**
> Ok here is problem 4: Problem 4: Add the MCP server to the vibe coder and test each tool. Make that section and then I'll proceed with instructions.

> ok so here is the work for this problem 4: add your MCP server to this project so you (the vibe coder) can call the tools. Save the connection JSON text in .mcp.json at the project root. Make sure you, the vibe coder, are connected, then test EACH of your three MCP tools. Save the evidence in output/mcp_smoke.json. For every tool include: the prompt I asked here (in the vibe coder); the tool name; the tool output (must match values in data/campus_customs_new.db).

**Follow-up prompt:** none. I moved on to Problem 5 before the smoke test ran. The vibe coder finished it during Problem 11, because `output/mcp_smoke.json` is in the expected submission layout.

**What was lacking after the first prompt:** The vibe coder couldn't call the tools until the session reloaded with `.mcp.json`. The three tool calls were made later through that live connection, and each output was checked against the working DB.

---

## Problem 5: Build the agent team and grow the MCP tools

**Prompt:**
> ok here is problem 5. Its called Problem 5: Build the agent team and grow the MCP tools. Build the agentic team for Campus Customs using PydanticAI: Boss, Inventory, Accounting, Facilities, and Customer Service. Include prompts, models, and agent loops so they can delegate work to each other with full connectivity. Put the agent prompts in backend/prompts/ - one file per agent, ok? Put data types in the backend/models.py, and the agent files under backend/ (the layout can vary as long as the five roles are CLEAR). Use my PORTKEY_API_KEY and only gpt-6-luna for every agent.
>
> Now add any tools the agents need to the MCP server so they can work on open tickets. Shop facts come from the MCP server over data/campus_customs_new.db. Do NOT invent a second shop tool later that bypasses MCP, ok?
>
> Wire the agents so they append to output/audit_trail.json as they run: for each agent-loop step, record enough to audit later. Append to this file - do not wipe it each run.
>
> In output/harness.md, list each agent and each MCP tool (including the ones we added in this problem) along with which table the tool uses. Also add a short safety section: for example do not actually contact a customer or authorize or initiate the solicitation or moving of money in amounts more than $50 without human two factor authentication. Do not use a token amount that exceeds $500; if you approach that ratchet down to a less expensive model. Update mcp_server/README.md so the tool list matches what you have now.

**Follow-up prompt:** none yet.

---

## Problem 6: Plan the three tickets

**Prompt:**
> Ok here goes problem 6. It's called Problem 6: plan the three tickets. Before you wire the backend, let's write down what we expect the team to do on each open ticket. Build output/desk_tickets.html - a page you can double-click with one tab per ticket (101, 102, 103). Also add empty Cash and Reflection tabs for later problems (leave them blank or with a short "coming later" note for now). On each ticket tab, fill an Expected section only (leave room for an Actual section you will fill after you run the agents). For each ticket's Expected section please indicate: That the boss should call the IT director first because they are the one who allocate types and volume of tickets to IT staff

**Follow-up (answer to the vibe coder's question):** When asked how to handle the IT director (the team didn't have one), I chose "Add IT Director agent": a sixth agent that the Boss consults first to assign tickets to specialists.

**Follow-up prompt:**
> ALSO, as you just clarified we haven't finished all the rules. We expect agent delegation to include some calls directly to IT staff, such as routine known issues. Please pick the MCP tools that are best fitted for this purpose. Do not send every specialist on every ticket. Let's make a workflow where IT specialists are directly sent problems that are common with known solutions and tier from there when directors need to be involved.

**What was lacking after the first prompt:** The first plan sent every ticket through the
Boss and IT Director and could pull in every specialist, so I followed up to add a tiered workflow. Routine known
issues now go straight to IT staff, and directors are involved only when escalation is needed.

---

## Problem 7: Backend routes

**Prompt:**
> ok here is Problem 7, its called Problem 7: Backend routes. Your React frontend dashboard (we will do this in the next problem) needs a backend it can call. In backend/main.py, use FastAPI and add routes that do the following: Return the three tickets and whether each is open or resolved

**Follow-up prompts:**
> Also, there are a few more things to do for this problem 7. The routes also must: Take a ticket ID and run your agent team on that ticket; Return recent agent events - what each agent said and which tool they used - so the board can refresh; Approve a payment or purchase after a human clicks approve (agents only prepare the pay; this route is what actually changes cash); Return the current checking balances from cash_accounts; Reset the database to the original values when you want to try a fresh run. Then from the backend/ folder, start the server with: uvicorn main:app --reload --port 8000

> This turn on your backend at http://localhost:8000 so the frontend dashboard can call those routes. In output/harness.md list each route in one line (what URL/what it does).

**What was lacking after the first prompt:** The first prompt only asked for the tickets route, so the backend
couldn't run agents, show agent events, approve payments, show cash, or reset. It also wasn't running on port 8000 or
documented route by route in the harness.

---

## Problem 8: Agent dashboard

**Prompt:**
> here is problem 8: Problem 8: Agent dashboard. Build the frontend dashboard in frontend/ with React + Vite + TypeScript. The page should call the routes you built in Problem 7. At minimum the board should: list all three tickets; let me pick one ticket and start the agent team on it; show each agent and what they are saying/doing as the ticket runs; mark a ticket resolved when the run finishes; show a short summary of what each agent did on that ticket; let a human approve a pay or purchase when asked; show the checking balance (it should drop after an approved pay). Make the dashboard design adhere to principles of user experience design, e.g. color blind friendly color palette, relatively dense display of information, not too many design elements that are decorative only (as per Edward Tufte). Tell the front end to talk to your backend at http://localhost:8000. On the backend, allow the Vite page origin (usually http://localhost:5173) so the browser is allowed to call those routes. Start the board with: npm run dev. This opens the React desk in my browser so I can pick tickets and watch agents. Write output/design.md with the same dashboard look (layout, how agents read differently, how resolved tickets and cash show up) and why, e.g. ensuring readability, dense information and design elements that are functional.

**Follow-up prompt:** none yet.

---

## Problem 9: Resolve the tickets

**Prompt:**
> ok this seems like its working well enough. Let's move on to problem 9: Problem 9: Resolve the tickets. Before testing the agents on a full run over the three tickets, I want to reset the working database data/campus_customs_new.db again so we can start clean. I want to note the starting checking balance for me and then run all three tickets on the board (101, 102, 103) until each is resolved. Open output/desk_tickets.html from Problem 6. On each ticket tab, fill in the Actual section from this run: which agents worked, what they delegated, and which tools they used. Keep the Expected section so we can compare the two. On the Cash tab of the same output/desk_tickets.html, itemize the money: starting checking balance (after the reset); for each ticket, how cash changed when that ticket resolved, and why (which pay/purchase, dollar amount); ending checking balance — it must match cash_accounts in the working database. Wrong cash will get points deducted from this assignment even if the board shows every ticket resolved, so let's make sure this works. Also save: output/resolved_tickets.json — for each ticket: id, final status, short outcome, what each agent contributed, and any human approvals; output/resolved_board.html — a page I can double-click with a screenshot of the React board for each resolved ticket (101, 102, 103). Append real runs to output/audit_trail.json. Finish output/harness.md so it covers tables, MCP tools, the five agents, API routes, the dashboard, and safety rules.

**Follow-up prompt:**
> I approved P-0003 and P-0004 on the board with 2FA. Please verify and finish Problem 9.

**What was lacking after the first prompt:** The agents can only *prepare* payments, so tickets 101 and 102 couldn't
resolve until I approved P-0003 ($840) and P-0004 ($2,400) myself with 2FA on the board. The follow-up confirmed those
approvals so the vibe coder could verify cash ($3,400 → $160, matching cash_accounts) and finish the reports.

---

## Problem 10: Reflection

**Prompt:**
> here is problem 10. Problem 10: Reflection. Open output/desk_tickets.html and fill the Reflections tab. This should be answered in my own vibe and be detailed and thorough. How would we evaluate the performance of the agent on each ticket and why? For each ticket, how did Actual compare to the Expected plan you wrote earlier? What would have been simpler as one agent with tool - and WHY? Describe three new problems Campus Customs might face that this agent team could solve with the tools we built? Describe three new problems Campus Customs might face that this agent team could NOT resolve with the tools we built, and explain the tools we would need to solve them. Tie every answer to THIS app and the three tickets we ran - use the tickets tab and Cash tab on the same page as the evidence. This should not be a generic AI essay and must include Campus Customs details. If you are unsure prompt me for my opinion or a decision point.

**Follow-up (my answers to the vibe coder's decision questions):** Score each ticket with a **pass/fail checklist**; my verdict on the multi-agent team is **"worth it, with caveats"**; the miss that bothers me most is **the drafts leaking internal details**; write it in **first person, polished**.

**What was lacking after the first prompt:** The reflection needed my own judgments (how to grade, whether the team was
worth it, which miss mattered most, and my voice), so the vibe coder asked me those decision points before writing.

---

## Problem 11: Submit to GitHub

**Prompt:**
> That looks great. Here is problem 11: Problem 11: Submit to GitHub. Push my code to a public GitHub repository so graders can clone it and also put it in output/github_url.txt. Do NOT push my real .env to the GitHub repo. Do include both database files under data/ (the original and my working copy) so graders can run the app easily. README should explain: copy original DB to the working copy when I need a clean run, start MCP server, start FastAPI backend, start the React board, reset the DB before a full three-ticket run. See this pic for expected file layout. *(attached screenshot of the expected hw5/ layout)*

**Follow-up prompt:** none yet.

---

<!-- One section per problem, added as I work:

## Problem N: Title

**Prompt:**
> ...

**Follow-up prompt:**
> ...

**What was lacking after the first prompt:** one sentence.

-->
