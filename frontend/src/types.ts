// Shapes returned by the FastAPI backend (backend/main.py).

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  status: string;
  state: "open" | "resolved";
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  notes: string | null;
  created_at: string;
}

export interface TicketsResponse { tickets: Ticket[]; count: number; open: number; resolved: number }

export interface Run {
  session_id: string;
  ticket_id: number;
  status: "running" | "done" | "error" | "stopped";
  started_at: string;
  finished_at: string | null;
  error: string | null;
  resolution: { resolved: boolean; waiting_on?: string[] } | null;
}

export interface AgentEvent {
  index: number;
  timestamp: string;
  session_id: string;
  run_id: string;
  ticket_id: number | null;
  agent: string;
  delegated_by: string | null;
  depth: number;
  event: string;
  said: string | null;
  tools_used: { tool: string; args: unknown }[];
  tool_results: { tool: string; result: unknown }[];
  detail: Record<string, unknown>;
}

export interface EventsResponse { events: AgentEvent[]; next_since: number; total: number }

export interface AgentReport {
  role: string;
  ticket_ids: number[];
  findings: string[];
  actions_taken: string[];
  drafts_saved: string[];
  blocked_on: string[];
  recommendation: string;
}

export interface AgentSummary {
  agent: string;
  delegated_by: string | null;
  tools_used: { tool: string; calls: number }[];
  handed_off_to: string[];
  payments_prepared: { kind: string; ref_id: number; amount: number | null; reason: string }[];
  report: AgentReport | null;
  steps: number;
}

export interface TicketSummary {
  ticket_id: number;
  session_id: string | null;
  dispatch: { known_issue: string | null; tier: number; route: string[]; escalation_reasons: string[]; sent_to: string } | null;
  agents: AgentSummary[];
  human_actions: { event: string; timestamp: string; detail: Record<string, unknown> }[];
}

export interface Payment {
  id: string;
  status: "pending" | "approved" | "denied" | "failed" | "void";
  kind: "invoice" | "rent";
  ref_id: number;
  account: string;
  amount: number;
  payee: string;
  due: string;
  overdue: boolean;
  requires_two_factor: boolean;
  balance_before: number;
  balance_after: number;
  ticket_id: number | null;
  requested_by: string;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  factor: string | null;
  reason: string | null;
  result: { balance_before: number; balance_after: number; amount: number } | null;
}

export interface Cash {
  today: string;
  accounts: { name: string; balance: number; date: string }[];
  total_cash: number;
  obligations: { kind: string; ref_id: number; payee: string; amount: number; due: string; overdue: boolean; description: string }[];
  cash_after_all_obligations: number;
  pending_approval_total: number;
}
