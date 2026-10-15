import {
  getNextStep,
  getStudyFlow,
  getStudyConfig,
  updateStudyConfig,
  quizStepId,
  surveyStepId,
} from "../../lib/study";

describe("study lib", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => JSON.stringify({ ok: true }),
    });
  });

  it("getNextStep requests the resolver endpoint", async () => {
    await getNextStep();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/study/next",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("getStudyFlow requests the whole assigned flow", async () => {
    await getStudyFlow();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/study/flow",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("getStudyConfig reads the admin flow configuration", async () => {
    await getStudyConfig();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/study/config",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("updateStudyConfig PUTs the patch", async () => {
    await updateStudyConfig({
      mode: "all_variants",
      variant_order: ["links", "double", "followup"],
      counterbalance: true,
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/study/config",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          mode: "all_variants",
          variant_order: ["links", "double", "followup"],
          counterbalance: true,
        }),
      })
    );
  });

  it("propagates an API error message", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      text: async () => JSON.stringify({ detail: "Admin only" }),
    });

    await expect(getStudyConfig()).rejects.toThrow("Admin only");
  });
});

describe("step id helpers", () => {
  // These must stay in lockstep with backend services/study_flow.py.
  it("builds quiz step ids", () => {
    expect(quizStepId("base")).toBe("quiz:base");
    expect(quizStepId("followup")).toBe("quiz:followup");
  });

  it("builds survey step ids", () => {
    expect(surveyStepId("pre_quiz")).toBe("survey:pre_quiz");
    expect(surveyStepId("post_links")).toBe("survey:post_links");
  });
});
