// frontend/lib/studySteps.ts
import type { User } from "./auth";

// ── Survey stage types ──────────────────────────────────────────────────────

// The three fixed stages. Participants now also get one interstitial survey per
// variant quiz (post_followup, post_links, …), so the stage set is open-ended —
// `SurveyStage` stays for the legacy values that other modules still name.
export type SurveyStage = "pre_quiz" | "post_base" | "post_variant" | "complete";
export type ActiveSurveyStage = Exclude<SurveyStage, "complete">;

export function isActiveSurveyStage(value: unknown): value is ActiveSurveyStage {
  return value === "pre_quiz" || value === "post_base" || value === "post_variant";
}

// ── Quiz ID types ───────────────────────────────────────────────────────────

export const VARIANT_QUIZ_IDS = ["followup", "links", "double"] as const;
export type VariantQuizId = (typeof VARIANT_QUIZ_IDS)[number];
export type QuizId = "base" | VariantQuizId;

export function isVariantQuizId(value: string): value is VariantQuizId {
  return (VARIANT_QUIZ_IDS as readonly string[]).includes(value);
}

// ── Study step types ────────────────────────────────────────────────────────

// Was a closed union of five ids. The flow is now assembled per participant
// (base quiz plus every variant, in a counterbalanced order), so ids come from
// the backend step registry — "quiz:base", "survey:post_links", and so on.
// The five legacy ids below are still produced by the fallback build.
export type StudyStepId = string;

export const LEGACY_STEP_IDS = [
  "survey_pre",
  "quiz_base",
  "survey_post_base",
  "quiz_variant",
  "survey_final",
] as const;

export type StudyStep = {
  id: StudyStepId;
  label: string;
  abbr: string;
  path: string;
  time: string;
  kind: "quiz" | "survey";
  subtitle: string;
  completed: boolean;
};

// ── Subtitle strings (single source of truth for page headers + hero card) ──

export const STEP_SUBTITLES: Record<string, string> = {
  survey_pre:       "Before you begin Quiz Part 1, please answer a few quick questions.",
  quiz_base:        "Answer each of the questions using the help of the AI assistant.",
  survey_post_base: "You've completed Quiz Part 1. Please answer a few more questions.",
  quiz_variant:     "Answer each of the questions using the help of the AI assistant.",
  survey_final:     "You've completed Quiz Part 2. Please answer a few final questions.",
};

const QUIZ_TIME = "10 min";
const SURVEY_TIME = "5 min";

// ── Survey stage display config (titles, UI strings per stage) ───────────────

export type StageConfig = {
  title: string;
  description: string;
  emptyMessage: string;
  submitLabel: string;
  loadError: string;
};

const EMPTY_MESSAGE =
  "No survey items found for this survey. Add items in the Surveys Panel.";
const LOAD_ERROR = "Failed to load this survey.";

export const STAGE_CONFIG: Record<ActiveSurveyStage, StageConfig> = {
  pre_quiz: {
    title: "Survey 1",
    description: STEP_SUBTITLES.survey_pre,
    emptyMessage: EMPTY_MESSAGE,
    submitLabel: "Begin Quiz Part 1",
    loadError: LOAD_ERROR,
  },
  post_base: {
    title: "Survey 2",
    description: STEP_SUBTITLES.survey_post_base,
    emptyMessage: EMPTY_MESSAGE,
    submitLabel: "Continue to Quiz Part 2",
    loadError: LOAD_ERROR,
  },
  post_variant: {
    title: "Survey 3",
    description: STEP_SUBTITLES.survey_final,
    emptyMessage: EMPTY_MESSAGE,
    submitLabel: "Finish",
    loadError: LOAD_ERROR,
  },
};

// ── Step-id helpers (mirror backend services/study_flow.py) ─────────────────

export function quizStepId(quizId: string): string {
  return `quiz:${quizId}`;
}

export function surveyStepId(stage: string): string {
  return `survey:${stage}`;
}

/** Split a backend step id into its kind and key. */
export function parseStepId(
  stepId: string,
): { kind: "quiz" | "survey"; key: string } | null {
  const [kind, ...rest] = stepId.split(":");
  const key = rest.join(":");
  if (!key) return null;
  if (kind === "quiz" || kind === "survey") return { kind, key };
  return null;
}

function routeForStep(kind: "quiz" | "survey", key: string): string {
  return kind === "quiz" ? `/quiz/${key}` : `/survey?stage=${key}`;
}


/**
 * Index of the step at `path` within a built step list.
 *
 * Matches on path rather than id deliberately: the flow-derived build uses
 * backend step ids ("quiz:base") while the legacy fallback uses the original
 * ones ("quiz_base"), but both produce identical paths — so callers work for a
 * participant with or without an assigned flow.
 */
export function stepIndexForPath(steps: StudyStep[], path: string): number {
  return steps.findIndex((s) => s.path === path);
}

