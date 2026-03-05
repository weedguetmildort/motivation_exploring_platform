// Centralized API helper for chat

import { apiFetch } from "./fetcher";

export async function sendChat(
  quizId: string,
  conversationId: string | null,
  message: string,
  agents: string[] = []
): Promise<{ replies: string[]; conversationId: string }> {
  const data = await apiFetch<{ reply?: string[]; message?: string; conversation_id?: string }>(
    `/api/chat/${quizId}`,
    {
      method: "POST",
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        agents,
      }),
    }
  );

  const replies = Array.isArray(data.reply)
    ? data.reply
    : [(data.reply ?? data.message ?? "").toString()];

  return { replies, conversationId: data.conversation_id ?? conversationId ?? "" };
}

export async function sendFollowupChat(
  lastAiMessage: string
): Promise<string[]> {
  const data = await apiFetch<{ questions?: string[] }>(`/api/chat/addon/followup`, {
    method: "POST",
    body: JSON.stringify({ last_ai_message: lastAiMessage }),
  });
  return data.questions ?? [];
}

