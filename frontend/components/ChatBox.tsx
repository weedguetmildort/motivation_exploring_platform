import { useEffect, useRef, useState } from "react";
import { sendChat } from "../lib/chat";
import FollowUpQuestionBox from "./FollowUpQuestionBox";
import MarkdownMessage from "./MarkdownMessage";

type Bot = "A" | "B" | "C" | "D";
type Msg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  ts: number;
  bot?: Bot; // Only for assistant, set when there are multiple replies
};

const BOT_COLORS: Record<Bot, string> = {
  A: "bg-gray-100 text-gray-900",
  B: "bg-purple-100 text-purple-900",
  C: "bg-green-100 text-green-900",
  D: "bg-orange-100 text-orange-900",
};

type ChatBoxProps = {
  quizId: string;
  onAssistantMessage?: (message: string) => void;
  externalQuestion?: string | null;
  enableFollowups?: boolean;
  conversationId?: string | null;
};

export default function ChatBox({
  quizId,
  onAssistantMessage,
  externalQuestion,
  enableFollowups = true,
  conversationId = null,
}: ChatBoxProps) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeConvId, setActiveConvId] = useState<string | null>(conversationId);
  const scrollerRef = useRef<HTMLDivElement>(null);

  // Sync activeConvId when the prop becomes available (e.g. after quizState loads)
  useEffect(() => {
    if (conversationId) setActiveConvId(conversationId);
  }, [conversationId]);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messages, pending]);

  async function sendMessage(content: string) {
    const trimmed = content.trim();
    if (!trimmed || pending) return;

    setError(null);
    const userMsg: Msg = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      ts: Date.now(),
    };
    setMessages((m) => [...m, userMsg]);

    try {
      setPending(true);
      const { replies, conversationId: returnedConvId } = await sendChat(quizId, activeConvId, trimmed);
      if (returnedConvId && !activeConvId) setActiveConvId(returnedConvId);
      const botMsgs: Msg[] = replies.map((r, i) => ({
        id: crypto.randomUUID(),
        role: "assistant" as const,
        content: r,
        ts: Date.now(),
        bot: replies.length > 1 ? ((["A", "B", "C", "D"][i] as Bot) ?? "A") : undefined,
      }));
      setMessages((m) => [...m, ...botMsgs]);
      if (onAssistantMessage) {
        onAssistantMessage(replies[replies.length - 1]);
      }
    } catch {
      setError("Failed to contact the server.");
    } finally {
      setPending(false);
    }
  }

  async function onSend() {
    const content = input.trim();
    if (!content || pending) return;
    setInput("");
    await sendMessage(content);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  useEffect(() => {
    if (!externalQuestion) return;
    sendMessage(externalQuestion);
  }, [externalQuestion]);

  const lastAiMessage =
    [...messages].reverse().find((m) => m.role === "assistant")?.content ??
    null;

  function handleFollowupClick(question: string) {
    void sendMessage(question);
  }

  return (
    <div className="flex h-full w-full flex-col rounded-2xl border bg-white shadow-sm">
      <div className="p-4 border-b sticky top-0 bg-white/80 backdrop-blur rounded-t-2xl">
        <h2 className="text-lg font-semibold">Chat</h2>
      </div>

      <div ref={scrollerRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((m) => {
          const label =
            m.role === "user" ? "You" : m.bot ? `Agent ${m.bot}` : "Assistant";
          const bubbleClass =
            m.role === "user"
              ? "bg-blue-600 text-white"
              : m.bot
              ? BOT_COLORS[m.bot]
              : "bg-gray-100 text-gray-900";

          return (
            <div key={m.id}>
              <div
                className={`text-xs text-gray-600 px-1 mb-1 ${
                  m.role === "user" ? "text-right" : "text-left"
                }`}
              >
                {label}
              </div>

              <div
                className={`flex ${
                  m.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div className={`max-w-[80%] rounded-2xl px-4 py-2 ${bubbleClass}`}>
                  {m.role === "assistant" ? (
                    <MarkdownMessage content={m.content} />
                  ) : (
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {pending && (
          <div className="text-sm text-gray-500">Assistant is typing…</div>
        )}

        {error && (
          <div role="alert" className="text-sm text-red-600">
            {error}
          </div>
        )}

        {enableFollowups && (
          <FollowUpQuestionBox
            lastAiMessage={lastAiMessage}
            onOptionClick={handleFollowupClick}
          />
        )}
      </div>

      <div className="p-3 border-t rounded-b-2xl bg-white">
        <div className="flex items-end gap-2">
          <textarea
            className="w-full resize-none rounded-xl border px-3 py-2 focus:outline-none focus:ring"
            placeholder="Type a message…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
          />
          <button
            className="rounded-xl px-4 py-2 font-medium bg-blue-600 text-white disabled:opacity-60"
            onClick={onSend}
            disabled={pending || !input.trim()}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
