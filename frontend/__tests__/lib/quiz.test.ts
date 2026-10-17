import {
  getQuizState,
  submitQuizAnswer,
  resetQuiz,
  getQuizResults,
} from "../../lib/quiz";

describe("quiz lib", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => JSON.stringify({ ok: true }),
    });
  });

  it("getQuizState requests the quiz state endpoint for the given quiz id", async () => {
    await getQuizState("base");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/quiz/base/state",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("submitQuizAnswer posts the question and choice ids", async () => {
    await submitQuizAnswer("base", "q1", "c2");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/quiz/base/answer",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ question_id: "q1", choice_id: "c2" }),
      })
    );
  });

  it("resetQuiz posts to the reset endpoint", async () => {
    await resetQuiz("links");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/quiz/links/reset",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("getQuizResults requests the results endpoint", async () => {
    await getQuizResults("double");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/quiz/double/results",
      expect.objectContaining({ credentials: "include" })
    );
  });
});
