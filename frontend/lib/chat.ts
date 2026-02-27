// Centralized API helper for chat

export async function sendChat(
  quizId: string,
  conversationId: string | null,
  message: string
): Promise<{ replies: string[]; conversationId: string }> {
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

  const replies = Array.isArray(data.reply)
    ? data.reply
    : [(data.reply ?? data.message ?? "").toString()];

  return { replies, conversationId: data.conversation_id ?? conversationId ?? "" };
}
