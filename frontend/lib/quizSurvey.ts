import { apiFetch } from "./fetcher";

export type QuizPreSurveyPayload = {
  prior_experience: number;   // 1–5
  trust_rely: number;         // 1–5
  trust_general: number;      // 1–5
  trust_count_on: number;     // 1–5
};

export async function saveQuizPreSurvey(payload: QuizPreSurveyPayload) {
  return apiFetch<{ ok: boolean }>("/api/quiz-survey/me", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
