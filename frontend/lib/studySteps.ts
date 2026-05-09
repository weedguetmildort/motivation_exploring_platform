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
  survey_pre:       "Before you begin the base quiz, please answer a few quick questions.",
  quiz_base:        "Answer each of the questions using the help of the AI assistant.",
  survey_post_base: "You've completed the base quiz. Please answer a few follow-up questions.",
  quiz_variant:     "Answer each of the questions using the help of the AI assistant.",
  survey_final:     "You've completed the variant quiz. Please answer a few final questions.",
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
    title: "Pre-Quiz Survey",
    description: STEP_SUBTITLES.survey_pre,
    emptyMessage: "No survey items found for the pre-quiz survey. Add items in the Surveys Panel.",
    submitLabel: "Begin Base Quiz",
    loadError: "Failed to load the pre-quiz survey.",
  },
  post_base: {
    title: "Post-Base Quiz Survey",
    description: STEP_SUBTITLES.survey_post_base,
    emptyMessage: "No survey items found for the post-base survey. Add items in the Surveys Panel.",
    submitLabel: "Continue to Variant Quiz",
    loadError: "Failed to load the post-base survey.",
  },
  post_variant: {
    title: "Final Survey",
    description: STEP_SUBTITLES.survey_final,
    emptyMessage: "No survey items found for the post-variant survey. Add items in the Surveys Panel.",
    submitLabel: "Finish",
    loadError: "Failed to load the final survey.",
  },
};

// ── Step builder ─────────────────────────────────────────────────────────────

export function buildStudySteps(user: User): StudyStep[] {
  const v = user.assigned_var;
  const variantAbbr =
    v === "followup" ? "Follow-Up" :
    v === "double"   ? "Dual"      :
    v === "links"    ? "Links"     : "Variant";
  const variantLabel =
    v === "followup" ? "Follow-Up Questions Quiz" :
    v === "double"   ? "Dual Agent Quiz"          :
    v === "links"    ? "Embedded Links Quiz"      : "Variant Quiz";

  return [
    {
      id: "survey_pre",
      label: "Pre-Quiz Survey",
      abbr: "Survey",
      path: "/survey?stage=pre_quiz",
      time: "5 min",
      kind: "survey",
      subtitle: STEP_SUBTITLES.survey_pre,
      completed: !!user.survey_pre_base_completed,
    },
    {
      id: "quiz_base",
      label: "Base Quiz",
      abbr: "Base Quiz",
      path: "/quiz/base",
      time: "10 min",
      kind: "quiz",
      subtitle: STEP_SUBTITLES.quiz_base,
      completed: !!user.quiz_base_completed,
    },
    {
      id: "survey_post_base",
      label: "Mid Survey",
      abbr: "Survey",
      path: "/survey?stage=post_base",
      time: "5 min",
      kind: "survey",
      subtitle: STEP_SUBTITLES.survey_post_base,
      completed: !!user.survey_post_base_completed,
    },
    {
      id: "quiz_variant",
      label: variantLabel,
      abbr: variantAbbr,
      path: v ? `/quiz/${v}` : "",
      time: "10 min",
      kind: "quiz",
      subtitle: STEP_SUBTITLES.quiz_variant,
      completed: !!user.quiz_variant_completed,
    },
    {
      id: "survey_final",
      label: "Final Survey",
      abbr: "Survey",
      path: "/survey?stage=post_variant",
      time: "5 min",
      kind: "survey",
      subtitle: STEP_SUBTITLES.survey_final,
      completed: !!user.survey_post_variant_completed,
    },
  ];
}
