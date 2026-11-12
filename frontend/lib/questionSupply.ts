// Live check for the Study Flow page: can every participant get different
// questions in every quiz? A participant never sees a question twice within a
// study, so quizzes sharing a set need enough questions between them.
//
// Mirrors backend study_flow.question_supply_problems, messages included; the
// server runs the same rule when the settings are saved.
import type { QuizSetMode } from "./study";

export const SET_IDS = ["a", "b", "c", "d"] as const;
const BASE_QUIZ = "base";

export type SupplyDraft = {
  mode: "all_variants" | "single_variant";
  quizSetMode: QuizSetMode;
  quizSetMap: Record<string, string>;
  questionsPerQuiz: number;
  variants: string[];
  counts: Record<string, number>;   // a..d, unassigned, total
  defaultSets?: string[] | null;    // Study 1 sign-ups' restriction
};

const count = (n: number, singular: string, plural: string) => `${n} ${n === 1 ? singular : plural}`;

/** Every combination of quizzes one participant can be given. */
export function participantQuizCombinations(mode: SupplyDraft["mode"], variants: string[]): string[][] {
  return mode === "single_variant" ? variants.map((v) => [BASE_QUIZ, v]) : [[BASE_QUIZ, ...variants]];
}

export function questionSupplyProblems(draft: SupplyDraft): string[] {
  const { counts, questionsPerQuiz: perQuiz } = draft;
  const have = (setId: string) => counts[setId] ?? 0;
  if (draft.quizSetMode !== "preset") {
    // Any quiz can be handed any set, and each participant uses a set once.
    return SET_IDS.filter((s) => have(s) < perQuiz).map((s) =>
      `Set ${s.toUpperCase()} has ${count(have(s), "question", "questions")}; every set needs at least ${perQuiz} because any quiz can draw from any set.`);
  }

  const pool = SET_IDS.filter((s) => (draft.defaultSets ?? []).includes(s));
  const poolSize = pool.length ? pool.reduce((sum, s) => sum + have(s), 0) : counts.total ?? 0;
  const inPool = (setId: string) => !pool.length || (pool as string[]).includes(setId);
  const setQuizzes: Record<string, number> = {};
  let poolQuizzes = 0;
  for (const quizzes of participantQuizCombinations(draft.mode, draft.variants)) {
    const mapped: Record<string, number> = {};
    for (const quiz of quizzes) {
      const setId = draft.quizSetMap[quiz];
      if (setId) mapped[setId] = (mapped[setId] ?? 0) + 1;
    }
    const unmapped = quizzes.filter((quiz) => !draft.quizSetMap[quiz]).length;
    for (const [setId, used] of Object.entries(mapped)) {
      // Worst case: quizzes without a set draw everything from this one.
      setQuizzes[setId] = Math.max(setQuizzes[setId] ?? 0, used + (inPool(setId) ? unmapped : 0));
    }
    if (unmapped) {
      poolQuizzes = Math.max(poolQuizzes, unmapped + Object.entries(mapped).filter(([s]) => inPool(s)).reduce((sum, [, used]) => sum + used, 0));
    }
  }

  const problems = Object.keys(setQuizzes).sort().flatMap((setId) => {
    const quizzes = setQuizzes[setId];
    return have(setId) < quizzes * perQuiz
      ? [`Set ${setId.toUpperCase()} has ${count(have(setId), "question", "questions")}, but ${count(quizzes, "quiz", "quizzes")} × ${perQuiz} questions need ${quizzes * perQuiz} different ones.`]
      : [];
  });
  if (poolQuizzes && poolSize < poolQuizzes * perQuiz) {
    const source = pool.length ? `Default question sets ${pool.map((s) => s.toUpperCase()).join(", ")}` : "The whole question bank";
    problems.push(`${source} has ${count(poolSize, "question", "questions")}, but ${count(poolQuizzes, "quiz", "quizzes")} × ${perQuiz} questions need ${poolQuizzes * perQuiz} different ones.`);
  }
  return problems;
}

/** Sets used by more than one quiz in a preset map, for a plain note (not an error). */
export function sharedSets(quizSetMap: Record<string, string>): string[] {
  const used = Object.values(quizSetMap);
  return [...new Set(used.filter((s) => used.filter((x) => x === s).length > 1))].sort();
}
