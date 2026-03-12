import { AIMessageMetadata } from "./chat";

export interface StoredMessage {
  id: string;
  conversationId: string;
  role: "user" | "assistant";
  content: string[];
  metadata?: AIMessageMetadata;
  timestamp: number;
}

class MessageMetadataStore {
  private cache: Map<string, StoredMessage[]> = new Map();

  storeMessage(
    conversationId: string,
    role: "user" | "assistant",
    content: string[],
    metadata?: AIMessageMetadata
  ): StoredMessage {
    const message: StoredMessage = {
      id: `${conversationId}-${Date.now()}-${Math.random()}`,
      conversationId,
      role,
      content,
      metadata,
      timestamp: Date.now(),
    };

    const existing = this.cache.get(conversationId) || [];
    existing.push(message);
    this.cache.set(conversationId, existing);
    return message;
  }

  getMessages(conversationId: string): StoredMessage[] {
    return this.cache.get(conversationId) || [];
  }

  clear(conversationId: string): void {
    this.cache.delete(conversationId);
  }
}

export const messageMetadataStore = new MessageMetadataStore();
