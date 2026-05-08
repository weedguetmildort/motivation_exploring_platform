// frontend/lib/quizTheme.ts

export type QuizType = "base" | "followup" | "double" | "links";

export type QuizTheme = {
  id: QuizType;
  label: string;
  subtitle: string;
  description: string;
  dataTheme: QuizType;
};

export const QUIZ_THEMES: Record<QuizType, QuizTheme> = {
  base: {
    id: "base",
    label: "Default",
    subtitle: "Default",
    description:
      "Standard AI assistant that provides answers to quiz questions.",
    dataTheme: "base",
  },
  followup: {
    id: "followup",
    label: "Follow-Up Questions",
    subtitle: "Follow-Up Questions",
    description:
      "After responding to your message, the AI generates follow-up questions you can click to continue exploring the topic in more depth.",
    dataTheme: "followup",
  },
  double: {
    id: "double",
    label: "Dual Response",
    subtitle: "Dual Response",
    description:
      "Two independent AI agents each provide their own response side by side.",
    dataTheme: "double",
  },
  links: {
    id: "links",
    label: "Embedded Links",
    subtitle: "Embedded Links",
    description:
      "The AI searches online and embeds citation links directly in its response, so you can verify sources and explore further reading.",
    dataTheme: "links",
  },
};

export function getQuizTheme(quizId: string): QuizTheme {
  if (quizId in QUIZ_THEMES) {
    return QUIZ_THEMES[quizId as QuizType];
  }
  return QUIZ_THEMES.base;
}
