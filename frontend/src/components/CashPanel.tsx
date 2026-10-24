import type { Cash, Payment } from "../types";
import { money } from "../agents";

/** Checking balance, its trail since the last reset, and what is still owed. */
export function CashPanel({ cash, payments }: { cash: Cash | null; payments: Payment[] }) {
  if (!cash) return <p className="muted empty">Loading…</p>;
  const lastReset = payments.filter((p) => p.reason === "database reset").map((p) => p.decided_at ?? "").sort().pop() ?? "";
  const paid = payments
    .filter((p) => p.status === "approved" && (p.decided_at ?? "") > lastReset && p.result)
    .sort((a, b) => (a.decided_at ?? "").localeCompare(b.decided_at ?? ""));
  const start = paid.length ? paid[0].result!.balance_before : cash.total_cash;
  const points = [start, ...paid.map((p) => p.result!.balance_after)];

  return (
    <div>
      {cash.accounts.map((a) => (
        <div key={a.name} className="balance">
          <span className="muted">{a.name}</span>
          <span className="big num">{money(a.balance)}</span>
          {paid.length > 0 && <span className="num small">({money(a.balance - start)} since start)</span>}
        </div>
      ))}
      <StepLine points={points} />
      <table className="grid compact">
        <thead><tr><th>Paid</th><th className="num">Amount</th><th className="num">Balance</th></tr></thead>
        <tbody>
          <tr><td className="muted">start</td><td /><td className="num">{money(start)}</td></tr>
          {paid.map((p) => (
            <tr key={p.id}><td>{p.id} {p.kind} {p.ref_id}</td><td className="num">−{money(p.amount)}</td><td className="num">{money(p.result!.balance_after)}</td></tr>
          ))}
        </tbody>
      </table>
      <table className="grid compact">
        <thead><tr><th>Still owed</th><th>Due</th><th className="num">Amount</th></tr></thead>
        <tbody>
          {cash.obligations.map((o) => (
            <tr key={`${o.kind}${o.ref_id}`}>
              <td>{o.kind} {o.ref_id} · {o.payee}</td>
              <td className="num">{o.due}{o.overdue ? " (overdue)" : ""}</td>
              <td className="num">{money(o.amount)}</td>
            </tr>
          ))}
          <tr className="total"><td>Cash after all obligations</td><td /><td className="num">{money(cash.cash_after_all_obligations)}</td></tr>
          {cash.pending_approval_total > 0 && (
            <tr><td>Waiting for approval</td><td /><td className="num">{money(cash.pending_approval_total)}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** A Tufte-style word-sized step line: only data ink, start and end labelled. */
function StepLine({ points }: { points: number[] }) {
  if (points.length < 2) return null;
  const w = 220, h = 34, max = Math.max(...points), min = 0;
  const x = (i: number) => (i / (points.length - 1)) * (w - 2) + 1;
  const y = (v: number) => h - 2 - ((v - min) / (max - min || 1)) * (h - 4);
  const d = points.map((v, i) => (i === 0 ? `M${x(0)},${y(v)}` : `H${x(i)}V${y(v)}`)).join("");
  return (
    <svg width={w} height={h} className="stepline" aria-label="checking balance after each approved payment">
      <path d={d} fill="none" stroke="#333" strokeWidth={1.25} />
      <circle cx={x(points.length - 1)} cy={y(points[points.length - 1])} r={2.5} fill="#333" />
    </svg>
  );
}
