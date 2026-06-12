import { injectCitationLinks, loadUserHistory, sendChat, Citation } from "../../lib/chat";

describe("injectCitationLinks", () => {
  it("converts [text][n] references into markdown links", () => {
    const citations: Citation[] = [{ n: 1, title: "Docs", url: "https://example.com/docs" }];
    const result = injectCitationLinks("See [the docs][1] for more.", citations);
    expect(result).toBe("See [the docs](https://example.com/docs) for more.");
  });

  it("converts bare [n] references not already followed by '(' into links", () => {
    const citations: Citation[] = [{ n: 1, title: "Docs", url: "https://example.com/docs" }];
    const result = injectCitationLinks("See [1] for more.", citations);
    expect(result).toBe("See [1](https://example.com/docs) for more.");
  });

  it("leaves [n](url) references that are already links untouched", () => {
    const citations: Citation[] = [{ n: 1, title: "Docs", url: "https://example.com/docs" }];
    const text = "Already linked [1](https://other.com).";
    expect(injectCitationLinks(text, citations)).toBe(text);
  });

  it("handles multiple citations independently", () => {
    const citations: Citation[] = [
      { n: 1, title: "A", url: "https://a.example" },
      { n: 2, title: "B", url: "https://b.example" },
    ];
    const result = injectCitationLinks("[Alpha][1] and [Beta][2]", citations);
    expect(result).toBe("[Alpha](https://a.example) and [Beta](https://b.example)");
  });

  it("returns the original text when there are no citations", () => {
    expect(injectCitationLinks("no refs here", [])).toBe("no refs here");
  });
});

describe("loadUserHistory", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => JSON.stringify({ conversation_id: "c1", messages: [] }),
    });
  });

  it("fetches the conversation history for the given conversation id", async () => {
    const result = await loadUserHistory("c1");

    expect(result).toEqual({ conversation_id: "c1", messages: [] });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/chat/load_user_history/c1",
      expect.objectContaining({ credentials: "include" })
    );
  });
});

// ---------------------------------------------------------------------------
// sendChat: SSE streaming
// ---------------------------------------------------------------------------

function sseChunk(events: Record<string, unknown>[]): string {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
}

function makeStreamingResponse(chunks: string[]) {
  let i = 0;
  const reader = {
    read: jest.fn(async () => {
      if (i < chunks.length) {
        const value = new TextEncoder().encode(chunks[i]);
        i += 1;
        return { done: false, value };
      }
      return { done: true, value: undefined };
    }),
    releaseLock: jest.fn(),
  };
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    body: { getReader: () => reader },
    json: async () => ({}),
  };
}

