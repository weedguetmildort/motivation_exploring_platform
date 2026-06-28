// frontend/lib/studySteps.ts
import type { User } from "./auth";

// ── Survey stage types ──────────────────────────────────────────────────────

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

export type StudyStepId =
  | "survey_pre"
  | "quiz_base"
  | "survey_post_base"
  | "quiz_variant"
  | "survey_final";

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

export const STEP_SUBTITLES: Record<StudyStepId, string> = {
  survey_pre:       "Before you begin Quiz Part 1, please answer a few quick questions.",
  quiz_base:        "Answer each of the questions using the help of the AI assistant.",
  survey_post_base: "You've completed Quiz Part 1. Please answer a few more questions.",
  quiz_variant:     "Answer each of the questions using the help of the AI assistant.",
  survey_final:     "You've completed Quiz Part 2. Please answer a few final questions.",
};

// ── Survey stage display config (titles, UI strings per stage) ───────────────

export type StageConfig = {
  title: string;
  description: string;
  emptyMessage: string;
  submitLabel: string;
  loadError: string;
};

export const STAGE_CONFIG: Record<ActiveSurveyStage, StageConfig> = {
  pre_quiz: {
    title: "Survey 1",
    description: STEP_SUBTITLES.survey_pre,
    emptyMessage: "No survey items found for this survey. Add items in the Surveys Panel.",
    submitLabel: "Begin Quiz Part 1",
    loadError: "Failed to load this survey.",
  },
  post_base: {
    title: "Survey 2",
    description: STEP_SUBTITLES.survey_post_base,
    emptyMessage: "No survey items found for this survey. Add items in the Surveys Panel.",
    submitLabel: "Continue to Quiz Part 2",
    loadError: "Failed to load this survey.",
  },
  post_variant: {
    title: "Survey 3",
    description: STEP_SUBTITLES.survey_final,
    emptyMessage: "No survey items found for this survey. Add items in the Surveys Panel.",
    submitLabel: "Finish",
    loadError: "Failed to load this survey.",
  },
};

// ── Step builder ─────────────────────────────────────────────────────────────

export function buildStudySteps(user: User): StudyStep[] {
  const v = user.assigned_var;

  return [
    {
      id: "survey_pre",
      label: "Survey 1",
      abbr: "Survey 1",
      path: "/survey?stage=pre_quiz",
      time: "5 min",
      kind: "survey",
      subtitle: STEP_SUBTITLES.survey_pre,
      completed: !!user.survey_pre_base_completed,
    },
    {
      id: "quiz_base",
      label: "Quiz Part 1",
      abbr: "Quiz Part 1",
      path: "/quiz/base",
      time: "10 min",
      kind: "quiz",
      subtitle: STEP_SUBTITLES.quiz_base,
      completed: !!user.quiz_base_completed,
    },
    {
      id: "survey_post_base",
      label: "Survey 2",
      abbr: "Survey 2",
      path: "/survey?stage=post_base",
      time: "5 min",
      kind: "survey",
      subtitle: STEP_SUBTITLES.survey_post_base,
      completed: !!user.survey_post_base_completed,
    },
    {
      id: "quiz_variant",
      label: "Quiz Part 2",
      abbr: "Quiz Part 2",
      path: v ? `/quiz/${v}` : "",
      time: "10 min",
      kind: "quiz",
      subtitle: STEP_SUBTITLES.quiz_variant,
      completed: !!user.quiz_variant_completed,
    },
    {
      id: "survey_final",
      label: "Survey 3",
      abbr: "Survey 3",
      path: "/survey?stage=post_variant",
      time: "5 min",
      kind: "survey",
      subtitle: STEP_SUBTITLES.survey_final,
      completed: !!user.survey_post_variant_completed,
    },
  ];
}
