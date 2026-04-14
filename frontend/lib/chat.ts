import { apiFetch } from "./fetcher";

export interface Citation {
  n: number;
  title: string;
  url: string;
}

export function injectCitationLinks(text: string, citations: Citation[]): string {
  let result = text;
  for (const { n, url } of citations) {
    const N = String(n);
    // Primary: [key phrase][N] or [key phrase] [N] → [key phrase](url)
    result = result.replaceAll(
      new RegExp(String.raw`\[([^\]\[]+)\]\s*\[${N}\]`, "g"),
      `[$1](${url})`,
    );
    // Fallback: bare [N] not already followed by ( → [N](url)
    result = result.replaceAll(
      new RegExp(String.raw`\[${N}\](?!\()`, "g"),
      `[${N}](${url})`,
    );
  }
  return result;
}

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

export async function loadUserHistory(conversationId: string): Promise<{
  conversation_id: string;
  messages: { role: string; content: string | string[] }[];
}> {
  return apiFetch(`/api/chat/load_user_history/${conversationId}`);
}

export interface SendChatOptions {
  signal?: AbortSignal;
  onToken?: (delta: string, agent?: string) => void;
  onDone?: (replies: string[], convId: string) => void;
  onFollowupToken?: (delta: string) => void;
  onCitations?: (citations: Citation[]) => void;
}

export async function sendChat(
  quizId: string,
  conversationId: string | null,
  message: string,
  agents: string[] = [],
  options: SendChatOptions = {},
): Promise<ChatResponse> {
  const { signal, onToken, onDone, onFollowupToken, onCitations } = options;
  const resp = await fetch(`/api/chat/${quizId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    signal,
    body: JSON.stringify({ message, conversation_id: conversationId, agents }),
  });

  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const data = await resp.json();
      detail = data.detail ?? data.message ?? detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  // All chat endpoints now return SSE (text/event-stream).
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let sseBuffer = "";
  const replyMap: Record<string, string> = {};
  let returnedConvId = conversationId ?? "";
  let followupQuestions: string[] | undefined;
  let citations: Citation[] = [];

  // Batch token updates: flush to React at most once per animation frame (~16ms).
  // This avoids one re-render per token while keeping streaming visually smooth.
  const FOLLOWUP_KEY = "__followup__";
  const tokenBuffer: Record<string, string> = {};

  const flushTokens = () => {
    for (const [key, accumulatedDelta] of Object.entries(tokenBuffer)) {
      if (accumulatedDelta) {
        if (key === FOLLOWUP_KEY) {
          onFollowupToken?.(accumulatedDelta);
        } else {
          const agentName = key === "default" ? undefined : key;
          onToken?.(accumulatedDelta, agentName);
        }
        tokenBuffer[key] = "";
      }
    }
  };
  const flushInterval = setInterval(flushTokens, 16);

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      sseBuffer += decoder.decode(value, { stream: true });
      const lines = sseBuffer.split("\n");
      sseBuffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        let event: Record<string, unknown>;
        try {
          event = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        if (event.type === "token") {
          const delta = (event.content as string) ?? "";
          const agent = event.agent != null ? (event.agent as string) : undefined;
          const key = agent ?? "default";
          replyMap[key] = (replyMap[key] ?? "") + delta;
          tokenBuffer[key] = (tokenBuffer[key] ?? "") + delta;
        } else if (event.type === "followup") {
          if ("token" in event) {
            // Streaming follow-up token — buffer at 60fps alongside main tokens.
            tokenBuffer[FOLLOWUP_KEY] = (tokenBuffer[FOLLOWUP_KEY] ?? "") + (event.token as string);
          } else {
            // Batch questions (backwards compat for endpoints that send the full array).
            followupQuestions = [...(followupQuestions ?? []), ...(event.questions as string[])];
          }
        } else if (event.type === "citations") {
          citations = (event.citations as Citation[]) ?? [];
          onCitations?.(citations);
        } else if (event.type === "done") {
          returnedConvId = (event.conversation_id as string) ?? returnedConvId;
          if (onDone) {
            flushTokens();
            const agentKeys = Object.keys(replyMap).filter(k => k !== "default").sort();
            const rawReplies = agentKeys.length > 0
              ? agentKeys.map(k => replyMap[k])
              : [replyMap["default"] ?? ""];
            const replies = citations.length > 0
              ? rawReplies.map(r => injectCitationLinks(r, citations))
              : rawReplies;
            onDone(replies, returnedConvId);
          }
        } else if (event.type === "error") {
          throw new Error((event.detail as string) ?? "Upstream AI request failed");
        }
      }
    }
  } finally {
    clearInterval(flushInterval);
    flushTokens(); // flush any tokens that arrived since the last interval tick
    reader.releaseLock();
  }

  const agentKeys = Object.keys(replyMap).filter(k => k !== "default").sort();
  const rawReplies = agentKeys.length > 0
    ? agentKeys.map(k => replyMap[k])
    : [replyMap["default"] ?? ""];
  const replies = citations.length > 0
    ? rawReplies.map(r => injectCitationLinks(r, citations))
    : rawReplies;

  return { replies, conversationId: returnedConvId, followupQuestions };
}
