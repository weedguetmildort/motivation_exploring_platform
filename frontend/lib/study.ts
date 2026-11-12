// frontend/lib/study.ts
//
// The study flow is resolved by the backend. Pages ask "where do I go next?"
// rather than each re-deriving the answer from the user's progress flags — the
// routing ladders that used to live in quiz/[quiz_id].tsx and survey.tsx are
// now a single call to /study/next.
import { apiFetch } from "./fetcher";
import type { StudyId } from "./studySelection";

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

/** How each quiz's question set is chosen. */
export type QuizSetMode = "preset" | "random" | "balanced_random";
export type VariantSurveyMode = "per_variant" | "end_only";
export type SurveyStageSetting = { name: string; enabled: boolean };
export type SurveyStages = Record<string, SurveyStageSetting>;

export type StudyConfig = {
  study_id?: string | null;
  survey_stages?: SurveyStages;
  variant_survey_mode?: VariantSurveyMode;
  mode: "all_variants" | "single_variant";
  variant_order: string[];
  counterbalance: boolean;
  version: number;
  questions_per_quiz?: number;
  wrong_ai_count?: number;
  wrong_ai_rate?: number | null;
  requires_study1_completion?: boolean;
  requires_study2_approval?: boolean;
  study_access_mode?: string;
  known_variants: string[];
  variant_labels: Record<string, string>;
  preview: string[][];

  // Per-quiz question sets. Giving each quiz its own set is what keeps a
  // participant's quizzes disjoint — a quiz absent from the map draws from the
  // whole pool.
  quiz_set_mode: QuizSetMode;
  quiz_set_map: Record<string, string>;
  known_sets: string[];
  known_quiz_ids: string[];
  quiz_labels: Record<string, string>;
  // This study's own default (Study 1 and Study 2 differ).
  default_quiz_set_mode?: QuizSetMode | null;

  // Question supply: a participant never sees a question twice in a study.
  question_counts?: Record<string, number>;  // a..d, unassigned, total
  default_question_sets?: string[] | null;   // Study 1 new sign-ups only
  supply_problems?: string[];
  enrolled_with_unstarted_quizzes?: number;
  applied_participants?: number | null;
};

export type StudyConfigUpdate = {
  survey_stages?: SurveyStages;
  variant_survey_mode?: VariantSurveyMode;
  questions_per_quiz?: number;
  wrong_ai_count?: number;
  wrong_ai_rate?: number | null;
  mode?: "all_variants" | "single_variant";
  variant_order?: string[];
  counterbalance?: boolean;
  quiz_set_mode?: QuizSetMode;
  quiz_set_map?: Record<string, string>;
  // Also move enrolled participants' unstarted quizzes onto the saved sets.
  apply_to_enrolled?: boolean;
};

export async function getNextStep() {
  return apiFetch<NextStepResponse>("/api/study/next");
}

export async function getStudyFlow() {
  return apiFetch<StudyFlowResponse>("/api/study/flow");
}

// --- admin ---

// Without a study, the request goes to the study selected in the admin
// workspace; the Study Flow page names the study it is editing.
function configPath(study?: StudyId) {
  return study ? `/api/studies/${study}/study/config` : "/api/study/config";
}

export async function getStudyConfig(study?: StudyId) {
  return apiFetch<StudyConfig>(configPath(study));
}

export async function updateStudyConfig(patch: StudyConfigUpdate, study?: StudyId) {
  return apiFetch<StudyConfig>(configPath(study), {
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
