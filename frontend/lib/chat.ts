// Centralized API helper for chat with optional metadata support

export interface AIMessageMetadata {
  sources?: string[];
  confidence_score?: number;
  model_version?: string;
  processing_time_ms?: number;
  tokens_used?: number;
  input_tokens?: number;
  output_tokens?: number;
  custom_metadata?: Record<string, unknown>;
}

export interface ChatResponse {
  replies: string[];
  conversationId: string;
  metadata?: AIMessageMetadata[];
}

import { apiFetch } from "./fetcher";

export async function sendChat(
  quizId: string,
  conversationId: string | null,
  message: string,
  agents: string[] = []
): Promise<ChatResponse> {
  const data = await apiFetch<{
    reply?: string[];
    message?: string;
    conversation_id?: string;
    metadata?: AIMessageMetadata[];
  }>(
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

  return {
    replies,
    conversationId: data.conversation_id ?? conversationId ?? "",
    metadata: data.metadata,
  };
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

export interface ConversationMessage {
  role: string;
  content: string | string[];
  created_at: string;
  metadata?: AIMessageMetadata;
  user_email?: string;
}

export interface ConversationHistory {
  conversation_id: string;
  messages: ConversationMessage[];
}

export async function getConversationHistory(
  conversationId: string
): Promise<ConversationHistory> {
  return apiFetch<ConversationHistory>(`/api/chat/history/${conversationId}`, {
    method: "GET",
  });
}

