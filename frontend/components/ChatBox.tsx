// frontend/components/ChatBox.tsx
import { useEffect, useRef, useState } from "react";
import { sendChat, loadUserHistory } from "../lib/chat";
import MarkdownMessage from "./MarkdownMessage";
import MentionSuggestions from "./MentionSuggestions";
import {
  getFilteredAgents,
  getPartialMention,
  getValidAgents,
  getValidMentionTargets,
  hasIncompleteMention,
  parseMentions,
  removeMentions,
} from "../lib/mentions";

type Bot = "A" | "B" | "C" | "D";
type AgentFilter = "double" | "base";
type Msg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  ts: number;
  bot?: Bot;
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
  onError?: () => void;
  onLoadingChange?: (loading: boolean) => void;
  onHistoryLoaded?: () => void;
  externalQuestion?: string | null;
  conversationId?: string | null;
  disableCancel?: boolean;
};

export default function ChatBox({
  quizId,
  onAssistantMessage,
  onError,
  onLoadingChange,
  onHistoryLoaded,
  externalQuestion,
  conversationId = null,
  disableCancel = false,
}: ChatBoxProps) {
  const agentFilter: AgentFilter = quizId === "double" ? "double" : "base";
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [followupQuestions, setFollowupQuestions] = useState<string[] | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [activeConvId, setActiveConvId] = useState<string | null>(
    conversationId,
  );
  const scrollerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const historyFetched = useRef(false);
  const [showMentions, setShowMentions] = useState(false);
  const [mentionIndex, setMentionIndex] = useState(0);
  const [filteredAgents, setFilteredAgents] = useState<string[]>([]);

  useEffect(() => {
    if (!activeConvId || historyFetched.current) return;
    historyFetched.current = true;
    let cancelled = false;
    loadUserHistory(activeConvId).then(({ messages }) => {
      if (cancelled || messages.length === 0) return;
      const loaded: Msg[] = [];
      for (const m of messages) {
        if (m.role === "user") {
          loaded.push({ id: crypto.randomUUID(), role: "user", content: m.content as string, ts: 0 });
        } else {
          const replies = Array.isArray(m.content) ? m.content : [m.content];
          replies.forEach((r, i) => {
            loaded.push({
              id: crypto.randomUUID(),
              role: "assistant",
              content: r,
              ts: 0,
              bot: agentFilter === "double"
                ? (["A", "B"][i] as Bot ?? undefined)
                : replies.length > 1 ? (["A", "B", "C", "D"][i] as Bot ?? "A") : undefined,
            });
          });
        }
      }
      onHistoryLoaded?.();
      setMessages(loaded);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [activeConvId]); // runs once when activeConvId first becomes available

  useEffect(() => {
    if (conversationId) {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
      setPending(false);
      setActiveConvId(conversationId);
    }
  }, [conversationId]);

  useEffect(() => {
    return () => { abortControllerRef.current?.abort(); };
  }, []);

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight });
  }, [messages, pending]);

  useEffect(() => {
    onLoadingChange?.(pending);
  }, [pending]);

  async function sendMessage(content: string) {
    const trimmed = content.trim();
    if (!trimmed) return;

    // Cancel any in-flight request before starting a new one
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setPending(false);

    let agents: string[] = [];
    let messageForBackend = trimmed;

    if (agentFilter === "double") {
      const validAgents = getValidAgents(agentFilter);
      const { mentions } = parseMentions(trimmed);
      agents = getValidMentionTargets(mentions, validAgents);
      messageForBackend = removeMentions(trimmed) || trimmed;
    }

    setError(null);
    setFollowupQuestions(undefined);
    const userMsg: Msg = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      ts: Date.now(),
    };
    setMessages((m) => [...m, userMsg]);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      setPending(true);
      const { replies, conversationId: returnedConvId, followupQuestions: newFollowupQuestions } = await sendChat(
        quizId,
        activeConvId,
        messageForBackend,
        agents,
        controller.signal,
      );
      if (returnedConvId && !activeConvId) setActiveConvId(returnedConvId);

      const mapAgentToBot = (agent: string): Bot | undefined => {
        const key = agent.toLowerCase();
        if (key === "agenta") return "A";
        if (key === "agentb") return "B";
        return undefined;
      };

      const botOrder: Bot[] =
        agentFilter === "double"
          ? agents.length > 0
            ? (agents
                .map(mapAgentToBot)
                .filter((bot): bot is Bot => Boolean(bot)) as Bot[])
            : ["A", "B"]
          : [];

      const botMsgs: Msg[] = replies.map((r, i) => ({
        id: crypto.randomUUID(),
        role: "assistant" as const,
        content: r,
        ts: Date.now(),
        bot:
          agentFilter === "double"
            ? botOrder[i] ?? (i % 2 === 0 ? "A" : "B")
            : replies.length > 1
              ? ((["A", "B", "C", "D"][i] as Bot) ?? "A")
              : undefined,
      }));

      setMessages((m) => [...m, ...botMsgs]);
      if (onAssistantMessage) {
        onAssistantMessage(replies[replies.length - 1]);
      }
      if (newFollowupQuestions) {
        setFollowupQuestions(newFollowupQuestions);
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setError("Failed to contact the server.");
      onError?.();
    } finally {
      abortControllerRef.current = null;
      setPending(false);
    }
  }

  async function onSend() {
    const content = input.trim();
    if (!content || pending) return;
    setInput("");
    setShowMentions(false);
    await sendMessage(content);
  }

  function handleCancel() {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setPending(false);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const newValue = e.target.value;
    setInput(newValue);

    if (hasIncompleteMention(newValue)) {
      const partial = getPartialMention(newValue);
      const agents = getFilteredAgents(agentFilter, partial);
      if (agents.length > 1) {
        setFilteredAgents(agents);
        setShowMentions(true);
        setMentionIndex(0);
      } else {
        setShowMentions(false);
      }
    } else {
      setShowMentions(false);
    }
  }

  function handleSelectAgent(agent: string) {
    const atIndex = input.lastIndexOf("@");
    const textBefore = input.substring(0, atIndex);
    const textAfter = input.substring(
      atIndex + getPartialMention(input).length + 1,
    );
    setInput(`${textBefore}@${agent} ${textAfter}`);
    setShowMentions(false);
    textareaRef.current?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (showMentions) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setMentionIndex((prev) => (prev + 1) % filteredAgents.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setMentionIndex(
          (prev) => (prev - 1 + filteredAgents.length) % filteredAgents.length,
        );
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setShowMentions(false);
        return;
      }
      if (e.key === "Tab" || e.key === "Enter") {
        e.preventDefault();
        if (filteredAgents[mentionIndex]) {
          handleSelectAgent(filteredAgents[mentionIndex]);
        }
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  useEffect(() => {
    if (!externalQuestion) return;
    sendMessage(externalQuestion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalQuestion]);

  function handleFollowupClick(question: string) {
    void sendMessage(question);
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col rounded-2xl border bg-white shadow-sm overflow-hidden">
      <div className="p-4 border-b sticky top-0 bg-white/80 backdrop-blur rounded-t-2xl">
        <h2 className="text-lg font-semibold">Chat</h2>
      </div>

      <div
        ref={scrollerRef}
        className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3"
      >
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
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2 ${bubbleClass}`}
                >
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

        {followupQuestions && (
          <div className="mt-3 border-t border-gray-200 pt-3">
            <div className="mb-2 text-sm font-semibold text-gray-900">Follow-up Questions</div>
            <div className="flex flex-wrap gap-2">
              {followupQuestions.map((q, i) => (
                <button
                  key={i}
                  type="button"
                  className="text-xs px-3 py-1 rounded-full border border-gray-300 bg-white hover:bg-gray-100 transition"
                  onClick={() => handleFollowupClick(q)}
                >
                  <MarkdownMessage content={q} inline />
                </button>
              ))}
            </div>
          </div>
        )}

        {pending && (
          <div className="text-sm text-gray-500">Assistant is typing…</div>
        )}

        {error && (
          <div role="alert" className="text-sm text-red-600">
            {error}
          </div>
        )}

      </div>

      <div className="p-3 border-t rounded-b-2xl bg-white relative">
        <MentionSuggestions
          visible={showMentions}
          agents={filteredAgents}
          selectedIndex={mentionIndex}
          onSelect={handleSelectAgent}
        />
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            className="w-full resize-none rounded-xl border px-3 py-2 focus:outline-none focus:ring text-sm"
            placeholder="Type a message…"
            value={input}
            onChange={handleInputChange}
            onKeyDown={onKeyDown}
            rows={2}
          />
          <button
            className={`rounded-xl px-4 py-2 font-medium text-white ${pending ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 disabled:opacity-60"}`}
            onClick={pending ? handleCancel : onSend}
            disabled={(!pending && !input.trim()) || (pending && disableCancel)}
          >
            {pending ? "Cancel" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
