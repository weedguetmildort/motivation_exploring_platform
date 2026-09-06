// frontend/lib/study.ts
//
// The study flow is resolved by the backend. Pages ask "where do I go next?"
// rather than each re-deriving the answer from the user's progress flags — the
// routing ladders that used to live in quiz/[quiz_id].tsx and survey.tsx are
// now a single call to /study/next.
import { apiFetch } from "./fetcher";

export type StepKind = "quiz" | "survey";

export type StudyStep = {
  id: string;        // e.g. "quiz:base", "survey:post_links"
  kind: StepKind;
  key: string;       // quiz_id for quizzes, survey stage for surveys
  label: string;
  route: string;     // where this step lives
  variant?: string | null;
  completed: boolean;
};

export type NextStepResponse = {
  next_step: StudyStep | null;
  next_route: string;
  completed_count: number;
  total_steps: number;
  finished: boolean;
};

export type StudyFlowResponse = {
  steps: StudyStep[];
  variant_sequence: string[];
  current_step_id: string | null;
  completed_count: number;
  total_steps: number;
  finished: boolean;
  study_flow_version: number;
  mode: string;
};

export type StudyConfig = {
  mode: "all_variants" | "single_variant";
  variant_order: string[];
  counterbalance: boolean;
  version: number;
  known_variants: string[];
  variant_labels: Record<string, string>;
  preview: string[][];
};

export type StudyConfigUpdate = {
  mode?: "all_variants" | "single_variant";
  variant_order?: string[];
  counterbalance?: boolean;
};

export async function getNextStep() {
  return apiFetch<NextStepResponse>("/api/study/next");
}

export async function getStudyFlow() {
  return apiFetch<StudyFlowResponse>("/api/study/flow");
}

// --- admin ---

export async function getStudyConfig() {
  return apiFetch<StudyConfig>("/api/study/config");
}

export async function updateStudyConfig(patch: StudyConfigUpdate) {
  return apiFetch<StudyConfig>("/api/study/config", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

/** Step id for a quiz — mirrors study_flow.quiz_step_id on the backend. */
export function quizStepId(quizId: string): string {
  return `quiz:${quizId}`;
}

/** Step id for a survey stage — mirrors study_flow.survey_step_id. */
export function surveyStepId(stage: string): string {
  return `survey:${stage}`;
}
