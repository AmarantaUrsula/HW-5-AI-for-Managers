import type { AgentEvent } from "../types";
import { money } from "../agents";
import { AgentTag } from "./AgentTag";

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-US", { hour12: false });

function argText(args: unknown): string {
  if (!args || typeof args !== "object") return "";
  return Object.entries(args as Record<string, unknown>)
    .filter(([k, v]) => v !== "" && v !== null && !k.startsWith("approval"))
    .map(([k, v]) => `${k}=${typeof v === "string" && v.length > 40 ? v.slice(0, 40) + "…" : JSON.stringify(v)}`)
    .join(", ");
}

/** One line of plain language per event. */
function describe(e: AgentEvent): string {
  const d = e.detail as Record<string, any>;
  switch (e.event) {
    case "dispatch":
      return `Triage: ${d.known_issue ?? "no known issue"} → Tier ${d.tier}, sent to ${d.sent_to}. Route: ${(d.route ?? []).join(" → ") || "none"}.` +
        (d.escalation_reasons?.length ? ` Why: ${d.escalation_reasons.join("; ")}.` : "");
    case "run_start":
      return e.delegated_by ? `Picked up a hand-off from ${e.delegated_by}.` : "Picked up the ticket.";
    case "delegation":
      return `Hands off to ${d.to}: “${d.request}”`;
    case "approval_decision":
      if (String(d.reason).startsWith("prepared"))
        return `Prepared a payment for human approval: ${d.kind} ${d.ref_id}, ${money(d.amount)} to ${d.payee ?? "?"} (${String(d.reason).replace("prepared for human approval as ", "")}). Not paid yet.`;
      return `${d.approved ? "Payment approved" : "Payment not made"}: ${d.kind} ${d.ref_id}, ${money(d.amount)} to ${d.payee ?? "?"}. ${d.reason}.`;
    case "run_end":
      return `Finished. ${e.said ?? ""}`;
    case "error":
      return `Error: ${d.error}`;
    case "2fa_code_sent":
      return `2FA code sent for ${d.payment} (${d.sent_to}).`;
    case "approval_rejected":
      return `Approval of ${d.payment} rejected: ${d.reason}`;
    case "payment_approved":
      return `Approved ${d.payment}: paid ${money(d.amount)} to ${d.payee} (${d.approval_factor}). ${d.account} ${money(d.balance_before)} → ${money(d.balance_after)}.`;
    case "payment_denied":
      return `Denied ${d.payment}: ${d.reason}.`;
    case "payment_refused":
      return `Pay tool refused ${d.payment}: ${d.reason}.`;
    default:
      return e.said ?? "";
  }
}

export function ActivityFeed({ events, running }: { events: AgentEvent[]; running: boolean }) {
  if (!events.length)
    return <p className="muted empty">No agent activity for this ticket yet. Press “Run agent team”.</p>;
  return (
    <table className="grid feed">
      <colgroup><col style={{ width: 68 }} /><col style={{ width: 62 }} /><col /><col style={{ width: "34%" }} /></colgroup>
      <thead>
        <tr><th>Time</th><th>Agent</th><th>Said / did</th><th>Tools used</th></tr>
      </thead>
      <tbody>
        {events.map((e) => (
          <tr key={e.index} className={`ev-${e.event}`}>
            <td className="mono small muted">{time(e.timestamp)}</td>
            <td><span style={{ paddingLeft: e.depth * 10 }}><AgentTag agent={e.agent} /></span></td>
            <td className="said">{describe(e)}</td>
            <td className="mono small">
              {e.tools_used.map((t, i) => (
                <div key={i}>{t.tool}<span className="muted">({argText(t.args)})</span></div>
              ))}
            </td>
          </tr>
        ))}
        {running && (
          <tr><td /><td /><td className="muted">working…</td><td /></tr>
        )}
      </tbody>
    </table>
  );
}
