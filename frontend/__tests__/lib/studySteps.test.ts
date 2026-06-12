import {
  isActiveSurveyStage,
  isVariantQuizId,
  buildStudySteps,
  STEP_SUBTITLES,
} from "../../lib/studySteps";
import type { User } from "../../lib/auth";

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "1",
    email: "user@example.com",
    is_admin: false,
    ...overrides,
  };
}

describe("isActiveSurveyStage", () => {
  it("returns true for the active survey stages", () => {
    expect(isActiveSurveyStage("pre_quiz")).toBe(true);
    expect(isActiveSurveyStage("post_base")).toBe(true);
    expect(isActiveSurveyStage("post_variant")).toBe(true);
  });

  it("returns false for 'complete' and other values", () => {
    expect(isActiveSurveyStage("complete")).toBe(false);
    expect(isActiveSurveyStage("unknown")).toBe(false);
    expect(isActiveSurveyStage(undefined)).toBe(false);
    expect(isActiveSurveyStage(123)).toBe(false);
  });
});

describe("isVariantQuizId", () => {
  it("returns true for known variant quiz ids", () => {
    expect(isVariantQuizId("followup")).toBe(true);
    expect(isVariantQuizId("links")).toBe(true);
    expect(isVariantQuizId("double")).toBe(true);
  });

  it("returns false for the base quiz id or unknown values", () => {
    expect(isVariantQuizId("base")).toBe(false);
    expect(isVariantQuizId("something-else")).toBe(false);
  });
});

describe("buildStudySteps", () => {
  it("returns the five steps in order with correct ids", () => {
    const steps = buildStudySteps(makeUser());

    expect(steps.map((s) => s.id)).toEqual([
      "survey_pre",
      "quiz_base",
      "survey_post_base",
      "quiz_variant",
      "survey_final",
    ]);
  });

  it("reflects completion flags from the user object", () => {
    const steps = buildStudySteps(
      makeUser({
        survey_pre_base_completed: true,
        quiz_base_completed: true,
        survey_post_base_completed: false,
        quiz_variant_completed: true,
        survey_post_variant_completed: false,
      })
    );

    const byId = Object.fromEntries(steps.map((s) => [s.id, s]));
    expect(byId.survey_pre.completed).toBe(true);
    expect(byId.quiz_base.completed).toBe(true);
    expect(byId.survey_post_base.completed).toBe(false);
    expect(byId.quiz_variant.completed).toBe(true);
    expect(byId.survey_final.completed).toBe(false);
  });

  it("treats missing completion flags as false", () => {
    const steps = buildStudySteps(makeUser());
    expect(steps.every((s) => s.completed === false)).toBe(true);
  });

  it.each([
    ["followup", "Follow-Up", "Follow-Up Questions Quiz", "/quiz/followup"],
    ["double", "Dual", "Dual Agent Quiz", "/quiz/double"],
    ["links", "Links", "Embedded Links Quiz", "/quiz/links"],
  ])(
    "builds the variant step for assigned_var=%s",
    (assignedVar, abbr, label, path) => {
      const steps = buildStudySteps(makeUser({ assigned_var: assignedVar }));
      const variant = steps.find((s) => s.id === "quiz_variant")!;

      expect(variant.abbr).toBe(abbr);
      expect(variant.label).toBe(label);
      expect(variant.path).toBe(path);
      expect(variant.subtitle).toBe(STEP_SUBTITLES.quiz_variant);
    }
  );

  it("falls back to generic Variant labeling when assigned_var is unset", () => {
    const steps = buildStudySteps(makeUser({ assigned_var: null }));
    const variant = steps.find((s) => s.id === "quiz_variant")!;

    expect(variant.abbr).toBe("Variant");
    expect(variant.label).toBe("Variant Quiz");
    expect(variant.path).toBe("");
  });

  it("falls back to generic Variant labeling for an unrecognized assigned_var", () => {
    const steps = buildStudySteps(makeUser({ assigned_var: "something-else" }));
    const variant = steps.find((s) => s.id === "quiz_variant")!;

    expect(variant.abbr).toBe("Variant");
    expect(variant.label).toBe("Variant Quiz");
    expect(variant.path).toBe("/quiz/something-else");
  });
});
