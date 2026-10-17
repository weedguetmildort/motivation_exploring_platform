// frontend/lib/copyEvents.ts
import { apiFetch } from "./fetcher";

export interface CopyEvent {
  id: string;
  user_id: string;
  user_email: string;
  quiz_id: string | null;
  question_id: string | null;
  conversation_id: string | null;
  copied_text: string;
  created_at: string;
}

const BASE = "/api/copy-events";

export function recordCopyEvent(data: {
  quiz_id?: string;
  question_id?: string;
  conversation_id?: string;
  copied_text: string;
}): Promise<CopyEvent> {
  return apiFetch(BASE, { method: "POST", body: JSON.stringify(data) });
}

export function getCopyEvents(): Promise<CopyEvent[]> {
  return apiFetch(BASE);
}
