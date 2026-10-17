import { targetFields, questionTarget } from "../../lib/surveyConfig";

test("selected targets deduplicate and legacy labels preserve their scope", () => {
  expect(targetFields("post_double", ["post_double", "post_links"]).stages).toEqual(["post_double", "post_links"]);
  expect(questionTarget({ stage: "post_base" })).toBe("post_quiz");
  expect(questionTarget({ stage: "post_variant" })).toBe("post_variant");
});
