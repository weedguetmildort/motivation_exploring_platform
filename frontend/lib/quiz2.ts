// frontend/lib/quiz2.ts
//
// SCAFFOLD (Phase 13): structure for a future "quiz 2" version, parallel to
// quiz 1 (base + followup/links/double). Nothing here is wired into the live
// quiz-1 flow — importing this module has no runtime effect until a later phase
// renders these steps in the dashboard/progress UI, gated by QUIZ2_ENABLED.
//
// Deferred to a future phase: quiz-2 questions & per-version default sets,
// quiz-2 survey stages, and quiz2_*_completed flags on the user model.
import type { User } from "./auth";

// Feature flag — OFF unless explicitly enabled in the environment. Keeps quiz 1
// completely unaffected while quiz 2 is scaffolded.
export const QUIZ2_ENABLED = process.env.NEXT_PUBLIC_QUIZ2_ENABLED === "true";

// Quiz-2 quiz_id namespace. The dynamic route pages/quiz/[quiz_id].tsx already
// serves any quiz_id, so these render through the same page once questions exist.
export const QUIZ2_QUIZ_IDS = ["base2", "followup2", "links2", "double2"] as const;
export type Quiz2QuizId = (typeof QUIZ2_QUIZ_IDS)[number];

export function isQuiz2QuizId(value: string): value is Quiz2QuizId {
  return (QUIZ2_QUIZ_IDS as readonly string[]).includes(value);
}

// Placeholder step shape (kept independent of lib/studySteps' closed StudyStepId
// union so quiz-2 ids don't have to be added there yet).
export type Quiz2Step = {
  id: string;
  label: string;
  path: string;
  time: string;
  subtitle: string;
  completed: boolean;
};

export const QUIZ2_INTRO_SUBTITLE =
  "Quiz 2 — a second problem set. Coming soon.";

// Returns the quiz-2 study steps to show in the dashboard once enabled. Empty
// while the flag is off so callers can splice it into the study flow safely.
export function buildQuiz2Steps(_user: User): Quiz2Step[] {
  if (!QUIZ2_ENABLED) return [];
  // TODO(phase-13+): read real quiz2_*_completed flags off the user, expand into
  // the full quiz-2 survey/quiz sequence, and give each step its own id.
  return [
    {
      id: "quiz2_base",
      label: "Quiz 2 · Part 1",
      path: "/quiz/base2",
      time: "10 min",
      subtitle: QUIZ2_INTRO_SUBTITLE,
      completed: false,
    },
  ];
}