export function quizPath(quizId: string): string {
  return `/quiz/${quizId}`;
}

export function surveyPath(stage: string): string {
  return `/survey?stage=${stage}`;
}

// ── Step builder ─────────────────────────────────────────────────────────────

/**
 * The participant's assigned journey.
 *
 * Derived from `step_order` / `completed_steps`, which the backend snapshots
 * onto the user at signup and returns from /auth/me. Labels stay de-identified
 * ("Quiz Part 1", "Survey 2"), numbered by position, so the same scheme extends
 * from the old two quizzes to however many variants the flow schedules.
 *
 * Falls back to the original fixed five-step build for a user with no
 * step_order — an account the backend has not backfilled yet.
 */
export function buildStudySteps(user: User): StudyStep[] {
  const order = user.step_order ?? [];
  if (order.length === 0) return buildLegacyStudySteps(user);

  const completed = new Set(user.completed_steps ?? []);

  let quizNumber = 0;
  let surveyNumber = 0;

  return order.flatMap<StudyStep>((stepId) => {
    const parsed = parseStepId(stepId);
    if (!parsed) return [];

    const { kind, key } = parsed;
    const isQuiz = kind === "quiz";
    const label = isQuiz ? `Quiz Part ${++quizNumber}` : `Survey ${++surveyNumber}`;

    return [{
      id: stepId,
      label,
      abbr: label,
      path: routeForStep(kind, key),
      time: isQuiz ? QUIZ_TIME : SURVEY_TIME,
      kind,
      subtitle: isQuiz
        ? STEP_SUBTITLES.quiz_base
        : surveyNumber === 1
          ? STEP_SUBTITLES.survey_pre
          : "You've completed that quiz. Please answer a few questions about it.",
      completed: completed.has(stepId),
    }];
  });
}

/** The original single-variant flow, for users without an assigned step_order. */
export function buildLegacyStudySteps(user: User): StudyStep[] {
  const v = user.assigned_var;

  return [
    {
      id: "survey_pre",
      label: "Survey 1",
      abbr: "Survey 1",
      path: "/survey?stage=pre_quiz",
      time: SURVEY_TIME,
      kind: "survey",
      subtitle: STEP_SUBTITLES.survey_pre,
      completed: !!user.survey_pre_base_completed,
    },
    {
      id: "quiz_base",
      label: "Quiz Part 1",
      abbr: "Quiz Part 1",
      path: "/quiz/base",
      time: QUIZ_TIME,
      kind: "quiz",
      subtitle: STEP_SUBTITLES.quiz_base,
      completed: !!user.quiz_base_completed,
    },
    {
      id: "survey_post_base",
      label: "Survey 2",
      abbr: "Survey 2",
      path: "/survey?stage=post_base",
      time: SURVEY_TIME,
      kind: "survey",
      subtitle: STEP_SUBTITLES.survey_post_base,
      completed: !!user.survey_post_base_completed,
    },
    {
      id: "quiz_variant",
      label: "Quiz Part 2",
      abbr: "Quiz Part 2",
      path: v ? `/quiz/${v}` : "",
      time: QUIZ_TIME,
      kind: "quiz",
      subtitle: STEP_SUBTITLES.quiz_variant,
      completed: !!user.quiz_variant_completed,
    },
    {
      id: "survey_final",
      label: "Survey 3",
      abbr: "Survey 3",
      path: "/survey?stage=post_variant",
      time: SURVEY_TIME,
      kind: "survey",
      subtitle: STEP_SUBTITLES.survey_final,
      completed: !!user.survey_post_variant_completed,
    },
  ];
}

/**
 * Copy for the survey page at `stage`.
 *
 * Titles and the submit label are derived from the survey's position in the
 * participant's own flow, so "Survey 2 → Continue to Quiz Part 2" still reads
 * correctly however many variants are scheduled. Falls back to STAGE_CONFIG for
 * the three fixed stages when the user has no flow.
 */
export function stageConfigFor(user: User, stage: string): StageConfig {
  const steps = buildStudySteps(user);
  const index = stepIndexForPath(steps, surveyPath(stage));

  if (index === -1) {
    return isActiveSurveyStage(stage) ? STAGE_CONFIG[stage] : STAGE_CONFIG.post_base;
  }

  const step = steps[index];
  const nextStep = steps[index + 1];

  let submitLabel: string;
  if (!nextStep) {
    submitLabel = "Finish";
  } else if (index === 0) {
    // Keeps the original wording on the very first step.
    submitLabel = `Begin ${nextStep.label}`;
  } else {
    submitLabel = `Continue to ${nextStep.label}`;
  }

  return {
    title: step.label,
    description: step.subtitle,
    emptyMessage: EMPTY_MESSAGE,
    submitLabel,
    loadError: LOAD_ERROR,
  };
}
