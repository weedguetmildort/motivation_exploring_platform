import { questionApplies, targetFields, questionTarget } from "../../lib/surveyConfig";

test("shared and selected-stage scopes retain legacy behavior and follow variants", () => {
  expect(questionApplies({ stage: "post_base" }, "post_double")).toBe(true);
  expect(questionApplies({ stage: "pre_quiz" }, "post_base")).toBe(false);
  expect(questionApplies({ stage: "pre_quiz", scope: "all_surveys" }, "post_links")).toBe(true);
  expect(questionApplies({ stage: "post_base", scope: "post_quiz" }, "pre_quiz")).toBe(false);
  const specific = { ...targetFields("post_double", ["post_double", "post_links"]), scope: "stages" as const };
  expect(specific.stages).toEqual(["post_double", "post_links"]);
  expect(questionApplies(specific, "post_double")).toBe(true);
  expect(questionApplies(specific, "post_followup")).toBe(false);
  expect(questionApplies({ ...specific, active: false }, "post_links")).toBe(false);
  expect(questionTarget({ stage: "post_base" })).toBe("post_quiz");
});
