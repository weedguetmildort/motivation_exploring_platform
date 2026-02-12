//let conversationId: string | null = null; // simple in-memory thread id

// Centralized API helper for chat
const BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || "http://localhost:8000";

export async function sendChat(conversationId: string | null, message: string): Promise<string> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ 
      message,
      conversation_id: conversationId,
    }),
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status} when calling /chat`);
  }

  const data = (await res.json()) as { reply?: string; message?: string; conversation_id?: string };
  if (!conversationId && data.conversation_id) conversationId = data.conversation_id;

  // Accept either {reply} or {message} to be tolerant
  return (data.reply ?? data.message ?? "").toString();
}
