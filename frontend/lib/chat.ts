import { apiFetch } from "./fetcher";

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
  followupQuestions?: string[];
  metadata?: AIMessageMetadata[];
}

interface ChatApiResponse {
  reply?: string[];
  message?: string;
  conversation_id?: string;
  followup_questions?: string[];
  metadata?: AIMessageMetadata[];
}

export async function sendChat(
  quizId: string,
  conversationId: string | null,
  message: string,
  agents: string[] = [],
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const data = await apiFetch<ChatApiResponse>(
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
    metadata: data.metadata,
  };
}