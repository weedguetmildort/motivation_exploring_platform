import { recordCopyEvent, getCopyEvents } from "../../lib/copyEvents";

describe("copyEvents lib", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => JSON.stringify({ ok: true }),
    }) as jest.Mock;
  });

  it("recordCopyEvent posts to /api/copy-events with the copy payload", async () => {
    const payload = { quiz_id: "base", question_id: "q1", conversation_id: "conv1", copied_text: "The answer is 4." };
    await recordCopyEvent(payload);

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/copy-events",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
        credentials: "include",
      })
    );
  });

  it("getCopyEvents requests the copy-events endpoint", async () => {
    await getCopyEvents();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/copy-events",
      expect.objectContaining({ credentials: "include" })
    );
  });
});
