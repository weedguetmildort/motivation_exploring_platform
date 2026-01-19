// frontend/lib/surveys.ts
import { apiFetch } from "./fetcher";

export type SurveyStage = string;

export type SurveyItem = {
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
  // for select types:
  options?: { id: string; label: string }[];
};

export type SurveyAnswer = {
  item_id: string;
  value: number | string | string[];
};

export type SurveyStateResponse = {
  stage: string;
  status: "not_started" | "in_progress" | "completed";
  items: SurveyItem[];
  answers: { item_id: string; value: any }[];
};

export async function getSurveyState(stage: SurveyStage) {
  return apiFetch<SurveyStateResponse>(`/api/surveys/${stage}/state`); // no /api here if you proxy
}

export async function submitSurvey(stage: SurveyStage, answers: SurveyAnswer[]) {
  return apiFetch<{ ok: boolean }>(`/api/surveys/${stage}/submit`, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}
