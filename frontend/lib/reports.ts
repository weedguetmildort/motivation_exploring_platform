// frontend/lib/reports.ts
import { apiFetch } from "./fetcher";

export type ReportCategory =
  | "bug"
  | "unclear_question"
  | "wrong_answer"
  | "technical"
  | "other";

export type ReportStatus = "open" | "in_progress" | "resolved" | "closed";

export interface Comment {
  id: string;
  author_email: string;
  is_admin: boolean;
  body: string;
  created_at: string;
}

export interface Report {
  id: string;
  user_email: string;
  quiz_id: string | null;
  question_id: string | null;
  category: ReportCategory;
  description: string;
  status: ReportStatus;
  comments: Comment[];
  created_at: string | null;
  updated_at: string | null;
}

const BASE = "/api/reports";

export function createReport(data: {
  category: ReportCategory;
  description: string;
  quiz_id?: string;
  question_id?: string;
}): Promise<Report> {
  return apiFetch(BASE, { method: "POST", body: JSON.stringify(data) });
}

export function getMyReports(status?: ReportStatus): Promise<Report[]> {
  const url = status ? `${BASE}?status=${status}` : BASE;
  return apiFetch(url);
}

export function getAllReports(status?: ReportStatus): Promise<Report[]> {
  const url = status ? `${BASE}?status=${status}` : BASE;
  return apiFetch(url);
}

export function getReport(id: string): Promise<Report> {
  return apiFetch(`${BASE}/${id}`);
}

export function addComment(id: string, body: string): Promise<Report> {
  return apiFetch(`${BASE}/${id}/comments`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export function updateStatus(id: string, status: ReportStatus): Promise<Report> {
  return apiFetch(`${BASE}/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}
