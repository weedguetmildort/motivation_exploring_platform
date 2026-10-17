import { recordLinkClick, getLinkClicks } from "../../lib/linkClicks";

describe("linkClicks lib", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => JSON.stringify({ ok: true }),
    }) as jest.Mock;
  });

  it("recordLinkClick posts to /api/links/clicks with the click payload", async () => {
    const payload = { quiz_id: "links", question_id: "q1", conversation_id: "conv1", url: "https://example.com" };
    await recordLinkClick(payload);

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/links/clicks",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
        credentials: "include",
      })
    );
  });

  it("getLinkClicks requests the clicks endpoint", async () => {
    await getLinkClicks();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/links/clicks",
      expect.objectContaining({ credentials: "include" })
    );
  });
});
