// frontend/lib/quizTheme.ts

export type QuizType = "base" | "followup" | "double" | "links";

export type QuizTheme = {
  id: QuizType;
  description: string;
  dataTheme: QuizType;
};

export const QUIZ_THEMES: Record<QuizType, QuizTheme> = {
  base: {
    id: "base",
    description:
      "Ask the assistant questions about the quiz and it will respond directly.",
    dataTheme: "base",
  },
  followup: {
    id: "followup",
    description:
      "After it responds, you'll see a few suggested follow-up questions — click one to keep exploring the topic.",
    dataTheme: "followup",
  },
  double: {
    id: "double",
    description:
      "You'll see two responses side by side. To reply to one specifically, start your message with @AgentA or @AgentB.",
    dataTheme: "double",
  },
  links: {
    id: "links",
    description:
      "The assistant includes source links in its response so you can verify information or read further.",
    dataTheme: "links",
  },
};

export function getQuizTheme(quizId: string): QuizTheme {
  if (quizId in QUIZ_THEMES) {
    return QUIZ_THEMES[quizId as QuizType];
  }
  return QUIZ_THEMES.base;
}
