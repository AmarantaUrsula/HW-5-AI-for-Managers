import { useCallback, useEffect, useMemo, useState } from "react";
import { api, API_BASE } from "./api";
import { AGENTS, money } from "./agents";
import type { AgentEvent, Cash, Payment, Run, Ticket, TicketSummary } from "./types";
import { TicketList } from "./components/TicketList";
import { ActivityFeed } from "./components/ActivityFeed";
import { AgentSummaryPanel } from "./components/AgentSummaryPanel";
import { ApprovalPanel } from "./components/ApprovalPanel";
import { CashPanel } from "./components/CashPanel";
import { AgentTag } from "./components/AgentTag";

/** Events from the ticket's latest run (from its triage onward), plus human actions after it. */
function latestRun(events: AgentEvent[]): AgentEvent[] {
  const lastDispatch = [...events].reverse().find((e) => e.event === "dispatch");
  if (!lastDispatch) return [];
  return events.filter((e) => e.index >= lastDispatch.index && (e.session_id === lastDispatch.session_id || e.agent === "human"));
}

export default function App() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [summary, setSummary] = useState<TicketSummary | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [cash, setCash] = useState<Cash | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runByTicket = useMemo(() => {
    const m: Record<number, Run | undefined> = {};
    for (const r of runs) if (!m[r.ticket_id] || r.started_at > m[r.ticket_id]!.started_at) m[r.ticket_id] = r;
    return m;
  }, [runs]);
  const anyRunning = runs.some((r) => r.status === "running");
  const selected = tickets.find((t) => t.id === selectedId) ?? null;
  const selectedRun = selectedId ? runByTicket[selectedId] : undefined;

  const refresh = useCallback(async () => {
    try {
      const [t, r, p, c] = await Promise.all([api.tickets(), api.runs(), api.payments(), api.cash()]);
      setTickets(t.tickets); setRuns(r); setPayments(p); setCash(c); setOnline(true);
      setSelectedId((id) => id ?? t.tickets[0]?.id ?? null);
    } catch {
      setOnline(false);
    }
  }, []);

  const refreshTicket = useCallback(async (id: number) => {
    try {
      const [ev, sm] = await Promise.all([api.events(id), api.summary(id)]);
      setEvents(latestRun(ev.events)); setSummary(sm);
    } catch { /* shown by the online flag */ }
  }, []);

  // Poll fast while agents are running, slowly otherwise.
  useEffect(() => {
    refresh();
    const h = setInterval(refresh, anyRunning ? 1500 : 5000);
    return () => clearInterval(h);
  }, [refresh, anyRunning]);
  useEffect(() => {
    if (selectedId === null) return;
    setEvents([]); setSummary(null);  // don't show the previous ticket's feed while the new one loads
    refreshTicket(selectedId);
    const h = setInterval(() => refreshTicket(selectedId), anyRunning ? 1500 : 5000);
    return () => clearInterval(h);
  }, [selectedId, refreshTicket, anyRunning]);

  const start = async () => {
    if (!selected) return;
    setError(null);
    try { await api.runTicket(selected.id); await refresh(); }
    catch (e) { setError((e as Error).message); }
  };
  const reset = async () => {
    if (!confirm("Reset the working database to the original values? Pending payments are voided; the audit trail is kept.")) return;
    setError(null);
    try { await api.reset(); await refresh(); if (selectedId) refreshTicket(selectedId); }
    catch (e) { setError((e as Error).message); }
  };
  const onApprovalChange = () => { refresh(); if (selectedId) refreshTicket(selectedId); };

  const checking = cash?.accounts.find((a) => a.name === "checking");
  const selectedPending = payments.filter((p) => p.status === "pending" && p.ticket_id === selectedId);
  const pendingCount = payments.filter((p) => p.status === "pending").length;
  const resolvedCount = tickets.filter((t) => t.state === "resolved").length;

  return (
    <div className="desk">
      <header>
        <h1>Campus Customs agent desk</h1>
        <span>shop date <b>{cash?.today ?? "—"}</b></span>
        <span>checking <b className="num">{money(checking?.balance)}</b></span>
        <span>tickets <b>{tickets.length - resolvedCount}</b> open · <b>{resolvedCount}</b> resolved</span>
        <span>awaiting approval <b>{pendingCount}</b></span>
        <span className="muted">
          API {online === false ? <b className="error">offline ({API_BASE})</b> : online ? "connected" : "…"}
        </span>
        <button className="right" onClick={reset} disabled={anyRunning}>Reset database</button>
      </header>

      {error && <div className="error banner">{error}</div>}

      <main>
        <section className="col tickets-col">
          <h2>Tickets</h2>
          <TicketList tickets={tickets} runs={runByTicket} selectedId={selectedId} onSelect={setSelectedId} />
          {selected && (
            <div className="ticket-detail">
              <h3>Ticket {selected.id} · {selected.subject}</h3>
              <table className="kv small">
                <tbody>
                  <tr><td>From</td><td>{selected.requester}</td></tr>
                  <tr><td>Type</td><td>{selected.type}</td></tr>
                  {selected.sku && <tr><td>Item</td><td className="mono">{selected.sku} · {selected.size} · qty {selected.qty}</td></tr>}
                  {selected.invoice_id && <tr><td>Invoice</td><td>{selected.invoice_id}</td></tr>}
                  {selected.lease_id && <tr><td>Lease</td><td>{selected.lease_id}</td></tr>}
                  <tr><td>Status</td><td className="mono">{selected.status}</td></tr>
                </tbody>
              </table>
              <button className="primary" onClick={start}
                disabled={anyRunning || selected.state === "resolved" || selectedPending.length > 0}>
                {selectedRun?.status === "running" ? "Agents running…" : "Run agent team"}
              </button>
              {selected.state === "resolved" && <span className="muted small"> resolved, nothing to run</span>}
              {selectedPending.length > 0 && (
                <span className="small"> waiting on your approval of {selectedPending.map((p) => p.id).join(", ")}</span>
              )}
              {selectedRun && selectedRun.status !== "running" && (
                <div className="small muted">
                  Last run {selectedRun.session_id}: {selectedRun.status}
                  {selectedPending.length > 0 && ` · waiting on ${selectedPending.map((p) => p.id).join(", ")}`}
                  {selectedRun.error && <div className="error">{selectedRun.error}</div>}
                </div>
              )}
              <details className="small">
                <summary>Ticket notes</summary>
                <pre className="notes">{selected.notes}</pre>
              </details>
            </div>
          )}
          <h2>Agents</h2>
          <table className="grid compact legend">
            <tbody>
              {Object.entries(AGENTS).map(([key, a]) => (
                <tr key={key}><td><AgentTag agent={key} full /></td><td className="muted">{a.tier}</td></tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="col feed-col">
          <h2>Agent activity {selected ? `· ticket ${selected.id}` : ""}</h2>
          <ActivityFeed events={events} running={selectedRun?.status === "running"} />
          <h2>What each agent did</h2>
          <AgentSummaryPanel summary={summary} />
        </section>

        <section className="col side-col">
          <h2>Approvals</h2>
          <ApprovalPanel payments={payments} onChange={onApprovalChange} />
          <h2>Cash</h2>
          <CashPanel cash={cash} payments={payments} />
        </section>
      </main>
    </div>
  );
}
