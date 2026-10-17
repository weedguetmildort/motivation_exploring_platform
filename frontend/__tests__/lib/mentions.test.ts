import {
  parseMentions,
  removeMentions,
  getValidAgents,
  getValidMentionTargets,
  hasIncompleteMention,
  getPartialMention,
  getFilteredAgents,
} from "../../lib/mentions";

describe("parseMentions", () => {
  it("extracts lowercase mentions from text", () => {
    const result = parseMentions("Hello @AgentA and @agentb!");
    expect(result.text).toBe("Hello @AgentA and @agentb!");
    expect(result.mentions).toEqual(["agenta", "agentb"]);
  });

  it("returns an empty mentions array when there are none", () => {
    const result = parseMentions("Hello world");
    expect(result.mentions).toEqual([]);
  });
});

describe("removeMentions", () => {
  it("strips mentions and trims surrounding whitespace", () => {
    expect(removeMentions("@agenta hello there")).toBe("hello there");
    expect(removeMentions("hello @agentb")).toBe("hello");
    expect(removeMentions("no mentions here")).toBe("no mentions here");
  });
});

describe("getValidAgents", () => {
  it("returns both agents for the double quiz", () => {
    expect(getValidAgents("double")).toEqual(["agenta", "agentb"]);
  });

  it("returns an empty array for the base quiz", () => {
    expect(getValidAgents("base")).toEqual([]);
  });

  it("returns an empty array for unknown filters", () => {
    expect(getValidAgents("links")).toEqual([]);
    expect(getValidAgents("")).toEqual([]);
  });
});

describe("getValidMentionTargets", () => {
  it("keeps only mentions present in validAgents, deduplicated", () => {
    const result = getValidMentionTargets(
      ["AgentA", "agenta", "agentb", "unknown"],
      ["agenta", "agentb"]
    );
    expect(result).toEqual(["agenta", "agentb"]);
  });

  it("returns an empty array when no mentions are valid", () => {
    expect(getValidMentionTargets(["nope"], ["agenta", "agentb"])).toEqual([]);
  });
});

describe("hasIncompleteMention", () => {
  it("returns false when there is no @ symbol", () => {
    expect(hasIncompleteMention("hello world")).toBe(false);
  });

  it("returns true when @ is followed by non-whitespace text", () => {
    expect(hasIncompleteMention("hello @agen")).toBe(true);
  });

  it("returns false when @ is followed by whitespace", () => {
    expect(hasIncompleteMention("hello @agenta ")).toBe(false);
  });

  it("returns true for a bare trailing @", () => {
    expect(hasIncompleteMention("hello @")).toBe(true);
  });
});

describe("getPartialMention", () => {
  it("returns an empty string when there is no @ symbol", () => {
    expect(getPartialMention("hello world")).toBe("");
  });

  it("returns the lowercase text following the last @", () => {
    expect(getPartialMention("hello @AgentA")).toBe("agenta");
  });

  it("uses the last @ when there are multiple", () => {
    expect(getPartialMention("@first @second")).toBe("second");
  });
});

describe("getFilteredAgents", () => {
  it("returns all valid agents when partial is empty", () => {
    expect(getFilteredAgents("double", "")).toEqual(["agenta", "agentb"]);
  });

  it("filters agents whose names start with the partial text", () => {
    expect(getFilteredAgents("double", "agenta")).toEqual(["agenta"]);
    expect(getFilteredAgents("double", "AGENT")).toEqual(["agenta", "agentb"]);
  });

  it("returns an empty array when nothing matches", () => {
    expect(getFilteredAgents("double", "xyz")).toEqual([]);
  });

  it("returns an empty array for the base quiz regardless of partial", () => {
    expect(getFilteredAgents("base", "a")).toEqual([]);
  });
});
