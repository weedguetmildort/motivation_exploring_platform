export interface ParsedMessage {
  text: string;
  mentions: string[];
}

export function parseMentions(text: string): ParsedMessage {
  const mentionRegex = /@([a-zA-Z0-9_-]+)/g;
  const mentions: string[] = [];
  let match;

  while ((match = mentionRegex.exec(text)) !== null) {
    mentions.push(match[1].toLowerCase());
  }

  return { text, mentions };
}

export function removeMentions(text: string): string {
  return text.replace(/@[a-zA-Z0-9_-]+/g, "").trim();
}

export function getValidAgents(filter: string): string[] {
  switch (filter) {
    case "double":
      return ["agenta", "agentb"];
    case "base":
      return [];
    default:
      return [];
  }
}

export function getValidMentionTargets(
  mentions: string[],
  validAgents: string[]
): string[] {
  const unique = new Set<string>();
  mentions.forEach((mention) => {
    const lower = mention.toLowerCase();
    if (validAgents.includes(lower)) {
      unique.add(lower);
    }
  });
  return Array.from(unique);
}

export function hasIncompleteMention(text: string): boolean {
  const lastAtSymbol = text.lastIndexOf("@");
  if (lastAtSymbol === -1) return false;
  const afterAt = text.substring(lastAtSymbol + 1);
  // If there's a space or newline after @, it's incomplete
  return !/\s/.test(afterAt);
}

export function getPartialMention(text: string): string {
  const lastAtSymbol = text.lastIndexOf("@");
  if (lastAtSymbol === -1) return "";
  return text.substring(lastAtSymbol + 1).toLowerCase();
}

export function getFilteredAgents(
  mode: "double" | "base",
  partial: string
): string[] {
  const valid = getValidAgents(mode);
  if (!partial) return valid;
  return valid.filter((agent) => agent.startsWith(partial.toLowerCase()));
}
