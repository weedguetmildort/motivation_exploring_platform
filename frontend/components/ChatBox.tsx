import { useEffect, useRef, useState } from "react";
import { sendChat } from "../lib/chat"; // fetch helper

type Msg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  ts: number;
};

export default function ChatBox() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messages, pending]);

  async function onSend() {
    const content = input.trim();
    if (!content || pending) return;

    setError(null);
    setInput("");
    const userMsg: Msg = { id: crypto.randomUUID(), role: "user", content, ts: Date.now() };
    setMessages((m) => [...m, userMsg]);

    try {
      setPending(true);
      const reply = await sendChat(content);
      const botMsg: Msg = { id: crypto.randomUUID(), role: "assistant", content: reply, ts: Date.now() };
      setMessages((m) => [...m, botMsg]);
    } catch (e) {
      setError("Failed to contact the server.");
    } finally {
      setPending(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="mx-auto max-w-2xl h-[80vh] flex flex-col rounded-2xl border bg-white shadow-sm">
      <div className="p-4 border-b sticky top-0 bg-white/80 backdrop-blur rounded-t-2xl">
        <h2 className="text-lg font-semibold">Chat</h2>
      </div>

      <div ref={scrollerRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2 ${
                m.role === "user" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-900"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {pending && (
          <div className="text-sm text-gray-500">Assistant is typing…</div>
        )}
        {error && (
          <div role="alert" className="text-sm text-red-600">{error}</div>
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
