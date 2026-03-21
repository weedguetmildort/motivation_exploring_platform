// Centralized API helper for chat

import { apiFetch } from "./fetcher";

export async function sendChat(
  quizId: string,
  conversationId: string | null,
  message: string,
  agents: string[] = [],
  signal?: AbortSignal,
): Promise<{ replies: string[]; conversationId: string; followupQuestions?: string[] }> {
  const data = await apiFetch<{
    reply?: string[];
    message?: string;
    conversation_id?: string;
    followup_questions?: string[];
  }>(
    `/api/chat/${quizId}`,
    {
      method: "POST",
      signal,
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

  return {
    replies,
    conversationId: data.conversation_id ?? conversationId ?? "",
    followupQuestions: data.followup_questions,
  };
}


