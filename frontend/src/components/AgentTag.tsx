import { agentStyle } from "../agents";

/** Agent identity: coloured bar + 3-letter code + name. Colour is never the only cue. */
export function AgentTag({ agent, full = false }: { agent: string; full?: boolean }) {
  const s = agentStyle(agent);
  return (
    <span className="agent-tag" style={{ borderLeftColor: s.color }} title={`${s.name} (${s.tier})`}>
      <b style={{ color: s.color === "#E69F00" || s.color === "#56B4E9" ? "#333" : s.color }}>{s.code}</b>
      {full && <span className="agent-name"> {s.name}</span>}
    </span>
  );
}
