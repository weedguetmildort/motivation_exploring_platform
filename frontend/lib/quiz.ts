// frontend/lib/quiz.ts
import { apiFetch } from "./fetcher";

// User-facing quiz information
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
  conversation_id: string;
  attempt: QuizAttemptPublic;
  current_question: QuizQuestionPayload | null;
};

// (Admin view for now) used to get and display quiz results after completion
export type QuizResultItem = {
  question_number: number;
  question_id: string;
  stem: string;
  user_choice_id: string;
  user_choice_label: string;
  correct_choice_id: string;
  correct_choice_label: string;
  is_correct: boolean;
};

export type QuizResultsResponse = {
  quiz_id: string;
  total_questions: number;
  correct_count: number;
  items: QuizResultItem[];
};


export async function getQuizState(quizID: string) {
  return apiFetch<QuizStateResponse>("/api/quiz/{quiz_id}/state".replace("{quiz_id}", quizID));
}

export async function submitQuizAnswer(quizID: string, questionId: string, choiceId: string) {
  return apiFetch<QuizStateResponse>("/api/quiz/{quiz_id}/answer".replace("{quiz_id}", quizID), {
    method: "POST",
    body: JSON.stringify({ question_id: questionId, choice_id: choiceId }),
  });
}

export async function resetQuiz(quizID: string) {
  return apiFetch<{ ok: boolean }>(`/api/quiz/${quizID}/reset`, { method: "POST" });
}

export async function getQuizResults(quizID: string) {
  return apiFetch<QuizResultsResponse>(`/api/quiz/${quizID}/results`);
}
