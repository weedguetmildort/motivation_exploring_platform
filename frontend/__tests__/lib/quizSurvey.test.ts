import { saveQuizPreSurvey } from "../../lib/quizSurvey";

describe("saveQuizPreSurvey", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      text: async () => JSON.stringify({ ok: true }),
    }) as jest.Mock;
  });

  it("posts the payload to /api/quiz-survey/me", async () => {
    const payload = {
      prior_experience: 3,
      trust_rely: 4,
      trust_general: 5,
      trust_count_on: 2,
    };

    const result = await saveQuizPreSurvey(payload);

    expect(result).toEqual({ ok: true });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/quiz-survey/me",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
        credentials: "include",
      })
    );
  });
});
