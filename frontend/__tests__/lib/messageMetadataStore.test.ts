import { messageMetadataStore } from "../../lib/messageMetadataStore";

describe("messageMetadataStore", () => {
  afterEach(() => {
    messageMetadataStore.clear("conv-1");
    messageMetadataStore.clear("conv-2");
  });

  it("returns an empty array for a conversation with no messages", () => {
    expect(messageMetadataStore.getMessages("unknown-conv")).toEqual([]);
  });

  it("stores a message and returns it from getMessages", () => {
    const stored = messageMetadataStore.storeMessage("conv-1", "user", ["hello"]);

    expect(stored.conversationId).toBe("conv-1");
    expect(stored.role).toBe("user");
    expect(stored.content).toEqual(["hello"]);
    expect(stored.metadata).toBeUndefined();
    expect(typeof stored.id).toBe("string");
    expect(typeof stored.timestamp).toBe("number");

    expect(messageMetadataStore.getMessages("conv-1")).toEqual([stored]);
  });

  it("appends multiple messages for the same conversation in order", () => {
    const first = messageMetadataStore.storeMessage("conv-1", "user", ["one"]);
    const second = messageMetadataStore.storeMessage("conv-1", "assistant", ["two"], {
      sources: ["a"],
    });

    const messages = messageMetadataStore.getMessages("conv-1");
    expect(messages).toEqual([first, second]);
    expect(messages[1].metadata).toEqual({ sources: ["a"] });
  });

  it("keeps separate conversations isolated from one another", () => {
    messageMetadataStore.storeMessage("conv-1", "user", ["a"]);
    messageMetadataStore.storeMessage("conv-2", "user", ["b"]);

    expect(messageMetadataStore.getMessages("conv-1")).toHaveLength(1);
    expect(messageMetadataStore.getMessages("conv-2")).toHaveLength(1);
  });

  it("clear removes all messages for a conversation", () => {
    messageMetadataStore.storeMessage("conv-1", "user", ["a"]);
    messageMetadataStore.clear("conv-1");

    expect(messageMetadataStore.getMessages("conv-1")).toEqual([]);
  });
});
