// frontend/lib/surveys.ts
import { apiFetch } from "./fetcher";

export type SurveyStage = string;

export type SurveyOption = { id: string; label: string };
export type SurveyScale = { min: number; max: number; anchors?: string[] | null };

export type SurveyItem = {
  scope?: import("./surveyConfig").QuestionScope | null;
  stages?: string[];
  active?: boolean;
  id: string;
  stage: string;
  category?: string | null;
  prompt: string;
  type: "likert" | "text" | "single_select" | "multi_select";
  required?: boolean;
  reverse_scored?: boolean;
  order?: number;
  // for likert:
  scale_min?: number;
  scale_max?: number;
  scale_left_label?: string | null;
  scale_right_label?: string | null;
  scale?: SurveyScale | null;
  // for select types:
  options?: SurveyOption[] | null;
};

export type SurveyAnswer = {
  item_id: string;
  value: number | string | string[];
};

export type SurveyAttemptPublic = {
  stage: string;
  status: "not_started" | "in_progress" | "completed";
  answered_count: number;
  total_items: number;
};

// Mirrors backend SurveyStateResponse. Status lives under `attempt` — this type
// previously declared `stage`/`status` at the top level, which the API has never
// returned, so every completion check against it silently read undefined.
export type SurveyStateResponse = {
  attempt: SurveyAttemptPublic;
  items: SurveyItem[];
  answers: { item_id: string; value: any }[];
};

export async function getSurveyState(stage: SurveyStage) {
  const state = await apiFetch<SurveyStateResponse>(`/api/surveys/${stage}/state`);
  return { ...state, items: (state.items ?? []).map(item => item.scale ? { ...item,
    scale_min: item.scale.min, scale_max: item.scale.max,
    scale_left_label: item.scale.anchors?.[0], scale_right_label: item.scale.anchors?.[1],
  } : item) };
}

export async function submitSurvey(stage: SurveyStage, answers: SurveyAnswer[]) {
  return apiFetch<{ ok: boolean }>(`/api/surveys/${stage}/submit`, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}

export function getSurveyPreview(stage: SurveyStage) {
  return apiFetch<SurveyItem[]>(`/api/surveys/preview/${encodeURIComponent(stage)}`);
}
