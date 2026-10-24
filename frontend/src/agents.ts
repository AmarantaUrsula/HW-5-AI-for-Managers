// One identity per agent: Okabe–Ito colour (safe for the common colour-vision deficiencies)
// PLUS a 3-letter code and a tier label, so colour is never the only cue.

export interface AgentStyle { code: string; name: string; color: string; tier: string }

export const AGENTS: Record<string, AgentStyle> = {
  boss:             { code: "BOS", name: "Boss",             color: "#D55E00", tier: "Tier 3" },
  it_director:      { code: "ITD", name: "IT Director",      color: "#CC79A7", tier: "Tier 2" },
  inventory:        { code: "INV", name: "Inventory",        color: "#0072B2", tier: "Staff" },
  accounting:       { code: "ACC", name: "Accounting",       color: "#009E73", tier: "Staff" },
  facilities:       { code: "FAC", name: "Facilities",       color: "#E69F00", tier: "Staff" },
  customer_service: { code: "CSV", name: "Customer Service", color: "#56B4E9", tier: "Staff" },
  dispatcher:       { code: "DSK", name: "Desk triage",      color: "#666666", tier: "Router" },
  human:            { code: "HUM", name: "Human",            color: "#000000", tier: "Approver" },
};

export const agentStyle = (agent: string): AgentStyle =>
  AGENTS[agent] ?? { code: agent.slice(0, 3).toUpperCase(), name: agent, color: "#666666", tier: "" };

export const money = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD" });
