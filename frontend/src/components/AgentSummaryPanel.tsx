import type { TicketSummary } from "../types";
import { money } from "../agents";
import { AgentTag } from "./AgentTag";

/** What each agent did on the ticket, one compact row per agent. */
export function AgentSummaryPanel({ summary }: { summary: TicketSummary | null }) {
  if (!summary?.session_id) return <p className="muted empty">No run yet.</p>;
  const d = summary.dispatch;
  return (
    <div>
      {d && (
        <p className="small">
          <b>Routing:</b> {d.known_issue} · Tier {d.tier} · first to <b>{d.sent_to}</b> · route {d.route.join(" → ") || "—"}
        </p>
      )}
      <table className="grid summary">
        <thead>
          <tr><th>Agent</th><th>Did</th><th>Outcome</th></tr>
        </thead>
        <tbody>
          {summary.agents.map((a) => (
            <tr key={a.agent}>
              <td>
                <AgentTag agent={a.agent} full />
                {a.delegated_by && <div className="muted small">asked by {a.delegated_by}</div>}
              </td>
              <td className="small">
                {a.tools_used.map((t) => (
                  <span key={t.tool} className="mono">{t.tool}{t.calls > 1 ? `×${t.calls}` : ""} </span>
                ))}
                {a.handed_off_to.length > 0 && <div>→ handed off to {a.handed_off_to.join(", ")}</div>}
                {a.payments_prepared.map((p, i) => (
                  <div key={i}>prepared {p.kind} {p.ref_id} {money(p.amount)}</div>
                ))}
                {a.report?.drafts_saved.length ? <div>draft saved (not sent)</div> : null}
              </td>
              <td className="small">
                {a.report?.recommendation ?? <span className="muted">—</span>}
                {a.report?.blocked_on.length ? <div className="muted">Blocked: {a.report.blocked_on.join("; ")}</div> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
