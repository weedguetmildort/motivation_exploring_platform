// frontend/lib/linkClicks.ts
import { apiFetch } from "./fetcher";

export interface LinkClick {
  id: string;
  user_id: string;
  user_email: string;
  quiz_id: string | null;
  question_id: string | null;
  conversation_id: string | null;
  url: string;
  clicked_at: string;
}

const BASE = "/api/links/clicks";

export function recordLinkClick(data: {
  quiz_id?: string;
  question_id?: string;
  conversation_id?: string;
  url: string;
}): Promise<LinkClick> {
  return apiFetch(BASE, { method: "POST", body: JSON.stringify(data) });
}

export function getLinkClicks(): Promise<LinkClick[]> {
  return apiFetch(BASE);
}
