// Centralized API helper for chat

export async function sendChat(
  quizId: string,
  conversationId: string | null,
  message: string
): Promise<string[]> {
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

  const data = (await res.json()) as { reply?: string[]; message?: string; conversation_id?: string };
  if (!conversationId && data.conversation_id) conversationId = data.conversation_id;

  // reply is now an array of LLM responses
  if (Array.isArray(data.reply)) {
    return data.reply;
  }
  // Fallback: wrap single string in array for backwards compatibility
  const single = (data.reply ?? data.message ?? "").toString();
  return [single];
}
