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

export async function loadUserHistory(conversationId: string): Promise<{
  conversation_id: string;
  messages: { role: string; content: string | string[] }[];
}> {
  return apiFetch(`/api/chat/load_user_history/${conversationId}`);
}

export async function sendChat(
  quizId: string,
  conversationId: string | null,
  message: string,
  agents: string[] = [],
  signal?: AbortSignal,
  onToken?: (delta: string, agent?: string) => void,
): Promise<ChatResponse> {
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

  // BATCHING LOGIC START ---
  // Buffer to hold tokens before sending to the UI
  const tokenBuffer: Record<string, string> = {};
  let lastFlushTime = Date.now();
  const FLUSH_INTERVAL_MS = 50; 

  const flushTokens = () => {
    for (const [key, accumulatedDelta] of Object.entries(tokenBuffer)) {
      if (accumulatedDelta) {
        const agentName = key === "default" ? undefined : key;
        onToken?.(accumulatedDelta, agentName);
        tokenBuffer[key] = ""; // Clear the buffer after flushing
      }
    }
    lastFlushTime = Date.now();
  };
  // BATCHING LOGIC END ---

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
          
          // Save the full response in the map for the final return
          replyMap[key] = (replyMap[key] ?? "") + delta;
          
          // Add the delta to our UI buffer
          tokenBuffer[key] = (tokenBuffer[key] ?? "") + delta;

          // If 50ms have passed, flush the buffer to React
          if (Date.now() - lastFlushTime > FLUSH_INTERVAL_MS) {
            flushTokens();
          }

        } else if (event.type === "followup") {
          followupQuestions = event.questions as string[];
        } else if (event.type === "done") {
          returnedConvId = (event.conversation_id as string) ?? returnedConvId;
        } else if (event.type === "error") {
          throw new Error((event.detail as string) ?? "Upstream AI request failed");
        }
      }
    }
  } finally {
    reader.releaseLock();
    // Do one final flush to ensure no tokens are left behind in the buffer
    flushTokens(); 
  }

  const agentKeys = Object.keys(replyMap).filter(k => k !== "default").sort();
  const replies = agentKeys.length > 0
    ? agentKeys.map(k => replyMap[k])
    : [replyMap["default"] ?? ""];

  return { replies, conversationId: returnedConvId, followupQuestions };
}
