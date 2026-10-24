import type { Run, Ticket } from "../types";

interface Props {
  tickets: Ticket[];
  runs: Record<number, Run | undefined>;
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export function TicketList({ tickets, runs, selectedId, onSelect }: Props) {
  return (
    <table className="grid tickets">
      <thead>
        <tr><th>#</th><th>Request</th><th>Status</th><th className="num">State</th></tr>
      </thead>
      <tbody>
        {tickets.map((t) => {
          const run = runs[t.id];
          const running = run?.status === "running";
          return (
            <tr key={t.id} className={`${t.id === selectedId ? "selected" : ""} ${t.state}`} onClick={() => onSelect(t.id)}>
              <td className="num">{t.id}</td>
              <td>
                <div className="strong">{t.subject}</div>
                <div className="muted">{t.requester} · {t.type.replace("_", " ")}</div>
              </td>
              <td className="mono small">{running ? "agents running…" : t.status.replaceAll("_", " ")}</td>
              <td className="num state">{t.state === "resolved" ? "✓ resolved" : "○ open"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
