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

 export interface ChatChoice {
  id: string;
  label: string;
}

export interface ChatResponse {
  replies: string[];
  conversationId: string;
  followupQuestions?: string[];
  metadata?: AIMessageMetadata[];
}

interface SendChatOptions {
  agents?: string[];
  answerIncorrectly?: boolean;
  questionText?: string | null;
  answerChoices?: ChatChoice[];
  signal?: AbortSignal;
}


interface ChatApiResponse {
  reply?: string[];
  message?: string;
  conversation_id?: string;
  followup_questions?: string[];
  metadata?: AIMessageMetadata[];
}

export async function loadUserHistory(conversationId: string): Promise<{
  conversation_id: string;
  messages: { role: string; content: string | string[] }[];
}> {
  return apiFetch(`/api/chat/load_user_history/${conversationId}`);
}

function getChatEndpoint(quizId: string): string {
  if (quizId === "double") return "/api/chat/double";
  if (quizId === "followup") return "/api/chat/followup";
  if (quizId === "links") return "/api/chat/links";
  return `/api/chat/${quizId}`;
}

export async function sendChat(
  quizId: string,
  conversationId: string | null,
  message: string,
  options: SendChatOptions = {},

): Promise<ChatResponse> {
  const {
    agents = [],
    answerIncorrectly = false,
    questionText = null,
    answerChoices = [],
    signal,
  } = options;

  const data = await apiFetch<ChatApiResponse>(
    getChatEndpoint(quizId),

    {
      method: "POST",
      signal,
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        agents,
        answer_incorrectly: answerIncorrectly,
        question_text: questionText,
        answer_choices: answerChoices,
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