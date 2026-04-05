// frontend/components/ChatBox.tsx
import { memo, useEffect, useRef, useState } from "react";
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

// Memoized so it only re-renders when message content changes, not on every keystroke.
const MessageBubble = memo(function MessageBubble({
  role,
  content,
  bot,
}: {
  role: "user" | "assistant";
  content: string;
  bot?: Bot;
}) {
  const label = role === "user" ? "You" : bot ? `Agent ${bot}` : "Assistant";
  const bubbleClass =
    role === "user"
      ? "bg-blue-600 text-white"
      : bot
        ? BOT_COLORS[bot]
        : "bg-gray-100 text-gray-900";

  return (
    <div>
      <div className={`text-xs text-gray-600 px-1 mb-1 ${role === "user" ? "text-right" : "text-left"}`}>
        {label}
      </div>
      <div className={`flex ${role === "user" ? "justify-end" : "justify-start"}`}>
        <div className={`max-w-[95%] rounded-2xl px-4 py-2 ${bubbleClass}`}>
          {role === "assistant" ? (
            <MarkdownMessage content={content} />
          ) : (
            <div className="text-[0.8125rem] whitespace-pre-wrap">{content}</div>
          )}
        </div>
      </div>
    </div>
  );
});

type ChatBoxProps = {
  quizId: string;
  onAssistantMessage?: (message: string) => void;
  onError?: () => void;
  onLoadingChange?: (loading: boolean) => void;
  onHistoryLoaded?: () => void;
  externalQuestion?: string | null;
  conversationId?: string | null;
  disableCancel?: boolean;
  questionCollapsed?: boolean;
  onToggleQuestion?: () => void;
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
  questionCollapsed,
  onToggleQuestion,
}: ChatBoxProps) {
  const agentFilter: AgentFilter = quizId === "double" ? "double" : "base";
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [streamingMap, setStreamingMap] = useState<Record<string, string>>({});
  const [followupQuestions, setFollowupQuestions] = useState<string[] | undefined>(undefined);
  const [followupStreamText, setFollowupStreamText] = useState("");
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

  // Guards against double-committing bot messages when onDone fires mid-stream.
  const textDoneCommitted = useRef(false);
  // Mirrors followupStreamText for synchronous access after sendChat resolves.
  const followupStreamTextRef = useRef("");
  // Tracks how many \n-terminated lines have already been turned into chips.
  const processedNewlinesRef = useRef(0);

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
  }, [messages, pending, streamingMap, followupStreamText, followupQuestions]);

  useEffect(() => {
    onLoadingChange?.(pending);
  }, [pending]);

  // Add a chip for each newly completed question line (\n-terminated).
  // processedNewlinesRef tracks how many lines have already been turned into chips,
  // so we only look at the new lines on each run — no re-parsing of existing chips.
  useEffect(() => {
    if (!followupStreamText) return;
    const lines = followupStreamText.split("\n");
    const completedCount = lines.length - 1; // lines before the trailing incomplete segment
    if (completedCount <= processedNewlinesRef.current) return;
    for (let i = processedNewlinesRef.current; i < completedCount; i++) {
      const m = lines[i].trim().match(/^[0-9]+[.)\-:\s]+(.*)/);
      if (m) {
        const question = m[1].trim();
        if (question) {
          setFollowupQuestions(prev => {
            if (prev?.includes(question)) return prev;
            return [...(prev ?? []), question];
          });
        }
      }
    }
    processedNewlinesRef.current = completedCount;
  }, [followupStreamText]);

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
    setFollowupStreamText("");
    followupStreamTextRef.current = "";
    processedNewlinesRef.current = 0;
    textDoneCommitted.current = false;

    const userMsg: Msg = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      ts: Date.now(),
    };
    setMessages((m) => [...m, userMsg]);

    const controller = new AbortController();
    abortControllerRef.current = controller;

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

    const buildBotMsgs = (replies: string[]): Msg[] =>
      replies.map((r, i) => ({
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

    try {
      setPending(true);
      const { replies, conversationId: returnedConvId, followupQuestions: newFollowupQuestions } = await sendChat(
        quizId,
        activeConvId,
        messageForBackend,
        agents,
        controller.signal,
        // onToken — streams main text at 60fps
        (delta, agent) => {
          const key = agent ?? "default";
          setStreamingMap((prev: Record<string, string>) => ({ ...prev, [key]: (prev[key] ?? "") + delta }));
        },
        // onDone — fires when main text is finished; unlock UI immediately
        (replies) => {
          textDoneCommitted.current = true;
          setMessages(m => [...m, ...buildBotMsgs(replies)]);
          onAssistantMessage?.(replies[replies.length - 1]);
          setPending(false);
          setStreamingMap({});
        },
        // onFollowupToken — streams follow-up question tokens at 60fps
        (delta) => {
          followupStreamTextRef.current += delta;
          setFollowupStreamText(prev => prev + delta);
        },
      );

      if (returnedConvId && !activeConvId) setActiveConvId(returnedConvId);

      if (!textDoneCommitted.current) {
        // onDone was never called (endpoint doesn't emit "done" mid-stream).
        // Commit messages the conventional way.
        const botMsgs = buildBotMsgs(replies);
        setMessages((m: Msg[]) => [...m, ...botMsgs]);
        if (onAssistantMessage) {
          onAssistantMessage(replies[replies.length - 1]);
        }
        if (newFollowupQuestions?.length) {
          setFollowupQuestions(newFollowupQuestions);
        }
      }

      // If the AI didn't end with \n, the last question is still the "incomplete tail"
      // from split("\n")'s perspective. Appending \n moves it into completeLines so the
      // useEffect picks it up and the in-progress chip disappears naturally.
      if (followupStreamTextRef.current && !followupStreamTextRef.current.endsWith("\n")) {
        followupStreamTextRef.current += "\n";
        setFollowupStreamText(prev => prev + "\n");
      }

    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      setError("Failed to contact the server.");
      onError?.();
    } finally {
      abortControllerRef.current = null;
      textDoneCommitted.current = false;
      setPending(false);
      setStreamingMap({});
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
    setStreamingMap({});
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

  // Current in-progress follow-up question text (the incomplete last line).
  // If followupStreamText ends with \n, all lines are complete — no chip needed.
  const followupInProgress = (() => {
    if (!followupStreamText || followupStreamText.endsWith("\n")) return "";
    const lines = followupStreamText.split("\n");
    const lastLine = lines[lines.length - 1];
    return lastLine.replace(/^[0-9]+[.)\-:\s]+/, "").trim();
  })();

  return (
    <div className="flex h-full min-h-0 w-full flex-col rounded-2xl border bg-white shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b sticky top-0 bg-white/90 backdrop-blur rounded-t-2xl flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600">
            <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-900 2xl:text-2xl">AI Assistant</h2>
        </div>
        {onToggleQuestion && (
          <button
            type="button"
            className="md:hidden inline-flex items-center gap-1 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-600 shadow-sm transition hover:bg-gray-50 hover:text-gray-900 active:scale-95"
            onClick={onToggleQuestion}
            aria-label={questionCollapsed ? "Minimize question" : "Maximize question"}
          >
            {questionCollapsed ? (
              <>
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
                Minimize
              </>
            ) : (
              <>
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
                </svg>
                Maximize
              </>
            )}
          </button>
        )}
      </div>

      <div
        ref={scrollerRef}
        className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-4 space-y-3"
      >
        {messages.map((m) => (
          <MessageBubble key={m.id} role={m.role} content={m.content} bot={m.bot} />
        ))}

        {(followupQuestions || followupInProgress) && (
          <div className="mt-3 border-t border-gray-200 pt-3">
            <div className="mb-2 text-lg font-semibold text-gray-900">Follow-up Questions</div>
            <div className="flex flex-wrap gap-2">
              {followupQuestions?.map((q, i) => (
                <button
                  key={i}
                  type="button"
                  className="text-[0.8125rem] px-3 py-1 rounded-full border border-gray-300 bg-white hover:bg-gray-100 transition"
                  onClick={() => handleFollowupClick(q)}
                >
                  <MarkdownMessage content={q} inline />
                </button>
              ))}
              {followupInProgress && !followupQuestions?.includes(followupInProgress) && (
                <span className="text-[0.8125rem] px-3 py-1 rounded-full border border-gray-200 bg-gray-50 text-gray-400 italic">
                  {followupInProgress}
                </span>
              )}
            </div>
          </div>
        )}

        {pending && Object.keys(streamingMap).length === 0 && (
          <div className="text-sm text-gray-500">Assistant is typing…</div>
        )}

        {pending && (Object.entries(streamingMap) as [string, string][]).map(([agentKey, content]) => {
          const bot: Bot | undefined = agentKey === "A" ? "A" : agentKey === "B" ? "B" : undefined;
          const label = bot ? `Agent ${bot}` : "Assistant";
          const bubbleClass = bot ? BOT_COLORS[bot] : "bg-gray-100 text-gray-900";
          return (
            <div key={`streaming-${agentKey}`}>
              <div className="text-xs text-gray-600 px-1 mb-1 text-left">{label}</div>
              <div className="flex justify-start">
                <div className={`max-w-[95%] rounded-2xl px-4 py-2 ${bubbleClass}`}>
                  <MarkdownMessage content={content} />
                </div>
              </div>
            </div>
          );
        })}

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
            className="w-full resize-none rounded-xl border px-3 py-2 focus:outline-none focus:ring text-gray-900"
            placeholder="Type a message…"
            value={input}
            onChange={handleInputChange}
            onKeyDown={onKeyDown}
            rows={2}
          />
          <button
            className={`rounded-xl px-4 py-2 font-medium text-white ${pending && disableCancel ? "bg-gray-400 cursor-default" : pending ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 disabled:opacity-60"}`}
            onClick={pending && !disableCancel ? handleCancel : onSend}
            disabled={(!pending && !input.trim()) || (pending && disableCancel)}
          >
            {pending ? "Cancel" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
