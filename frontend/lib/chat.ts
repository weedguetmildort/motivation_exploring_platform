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

export async function sendChat(
  quizId: string,
  conversationId: string | null,
  message: string
): Promise<ChatResponse> {
  const res = await fetch(`/api/chat/${quizId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
    }),
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status} when calling /chat/${quizId}`);
  }

  const data = (await res.json()) as {
    reply?: string[];
    message?: string;
    conversation_id?: string;
    metadata?: AIMessageMetadata[];
  };

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
  const res = await fetch(`/api/chat/followup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ last_ai_message: lastAiMessage }),
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status} when calling /chat/followup`);
  }

  const data = (await res.json()) as { questions?: string[] };
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
  const res = await fetch(`/api/chat/history/${conversationId}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });

  if (!res.ok) {
    throw new Error(
      `HTTP ${res.status} when retrieving conversation history`
    );
  }

  return (await res.json()) as ConversationHistory;
}