describe("sendChat", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("throws using the response detail when the request fails", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: async () => ({ detail: "Invalid quiz id" }),
    });

    await expect(sendChat("base", null, "hi")).rejects.toThrow("Invalid quiz id");
  });

  it("falls back to status text when the error body cannot be parsed", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Server Error",
      json: async () => {
        throw new Error("not json");
      },
    });

    await expect(sendChat("base", null, "hi")).rejects.toThrow("500 Server Error");
  });

  it("uses the backend-provided reply and conversation id in the done event", async () => {
    const chunks = [
      sseChunk([{ type: "token", content: "Hel" }]),
      sseChunk([{ type: "token", content: "lo" }]),
      sseChunk([{ type: "done", conversation_id: "conv-123", reply: "Hello" }]),
    ];
    (global.fetch as jest.Mock).mockResolvedValue(makeStreamingResponse(chunks));

    const onToken = jest.fn();
    const onDone = jest.fn();

    const result = await sendChat("base", null, "hi", [], { onToken, onDone });

    expect(result.replies).toEqual(["Hello"]);
    expect(result.conversationId).toBe("conv-123");
    expect(onDone).toHaveBeenCalledWith(["Hello"], "conv-123");
    expect(onToken).toHaveBeenCalled();
    const totalDelta = onToken.mock.calls.map((c) => c[0]).join("");
    expect(totalDelta).toBe("Hello");
  });

  it("builds replies from accumulated tokens when no backend reply is provided", async () => {
    const chunks = [
      sseChunk([{ type: "token", content: "Hi" }]),
      sseChunk([{ type: "token", content: " there" }]),
      sseChunk([{ type: "done", conversation_id: "conv-1" }]),
    ];
    (global.fetch as jest.Mock).mockResolvedValue(makeStreamingResponse(chunks));

    const result = await sendChat("base", "conv-1", "hi");

    expect(result.replies).toEqual(["Hi there"]);
    expect(result.conversationId).toBe("conv-1");
  });

  it("returns one reply per agent, sorted by agent key, for multi-agent responses", async () => {
    const chunks = [
      sseChunk([{ type: "token", content: "B says hi", agent: "agentb" }]),
      sseChunk([{ type: "token", content: "A says hi", agent: "agenta" }]),
      sseChunk([{ type: "done", conversation_id: "conv-2" }]),
    ];
    (global.fetch as jest.Mock).mockResolvedValue(makeStreamingResponse(chunks));

    const onToken = jest.fn();
    const result = await sendChat("double", null, "hi", ["agenta", "agentb"], { onToken });

    expect(result.replies).toEqual(["A says hi", "B says hi"]);
    // agent-specific deltas are forwarded with the agent name
    const agents = onToken.mock.calls.map((c) => c[1]);
    expect(agents).toEqual(expect.arrayContaining(["agenta", "agentb"]));
  });

  it("collects streamed follow-up tokens via onFollowupToken", async () => {
    const chunks = [
      sseChunk([{ type: "token", content: "Answer" }]),
      sseChunk([{ type: "followup", token: "What" }]),
      sseChunk([{ type: "followup", token: "?" }]),
      sseChunk([{ type: "done", conversation_id: "conv-3" }]),
    ];
    (global.fetch as jest.Mock).mockResolvedValue(makeStreamingResponse(chunks));

    const onFollowupToken = jest.fn();
    await sendChat("followup", null, "hi", [], { onFollowupToken });

    const totalFollowup = onFollowupToken.mock.calls.map((c) => c[0]).join("");
    expect(totalFollowup).toBe("What?");
  });

  it("collects batched follow-up questions", async () => {
    const chunks = [
      sseChunk([{ type: "token", content: "Answer" }]),
      sseChunk([{ type: "followup", questions: ["Q1?", "Q2?"] }]),
      sseChunk([{ type: "done", conversation_id: "conv-4" }]),
    ];
    (global.fetch as jest.Mock).mockResolvedValue(makeStreamingResponse(chunks));

    const onDone = jest.fn();
    const result = await sendChat("followup", null, "hi", [], { onDone });

    expect(result.followupQuestions).toEqual(["Q1?", "Q2?"]);
  });

  it("injects citation links into the final replies", async () => {
    const chunks = [
      sseChunk([{ type: "token", content: "See [1] for more." }]),
      sseChunk([
        { type: "citations", citations: [{ n: 1, title: "Docs", url: "https://example.com" }] },
      ]),
      sseChunk([{ type: "done", conversation_id: "conv-5" }]),
    ];
    (global.fetch as jest.Mock).mockResolvedValue(makeStreamingResponse(chunks));

    const result = await sendChat("links", null, "hi");

    expect(result.replies).toEqual(["See [1](https://example.com) for more."]);
  });

  it("throws when the stream emits an error event", async () => {
    const chunks = [sseChunk([{ type: "error", detail: "Upstream failure" }])];
    (global.fetch as jest.Mock).mockResolvedValue(makeStreamingResponse(chunks));

    await expect(sendChat("base", null, "hi")).rejects.toThrow("Upstream failure");
  });

  it("sends answer_incorrectly and answer_choices in the request body", async () => {
    const chunks = [sseChunk([{ type: "done", conversation_id: "conv-6" }])];
    (global.fetch as jest.Mock).mockResolvedValue(makeStreamingResponse(chunks));

    await sendChat("base", "conv-6", "hi", [], {
      answerIncorrectly: true,
      answerChoices: [{ id: "c1", label: "Choice 1" }],
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/chat/base",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          message: "hi",
          conversation_id: "conv-6",
          agents: [],
          answer_incorrectly: true,
          answer_choices: [{ id: "c1", label: "Choice 1" }],
        }),
      })
    );
  });
});
