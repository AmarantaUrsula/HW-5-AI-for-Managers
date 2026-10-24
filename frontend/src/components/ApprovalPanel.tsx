import { useState } from "react";
import type { Payment } from "../types";
import { money } from "../agents";
import { api } from "../api";

interface Props { payments: Payment[]; onChange: () => void }

/** Human approval: agents only prepare payments; cash moves only when a person approves here. */
export function ApprovalPanel({ payments, onChange }: Props) {
  const pending = payments.filter((p) => p.status === "pending");
  if (!pending.length) return <p className="muted empty">Nothing waiting for approval.</p>;
  return <div>{pending.map((p) => <PendingRow key={p.id} p={p} onChange={onChange} />)}</div>;
}

function PendingRow({ p, onChange }: { p: Payment; onChange: () => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [codeSentTo, setCodeSentTo] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const act = async (fn: () => Promise<unknown>, after?: (r: any) => void) => {
    setBusy(true); setMsg(null);
    try { const r = await fn(); after?.(r); onChange(); }
    catch (e) { setMsg((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <div className="approval">
      <div className="approval-head">
        <b>{p.id}</b> · {p.kind} {p.ref_id} · ticket {p.ticket_id ?? "—"} · asked by {p.requested_by}
      </div>
      <table className="kv">
        <tbody>
          <tr><td>Pay</td><td className="num strong">{money(p.amount)}</td><td>to {p.payee}</td></tr>
          <tr><td>Due</td><td className="num">{p.due}</td><td>{p.overdue ? "overdue" : ""}</td></tr>
          <tr><td>{p.account}</td><td className="num">{money(p.balance_before)} → {money(p.balance_after)}</td><td>at preparation</td></tr>
        </tbody>
      </table>
      <div className="form-row">
        <input placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
        {p.requires_two_factor && (
          <>
            <button disabled={busy} onClick={() => act(() => api.requestCode(p.id), (r) => setCodeSentTo(r.sent_to))}>
              {codeSentTo ? "Resend code" : "Send 2FA code"}
            </button>
            <input className="code" placeholder="6-digit code" value={code} maxLength={6} onChange={(e) => setCode(e.target.value)} />
          </>
        )}
      </div>
      {p.requires_two_factor && (
        <div className="muted small">
          Over $50: two-factor required.
          {codeSentTo ? <> Code sent to <span className="mono">{codeSentTo}</span>. Open that file fresh; each new request replaces the old code.</> : ""}
        </div>
      )}
      <div className="form-row">
        <button className="primary" disabled={busy || !name.trim() || (p.requires_two_factor && code.length !== 6)}
          onClick={() => act(() => api.approve(p.id, name.trim(), code))}>
          Approve and pay {money(p.amount)}
        </button>
        <button disabled={busy || !name.trim()} onClick={() => act(() => api.deny(p.id, name.trim(), "denied on dashboard"))}>
          Deny
        </button>
      </div>
      {msg && <div className="error small">{msg}</div>}
    </div>
  );
}
