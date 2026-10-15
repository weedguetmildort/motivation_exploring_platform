import type { Metric, Results, ParticipantResults, QuestionResult, QuestionTrace } from "../lib/researchResults";
export const metric = (value: number | null, people = 2, observations = 6): Metric => ({ value, participant_count: value == null ? 0 : people, observation_count: value == null ? 0 : observations, numerator: null, denominator: null, pooled_value: value });
export const definitions: Results["metric_definitions"] = [
  { key: "accuracy", label: "Accuracy", unit: "percent", group: "Performance" },
  { key: "wrong_ai_agreement", label: "Agreement with wrong AI", unit: "percent", group: "AI agreement" },
  { key: "active_ms", label: "Active time per question", unit: "seconds", group: "Timing" },
  { key: "telemetry_coverage", label: "Questions with telemetry", unit: "percent", group: "Data quality" },
  { key: "pointer_chat_share", label: "Pointer share: Chat", unit: "percent", group: "Pointer regions" },
];
const overall = { participant_count: 2, questions_assigned: 6, questions_answered: 6,
  metrics: { accuracy: metric(.5), wrong_ai_agreement: metric(null), active_ms: metric(12000, 1, 1), telemetry_coverage: metric(0), pointer_chat_share: metric(.75) } };
export const results: Results = {
  metric_definitions: definitions, overall, variants: [{ ...overall, quiz_id: "base" }],
  facets: [{ key: "gender", label: "Gender", options: [{ value: "Female", count: 1 }, { value: "Male", count: 1 }], missing_count: 1 },
    { key: "year", label: "Year in program", options: [{ value: "first", count: 1 }], missing_count: 2 }],
  study_versions: [2], quiz_ids: ["base", "links"], matched_accounts: 3, page: 1, page_size: 25, total_pages: 1,
  averaging: "Each participant contributes equally.",
  participants: [{ participant_id: "alice", name: "Alice Student", email: "alice@test.edu", demographics: { gender: "Female", academic_level: "Undergraduate", year: "first" },
    is_test: false, study_flow_version: 2, completed_steps: [], step_order: ["quiz:base"], questions_answered: 5, attempt_count: 1, accuracy: 1, telemetry_questions: 4 }],
};
export const question = { participant_id: "alice", attempt_id: "attempt", question_id: "q1", quiz_id: "links", question_position: 1, question_stem: "Frozen question",
  choice_id: "b", correct_choice_id: "a", correct: false, answered: true, archived: false, attempt_status: "completed", question_set: "a", variant_position: 2,
  wrong_ai_exposed: true, matched_wrong_ai: true, matched_first_ai: true, active_ms: 12000, visible_ms: 14000, last_ai_to_submit_ms: 3000, server_elapsed_ms: 16000,
  manual_prompts: 1, suggested_prompts: 1, answer_revision_count: 2, suggestion_click_rate: .5, reference_click_rate: 0, telemetry_available: true, quality_flags: [], ai_requests: 3,
} satisfies QuestionResult;
export const person: ParticipantResults = { participant: results.participants[0], metric_definitions: definitions, overall, variants: results.variants, questions: [question] };
export const trace: QuestionTrace = { snapshot: { stem: "Frozen question", choices: [{ id: "a", label: "Correct answer" }] },
  messages: [{ id: "m1", role: "user", content: "Please double check this answer", created_at: "2026-01-01", trigger: "manual", request_id: "r1", stated_choice_id: null, intent_labels_heuristic: ["double_check"] }],
  events: [], requests: [], copies: [], events_total: 0, events_pages: 0 };
