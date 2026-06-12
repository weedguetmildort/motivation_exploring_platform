import { getSurveyState, submitSurvey } from "../../lib/surveys";

describe("surveys lib", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => JSON.stringify({ ok: true }),
    });
  });

  it("getSurveyState requests the stage-specific state endpoint", async () => {
    await getSurveyState("pre_quiz");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/surveys/pre_quiz/state",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("submitSurvey posts answers to the stage-specific submit endpoint", async () => {
    const answers = [{ item_id: "q1", value: 5 }];

    await submitSurvey("post_base", answers);

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/surveys/post_base/submit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ answers }),
      })
    );
  });
});
