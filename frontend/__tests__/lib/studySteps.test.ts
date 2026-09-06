import {
  isActiveSurveyStage,
  isVariantQuizId,
  buildStudySteps,
  stageConfigFor,
  stepIndexForPath,
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
    ["followup", "/quiz/followup"],
    ["double", "/quiz/double"],
    ["links", "/quiz/links"],
  ])(
    "builds the variant step for assigned_var=%s with a neutral label",
    (assignedVar, path) => {
      const steps = buildStudySteps(makeUser({ assigned_var: assignedVar }));
      const variant = steps.find((s) => s.id === "quiz_variant")!;

      expect(variant.abbr).toBe("Quiz Part 2");
      expect(variant.label).toBe("Quiz Part 2");
      expect(variant.path).toBe(path);
      expect(variant.subtitle).toBe(STEP_SUBTITLES.quiz_variant);
    }
  );

  it("uses the same neutral labeling when assigned_var is unset", () => {
    const steps = buildStudySteps(makeUser({ assigned_var: null }));
    const variant = steps.find((s) => s.id === "quiz_variant")!;

    expect(variant.abbr).toBe("Quiz Part 2");
    expect(variant.label).toBe("Quiz Part 2");
    expect(variant.path).toBe("");
  });

  it("uses the same neutral labeling for an unrecognized assigned_var", () => {
    const steps = buildStudySteps(makeUser({ assigned_var: "something-else" }));
    const variant = steps.find((s) => s.id === "quiz_variant")!;

    expect(variant.abbr).toBe("Quiz Part 2");
    expect(variant.label).toBe("Quiz Part 2");
    expect(variant.path).toBe("/quiz/something-else");
  });
});

// ── Flow-derived build (participants with an assigned step_order) ───────────

const FLOW_ORDER = [
  "survey:pre_quiz",
  "quiz:base",
  "survey:post_base",
  "quiz:followup",
  "survey:post_followup",
  "quiz:double",
  "survey:post_double",
  "quiz:links",
  "survey:post_links",
];

describe("buildStudySteps (flow-derived)", () => {
  it("builds one step per entry in the participant's assigned order", () => {
    const steps = buildStudySteps(makeUser({ step_order: FLOW_ORDER }));

    expect(steps.map((s) => s.id)).toEqual(FLOW_ORDER);
  });

  it("numbers quizzes and surveys independently, past the old two-quiz ceiling", () => {
    const steps = buildStudySteps(makeUser({ step_order: FLOW_ORDER }));

    expect(steps.filter((s) => s.kind === "quiz").map((s) => s.label)).toEqual([
      "Quiz Part 1",
      "Quiz Part 2",
      "Quiz Part 3",
      "Quiz Part 4",
    ]);
    expect(steps.filter((s) => s.kind === "survey").map((s) => s.label)).toEqual([
      "Survey 1",
      "Survey 2",
      "Survey 3",
      "Survey 4",
      "Survey 5",
    ]);
  });

  it("keeps labels de-identified — no variant name is exposed", () => {
    const steps = buildStudySteps(makeUser({ step_order: FLOW_ORDER }));

    for (const variant of ["followup", "links", "double"]) {
      expect(steps.some((s) => s.label.includes(variant))).toBe(false);
    }
  });

  it("derives paths from the step id", () => {
    const steps = buildStudySteps(makeUser({ step_order: FLOW_ORDER }));
    const byId = Object.fromEntries(steps.map((s) => [s.id, s]));

    expect(byId["quiz:links"].path).toBe("/quiz/links");
    expect(byId["survey:post_links"].path).toBe("/survey?stage=post_links");
  });

  it("reflects completed_steps rather than the legacy booleans", () => {
    const steps = buildStudySteps(
      makeUser({
        step_order: FLOW_ORDER,
        completed_steps: ["survey:pre_quiz", "quiz:base"],
        // Deliberately contradictory legacy flags — they must be ignored.
        quiz_variant_completed: true,
        survey_post_variant_completed: true,
      })
    );

    const byId = Object.fromEntries(steps.map((s) => [s.id, s]));
    expect(byId["survey:pre_quiz"].completed).toBe(true);
    expect(byId["quiz:base"].completed).toBe(true);
    expect(byId["quiz:links"].completed).toBe(false);
    expect(byId["survey:post_links"].completed).toBe(false);
  });

  it("skips step ids it does not recognise", () => {
    const steps = buildStudySteps(
      makeUser({ step_order: [...FLOW_ORDER, "garbage"] })
    );

    expect(steps).toHaveLength(FLOW_ORDER.length);
  });

  it("falls back to the legacy five steps when there is no assigned flow", () => {
    const steps = buildStudySteps(makeUser({ step_order: [] }));

    expect(steps.map((s) => s.id)).toEqual([
      "survey_pre",
      "quiz_base",
      "survey_post_base",
      "quiz_variant",
      "survey_final",
    ]);
  });
});

describe("stepIndexForPath", () => {
  it("finds a step in the flow-derived build", () => {
    const steps = buildStudySteps(makeUser({ step_order: FLOW_ORDER }));
    expect(stepIndexForPath(steps, "/quiz/double")).toBe(5);
  });

  it("finds the equivalent step in the legacy build", () => {
    // Both builds emit identical paths, which is why lookups match on path.
    const steps = buildStudySteps(makeUser({ step_order: [] }));
    expect(stepIndexForPath(steps, "/quiz/base")).toBe(1);
  });

  it("returns -1 for a path that is not in the flow", () => {
    const steps = buildStudySteps(makeUser({ step_order: FLOW_ORDER }));
    expect(stepIndexForPath(steps, "/quiz/nope")).toBe(-1);
  });
});

describe("stageConfigFor", () => {
  it("titles and numbers a survey by its position in the flow", () => {
    const config = stageConfigFor(
      makeUser({ step_order: FLOW_ORDER }),
      "post_followup"
    );

    expect(config.title).toBe("Survey 3");
    expect(config.submitLabel).toBe("Continue to Quiz Part 3");
  });

  it("keeps the original wording on the first step", () => {
    const config = stageConfigFor(makeUser({ step_order: FLOW_ORDER }), "pre_quiz");
    expect(config.submitLabel).toBe("Begin Quiz Part 1");
  });

  it("labels the final survey's submit as Finish", () => {
    const config = stageConfigFor(makeUser({ step_order: FLOW_ORDER }), "post_links");
    expect(config.submitLabel).toBe("Finish");
  });

  it("falls back to the fixed stage config without a flow", () => {
    const config = stageConfigFor(makeUser({ step_order: [] }), "post_base");
    expect(config.title).toBe("Survey 2");
  });
});
