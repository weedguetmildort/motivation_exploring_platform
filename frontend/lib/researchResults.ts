export type Metric = {
  value: number | null; participant_count: number; observation_count: number;
  numerator: number | null; denominator: number | null; pooled_value: number | null;
};
export type MetricDefinition = { key: string; label: string; group: string; unit: "percent" | "seconds" | "count" };
export type Comparison = {
  quiz_id?: string; participant_count: number; attempt_count: number; completed_attempt_count: number;
  incomplete_completed_attempt_count: number; questions_assigned: number; questions_shown: number;
  questions_answered: number; questions_graded: number; answers_missing_grade: number; metrics: Record<string, Metric>;
};
export type Participant = {
  study_id?: string; account_id?: string;
  participant_id: string; name: string; email: string; demographics: Record<string, string | string[] | null>;
  is_test: boolean; study_flow_version: number | null; completed_steps: string[]; step_order: string[];
  questions_answered?: number; questions_graded?: number; answers_missing_grade?: number;
  attempt_count?: number; accuracy?: number | null; telemetry_questions?: number;
};
export type Results = {
  matched_enrollments?: number; unique_participants_with_attempts?: number;
  by_study?: { study_id: string; overall: Comparison; variants: Comparison[] }[];
  metric_definitions: MetricDefinition[]; facets: { key: string; label: string; options: { value: string; count: number }[]; missing_count: number }[];
  study_versions: number[]; quiz_ids: string[]; matched_accounts: number; overall: Comparison; variants: Comparison[];
  participants: Participant[]; page: number; page_size: number; total_pages: number; averaging: string;
};
export type QuestionResult = {
  participant_id: string; attempt_id: string; question_id: string; quiz_id: string; question_position: number;
  question_stem: string | null; choice_id: string | null; correct_choice_id: string | null; correct: boolean | null;
  answered: boolean; archived: boolean; attempt_status: string; question_set: string | null; variant_position: number | null;
  wrong_ai_exposed: boolean | null; matched_wrong_ai: boolean | null; matched_first_ai: boolean | null;
  active_ms: number | null; visible_ms: number | null; last_ai_to_submit_ms: number | null; server_elapsed_ms: number | null;
  manual_prompts: number; suggested_prompts: number; answer_revision_count: number;
  suggestion_click_rate: number | null; reference_click_rate: number | null; telemetry_available: boolean; quality_flags: string[];
  [key: string]: unknown;
};
export type ParticipantResults = { participant: Participant; metric_definitions: MetricDefinition[]; overall: Comparison; variants: Comparison[]; questions: QuestionResult[] };
export type QuestionTrace = {
  events_total: number; events_pages: number;
  copies: { id: string; text: string; created_at: string }[];
  snapshot: { stem?: string; subtitle?: string; choices?: { id: string; label: string }[]; correct_choice_id?: string } | null;
  snapshot_source?: "attempt" | "unavailable";
  answer?: { choice_id: string | null; correct_choice_id: string | null; correct: boolean | null; answered_at: string };
  messages: { id: string; role: string; content: string | string[]; created_at: string; trigger: string | null; request_id: string | null; stated_choice_id: Record<string, string | null> | null; intent_labels_heuristic: string[] }[];
  events: { event_id: string; event_type: string; occurred_at: string; elapsed_ms: number; page_id: string; sequence: number; data: Record<string, unknown> }[];
  requests: { request_id: string; prompt: string; trigger: string | null; status: string; started_at: string; partial_visible_replies: Record<string, string> | null; followup_text: string | null }[];
};
export function formatMetric(value: number | null | undefined, unit: MetricDefinition["unit"]) {
  if (value == null) return "—";
  return unit === "percent" ? `${(value * 100).toFixed(1)}%` : unit === "seconds" ? `${(value / 1000).toFixed(1)}s` : value.toFixed(2);
}
export function demographicLabel(key: string, value: string | string[] | null | undefined) {
  if (value == null || value === "" || (Array.isArray(value) && !value.length)) return "Not provided";
  if (Array.isArray(value)) return value.join(", ");
  const years: Record<string, string> = { first: "First year", second: "Second year", third: "Third year", fourth: "Fourth year", other: "Other" };
  return key === "year" ? years[value] ?? value : value;
}
