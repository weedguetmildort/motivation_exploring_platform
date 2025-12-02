// frontend/lib/quiz.ts
import { apiFetch } from "./fetcher";

export type QuizQuestionPayload = {
  id: string;
  stem: string;
  subtitle?: string | null;
  choices: { id: string; label: string }[];
};

export type QuizAttemptPublic = {
  quiz_id: string;
  status: "in_progress" | "completed" | string;
  total_questions: number;
  answered_count: number;
};

export type QuizStateResponse = {
  attempt: QuizAttemptPublic;
  current_question: QuizQuestionPayload | null;
};

export async function getQuizState() {
  return apiFetch<QuizStateResponse>("/api/quiz/state");
}

export async function submitQuizAnswer(questionId: string, choiceId: string) {
  return apiFetch<QuizStateResponse>("/api/quiz/answer", {
    method: "POST",
    body: JSON.stringify({ question_id: questionId, choice_id: choiceId }),
  });
}
