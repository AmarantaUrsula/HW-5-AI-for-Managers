// Thin client for the Problem 7 backend. The base URL comes from frontend/.env (VITE_API_BASE).
import type { Cash, EventsResponse, Payment, Run, TicketSummary, TicketsResponse } from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((body as { detail?: string }).detail ?? `${res.status} ${res.statusText}`);
  return body as T;
}

const post = <T,>(path: string, data?: unknown) =>
  request<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const api = {
  health: () => request<{ ok: boolean; mcp_tools: number }>("/api/health"),
  tickets: () => request<TicketsResponse>("/api/tickets"),
  runTicket: (id: number) => post<Run>(`/api/tickets/${id}/run`),
  runs: () => request<Run[]>("/api/runs"),
  run: (sessionId: string) => request<Run>(`/api/runs/${sessionId}`),
  events: (ticketId: number) => request<EventsResponse>(`/api/events?ticket_id=${ticketId}&limit=400`),
  summary: (ticketId: number) => request<TicketSummary>(`/api/tickets/${ticketId}/summary`),
  payments: () => request<Payment[]>("/api/payments"),
  requestCode: (pid: string) => post<{ sent_to: string; expires_in_seconds: number }>(`/api/payments/${pid}/request-code`),
  approve: (pid: string, approved_by: string, code?: string) =>
    post<{ payment: Payment }>(`/api/payments/${pid}/approve`, { approved_by, code: code || null }),
  deny: (pid: string, denied_by: string, reason: string) =>
    post<{ payment: Payment }>(`/api/payments/${pid}/deny`, { denied_by, reason }),
  cash: () => request<Cash>("/api/cash"),
  reset: () => post<{ reset: boolean; voided_pending_payments: number }>("/api/reset"),
};
