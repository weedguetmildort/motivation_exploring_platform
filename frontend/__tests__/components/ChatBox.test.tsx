import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import ChatBox from "../../components/ChatBox";
import type { SendChatOptions, ChatResponse } from "../../lib/chat";

const mockSendChat = jest.fn();
const mockLoadUserHistory = jest.fn();
const mockRecordLinkClick = jest.fn();
const mockRecordCopyEvent = jest.fn();

jest.mock("../../lib/chat", () => ({
  sendChat: (...args: unknown[]) => mockSendChat(...args),
  loadUserHistory: (...args: unknown[]) => mockLoadUserHistory(...args),
}));

jest.mock("../../lib/linkClicks", () => ({
  recordLinkClick: (...args: unknown[]) => mockRecordLinkClick(...args),
}));

jest.mock("../../lib/copyEvents", () => ({
  recordCopyEvent: (...args: unknown[]) => mockRecordCopyEvent(...args),
}));

const PLACEHOLDER = "Type a message…";
const DOUBLE_PLACEHOLDER = "Message both agents, or @AgentA / @AgentB to address one…";

describe("ChatBox", () => {
  beforeEach(() => {
    mockSendChat.mockReset();
    mockLoadUserHistory.mockReset();
    mockLoadUserHistory.mockResolvedValue({ conversation_id: "", messages: [] });
    mockRecordLinkClick.mockReset();
    mockRecordLinkClick.mockResolvedValue(undefined);
    mockRecordCopyEvent.mockReset();
    mockRecordCopyEvent.mockResolvedValue(undefined);
  });

  it("renders the header and a disabled Send button when the input is empty", () => {
    render(<ChatBox quizId="base" />);
    expect(screen.getByText("AI Assistant")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(PLACEHOLDER)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("sends a message, renders the reply and clears the input", async () => {
    const onAssistantMessage = jest.fn();
    mockSendChat.mockImplementation(async (_q, _c, _m, _a, options: SendChatOptions) => {
      options.onDone?.(["Hi there!"], "conv-1");
      return { replies: ["Hi there!"], conversationId: "conv-1", followupQuestions: undefined } as ChatResponse;
    });

    render(<ChatBox quizId="base" onAssistantMessage={onAssistantMessage} />);
    const textarea = screen.getByPlaceholderText(PLACEHOLDER);
    fireEvent.change(textarea, { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Hi there!")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(textarea).toHaveValue("");
    expect(onAssistantMessage).toHaveBeenCalledWith("Hi there!");
    expect(mockSendChat).toHaveBeenCalledWith("base", null, "Hello", [], expect.any(Object));
  });

  it("shows a typing indicator, then a streaming bubble as tokens arrive", async () => {
    let capturedOptions: SendChatOptions = {};
    let resolveSend: (value: ChatResponse) => void = () => {};
    mockSendChat.mockImplementation((_q, _c, _m, _a, options: SendChatOptions) => {
      capturedOptions = options;
      return new Promise<ChatResponse>((resolve) => { resolveSend = resolve; });
    });

    render(<ChatBox quizId="base" />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Assistant is typing…")).toBeInTheDocument();

    act(() => { capturedOptions.onToken?.("Partial reply", undefined); });
    expect(await screen.findByText("Partial reply")).toBeInTheDocument();
    expect(screen.queryByText("Assistant is typing…")).not.toBeInTheDocument();

    act(() => {
      capturedOptions.onDone?.(["Final reply"], "conv-1");
      resolveSend({ replies: ["Final reply"], conversationId: "conv-1", followupQuestions: undefined });
    });

    expect(await screen.findByText("Final reply")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Send" })).toBeInTheDocument();
  });

  it("shows a Cancel button while pending and resets state when clicked", async () => {
    mockSendChat.mockImplementation(() => new Promise<ChatResponse>(() => {}));

    render(<ChatBox quizId="base" />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    const cancelButton = await screen.findByRole("button", { name: "Cancel" });
    fireEvent.click(cancelButton);

    expect(await screen.findByRole("button", { name: "Send" })).toBeInTheDocument();
    expect(screen.queryByText("Assistant is typing…")).not.toBeInTheDocument();
  });

  it("shows an error message and calls onError when the request fails", async () => {
    const onError = jest.fn();
    mockSendChat.mockRejectedValue(new Error("network down"));

    render(<ChatBox quizId="base" onError={onError} />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to contact the server.");
    expect(onError).toHaveBeenCalled();
  });

  it("silently ignores AbortError without showing an error message", async () => {
    const abortError = new Error("aborted");
    abortError.name = "AbortError";
    mockSendChat.mockRejectedValue(abortError);

    render(<ChatBox quizId="base" />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("sends on Enter and does not send on Shift+Enter", () => {
    mockSendChat.mockImplementation(() => new Promise<ChatResponse>(() => {}));
    render(<ChatBox quizId="base" />);
    const textarea = screen.getByPlaceholderText(PLACEHOLDER);

    fireEvent.change(textarea, { target: { value: "Hello" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(mockSendChat).not.toHaveBeenCalled();

    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(mockSendChat).toHaveBeenCalled();
  });

  it("shows mention suggestions for @ in double-agent quizzes and allows keyboard selection", () => {
    render(<ChatBox quizId="double" />);
    const textarea = screen.getByPlaceholderText(DOUBLE_PLACEHOLDER);

    fireEvent.change(textarea, { target: { value: "@" } });
    expect(screen.getByText("@agenta")).toBeInTheDocument();
    expect(screen.getByText("@agentb")).toBeInTheDocument();
    expect(screen.getByText("@agenta").closest("button")?.className).toContain("bg-accent-500");

    fireEvent.keyDown(textarea, { key: "ArrowDown" });
    expect(screen.getByText("@agentb").closest("button")?.className).toContain("bg-accent-500");

    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(textarea).toHaveValue("@agentb ");
    expect(screen.queryByRole("button", { name: "@agentb" })).not.toBeInTheDocument();
  });

  it("strips mentions from the outgoing message and routes agents to sendChat", async () => {
    mockSendChat.mockImplementation(async (_q, _c, _m, _a, options: SendChatOptions) => {
      options.onDone?.(["Reply A", "Reply B"], "conv-1");
      return { replies: ["Reply A", "Reply B"], conversationId: "conv-1", followupQuestions: undefined } as ChatResponse;
    });

    const { container } = render(<ChatBox quizId="double" />);
    const textarea = screen.getByPlaceholderText(DOUBLE_PLACEHOLDER);
    fireEvent.change(textarea, { target: { value: "@agenta What's up?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() =>
      expect(mockSendChat).toHaveBeenCalledWith("double", null, "What's up?", ["agenta"], expect.any(Object))
    );

    expect(await screen.findByText("Reply A")).toBeInTheDocument();
    expect(screen.getByText("Reply B")).toBeInTheDocument();
    expect(container.querySelector(".grid.grid-cols-2")).not.toBeNull();
  });

  it("labels multiple replies as separate agents in non-double quizzes", async () => {
    mockSendChat.mockImplementation(async (_q, _c, _m, _a, options: SendChatOptions) => {
      options.onDone?.(["Reply 1", "Reply 2"], "conv-1");
      return { replies: ["Reply 1", "Reply 2"], conversationId: "conv-1", followupQuestions: undefined } as ChatResponse;
    });

    render(<ChatBox quizId="base" />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Reply 1")).toBeInTheDocument();
    expect(screen.getByText("Reply 2")).toBeInTheDocument();
    expect(screen.getByText("Agent A")).toBeInTheDocument();
    expect(screen.getByText("Agent B")).toBeInTheDocument();
  });

  it("streams follow-up questions as chips and sends a follow-up on click", async () => {
    let capturedOptions: SendChatOptions = {};
    let resolveSend: (value: ChatResponse) => void = () => {};
    mockSendChat.mockImplementationOnce((_q, _c, _m, _a, options: SendChatOptions) => {
      capturedOptions = options;
      return new Promise<ChatResponse>((resolve) => { resolveSend = resolve; });
    });

    render(<ChatBox quizId="base" />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    act(() => { capturedOptions.onDone?.(["Main reply"], "conv-1"); });
    expect(await screen.findByText("Main reply")).toBeInTheDocument();
    expect(screen.getByText("Loading follow-up questions…")).toBeInTheDocument();

    act(() => { capturedOptions.onFollowupToken?.("1. What is X?\n"); });
    expect(await screen.findByText("What is X?")).toBeInTheDocument();

    act(() => {
      resolveSend({ replies: ["Main reply"], conversationId: "conv-1", followupQuestions: undefined });
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument());

    mockSendChat.mockImplementationOnce(async (_q, _c, _m, _a, options: SendChatOptions) => {
      options.onDone?.(["Answer to X"], "conv-1");
      return { replies: ["Answer to X"], conversationId: "conv-1", followupQuestions: undefined } as ChatResponse;
    });

    fireEvent.click(screen.getByText("What is X?"));

    await waitFor(() =>
      expect(mockSendChat).toHaveBeenCalledWith("base", "conv-1", "What is X?", [], expect.any(Object))
    );
    expect(await screen.findByText("Answer to X")).toBeInTheDocument();
  });

  it("loads conversation history on mount and renders past messages", async () => {
    const onHistoryLoaded = jest.fn();
    mockLoadUserHistory.mockResolvedValue({
      conversation_id: "conv-99",
      messages: [
        { role: "user", content: "Hi" },
        { role: "assistant", content: "Hello there" },
      ],
    });

    render(<ChatBox quizId="base" conversationId="conv-99" onHistoryLoaded={onHistoryLoaded} />);

    expect(await screen.findByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello there")).toBeInTheDocument();
    expect(onHistoryLoaded).toHaveBeenCalled();
    expect(mockLoadUserHistory).toHaveBeenCalledWith("conv-99");
  });

  it("loads dual-agent history with array replies into a paired grid", async () => {
    mockLoadUserHistory.mockResolvedValue({
      conversation_id: "conv-1",
      messages: [
        { role: "user", content: "Question" },
        { role: "assistant", content: ["Reply A", "Reply B"] },
      ],
    });

    const { container } = render(<ChatBox quizId="double" conversationId="conv-1" />);

    expect(await screen.findByText("Reply A")).toBeInTheDocument();
    expect(screen.getByText("Reply B")).toBeInTheDocument();
    expect(container.querySelector(".grid.grid-cols-2")).not.toBeNull();
  });

  it("automatically sends an externalQuestion once it becomes available", async () => {
    mockSendChat.mockImplementation(async (_q, _c, _m, _a, options: SendChatOptions) => {
      options.onDone?.(["Auto reply"], "conv-1");
      return { replies: ["Auto reply"], conversationId: "conv-1", followupQuestions: undefined } as ChatResponse;
    });

    const { rerender } = render(<ChatBox quizId="base" externalQuestion={null} />);
    rerender(<ChatBox quizId="base" externalQuestion="What is the meaning of life?" />);

    await waitFor(() =>
      expect(mockSendChat).toHaveBeenCalledWith("base", null, "What is the meaning of life?", [], expect.any(Object))
    );
    expect(await screen.findByText("Auto reply")).toBeInTheDocument();
  });

  it("disables the Send button entirely when disableCancel is set", () => {
    render(<ChatBox quizId="base" disableCancel />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("shows a disabled Cancel button styled for non-cancellable requests", async () => {
    mockSendChat.mockImplementation(() => new Promise<ChatResponse>(() => {}));

    const { rerender } = render(<ChatBox quizId="base" disableCancel externalQuestion={null} />);
    rerender(<ChatBox quizId="base" disableCancel externalQuestion="Auto question" />);

    const button = await screen.findByRole("button", { name: "Cancel" });
    expect(button).toBeDisabled();
    expect(button.className).toContain("bg-gray-400");
  });

  it("resets messages and loads new history when conversationId prop changes", async () => {
    mockSendChat.mockImplementation(async (_q, _c, _m, _a, options: SendChatOptions) => {
      options.onDone?.(["First reply"], "conv-1");
      return { replies: ["First reply"], conversationId: "conv-1", followupQuestions: undefined } as ChatResponse;
    });

    const { rerender } = render(<ChatBox quizId="base" conversationId={null} />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("First reply")).toBeInTheDocument();

    mockLoadUserHistory.mockResolvedValue({
      conversation_id: "conv-2",
      messages: [{ role: "user", content: "Old question" }],
    });

    rerender(<ChatBox quizId="base" conversationId="conv-2" />);

    expect(await screen.findByText("Old question")).toBeInTheDocument();
    expect(screen.queryByText("First reply")).not.toBeInTheDocument();
    expect(mockLoadUserHistory).toHaveBeenCalledWith("conv-2");
  });

  // ── question_id / trigger plumbing ──────────────────────────────────────

  it("sends trigger='manual' and the questionId prop for a manually typed message", async () => {
    mockSendChat.mockImplementation(() => new Promise<ChatResponse>(() => {}));

    render(<ChatBox quizId="base" questionId="q1" />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(mockSendChat).toHaveBeenCalledWith(
      "base", null, "Hello", [],
      expect.objectContaining({ questionId: "q1", trigger: "manual" })
    );
  });

  it("sends trigger='followup_chip' when a follow-up chip is clicked", async () => {
    let capturedOptions: SendChatOptions = {};
    let resolveSend: (value: ChatResponse) => void = () => {};
    mockSendChat.mockImplementationOnce((_q, _c, _m, _a, options: SendChatOptions) => {
      capturedOptions = options;
      return new Promise<ChatResponse>((resolve) => { resolveSend = resolve; });
    });

    render(<ChatBox quizId="base" />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    act(() => { capturedOptions.onDone?.(["Main reply"], "conv-1"); });
    await screen.findByText("Main reply");

    act(() => { capturedOptions.onFollowupToken?.("1. What is X?\n"); });
    await screen.findByText("What is X?");

    act(() => {
      resolveSend({ replies: ["Main reply"], conversationId: "conv-1", followupQuestions: undefined });
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument());

    mockSendChat.mockImplementationOnce(() => new Promise<ChatResponse>(() => {}));
    fireEvent.click(screen.getByText("What is X?"));

    await waitFor(() =>
      expect(mockSendChat).toHaveBeenCalledWith(
        "base", "conv-1", "What is X?", [],
        expect.objectContaining({ trigger: "followup_chip" })
      )
    );
  });

  it("sends trigger='auto_question' for an externalQuestion auto-send", async () => {
    mockSendChat.mockImplementation(() => new Promise<ChatResponse>(() => {}));

    const { rerender } = render(<ChatBox quizId="base" externalQuestion={null} />);
    rerender(<ChatBox quizId="base" externalQuestion="What is the meaning of life?" />);

    await waitFor(() =>
      expect(mockSendChat).toHaveBeenCalledWith(
        "base", null, "What is the meaning of life?", [],
        expect.objectContaining({ trigger: "auto_question" })
      )
    );
  });

  // ── link click tracking (links variant) ─────────────────────────────────

  it("records a link click for an assistant message in the links variant", async () => {
    mockSendChat.mockImplementation(async (_q, _c, _m, _a, options: SendChatOptions) => {
      options.onDone?.(["See [source](https://example.com/article) for more."], "conv-1");
      return { replies: ["See [source](https://example.com/article) for more."], conversationId: "conv-1", followupQuestions: undefined } as ChatResponse;
    });

    render(<ChatBox quizId="links" questionId="q1" conversationId="conv-1" />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    const link = await screen.findByRole("link", { name: "source" });
    fireEvent.click(link);

    expect(mockRecordLinkClick).toHaveBeenCalledWith({
      quiz_id: "links",
      question_id: "q1",
      conversation_id: "conv-1",
      url: "https://example.com/article",
    });
  });

  it("does not record a link click for a non-links variant", async () => {
    mockSendChat.mockImplementation(async (_q, _c, _m, _a, options: SendChatOptions) => {
      options.onDone?.(["See [source](https://example.com/article) for more."], "conv-1");
      return { replies: ["See [source](https://example.com/article) for more."], conversationId: "conv-1", followupQuestions: undefined } as ChatResponse;
    });

    render(<ChatBox quizId="base" conversationId="conv-1" />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    const link = await screen.findByRole("link", { name: "source" });
    fireEvent.click(link);

    expect(mockRecordLinkClick).not.toHaveBeenCalled();
  });

  // ── copy event tracking ──────────────────────────────────────────────────

  it("records a copy event with the selected text from the chat pane", async () => {
    mockSendChat.mockImplementation(async (_q, _c, _m, _a, options: SendChatOptions) => {
      options.onDone?.(["Hi there!"], "conv-1");
      return { replies: ["Hi there!"], conversationId: "conv-1", followupQuestions: undefined } as ChatResponse;
    });

    const { container } = render(<ChatBox quizId="base" questionId="q1" />);
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Hi there!");

    const getSelectionSpy = jest.spyOn(window, "getSelection").mockReturnValue({
      toString: () => "Hi there!",
    } as Selection);

    const scroller = container.querySelector(".overflow-y-auto") as HTMLElement;
    fireEvent.copy(scroller);

    expect(mockRecordCopyEvent).toHaveBeenCalledWith({
      quiz_id: "base",
      question_id: "q1",
      conversation_id: "conv-1",
      copied_text: "Hi there!",
    });

    getSelectionSpy.mockRestore();
  });

  it("does not record a copy event when there is no selected text", async () => {
    const { container } = render(<ChatBox quizId="base" />);

    const getSelectionSpy = jest.spyOn(window, "getSelection").mockReturnValue({
      toString: () => "",
    } as Selection);

    const scroller = container.querySelector(".overflow-y-auto") as HTMLElement;
    fireEvent.copy(scroller);

    expect(mockRecordCopyEvent).not.toHaveBeenCalled();

    getSelectionSpy.mockRestore();
  });
});
