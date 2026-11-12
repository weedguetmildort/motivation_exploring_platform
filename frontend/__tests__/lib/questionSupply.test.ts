import { participantQuizCombinations, questionSupplyProblems, sharedSets, type SupplyDraft } from "../../lib/questionSupply";

// The same cases as backend tests/test_study_flow_service.py TestQuestionSupplyProblems,
// so the page and the server agree on what can be saved.
const VARIANTS = ["followup", "double", "links"];
const ALL_QUIZZES = ["base", ...VARIANTS];

function counts(perSet: Partial<Record<"a" | "b" | "c" | "d" | "unassigned", number>> = {}) {
  const result: Record<string, number> = { a: 0, b: 0, c: 0, d: 0, unassigned: 0, ...perSet };
  result.total = Object.values(result).reduce((sum, n) => sum + n, 0);
  return result;
}

function supply(overrides: Partial<SupplyDraft> = {}) {
  return questionSupplyProblems({
    mode: "all_variants", quizSetMode: "preset", quizSetMap: {}, questionsPerQuiz: 5,
    variants: VARIANTS, counts: counts(), defaultSets: null, ...overrides,
  });
}
const allOn = (setId: string) => Object.fromEntries(ALL_QUIZZES.map((q) => [q, setId]));

test("four quizzes can share set C with twenty questions", () => {
  expect(supply({ quizSetMap: allOn("c"), counts: counts({ c: 20 }) })).toEqual([]);
});

test("nineteen questions are one short", () => {
  expect(supply({ quizSetMap: allOn("c"), counts: counts({ c: 19 }) })).toEqual([
    "Set C has 19 questions, but 4 quizzes × 5 questions need 20 different ones."]);
});

test("each set is checked for the quizzes that use it", () => {
  const quizSetMap = { base: "a", followup: "a", double: "b", links: "d" };
  expect(supply({ quizSetMap, counts: counts({ a: 9, b: 5, d: 4 }) })).toEqual([
    "Set A has 9 questions, but 2 quizzes × 5 questions need 10 different ones.",
    "Set D has 4 questions, but 1 quiz × 5 questions need 5 different ones."]);
});

test("single-variant participants take only one variant", () => {
  const draft = { mode: "single_variant" as const, quizSetMap: allOn("c"), questionsPerQuiz: 10 };
  expect(supply({ ...draft, counts: counts({ c: 20 }) })).toEqual([]);
  expect(supply({ ...draft, counts: counts({ c: 19 }) })).toEqual([
    "Set C has 19 questions, but 2 quizzes × 10 questions need 20 different ones."]);
});

test("quizzes without a set need the whole bank to cover them", () => {
  expect(supply({ counts: counts({ a: 10, unassigned: 10 }) })).toEqual([]);
  expect(supply({ counts: counts({ a: 10, unassigned: 9 }) })).toEqual([
    "The whole question bank has 19 questions, but 4 quizzes × 5 questions need 20 different ones."]);
});

test("a set also covers quizzes drawing from the whole bank in the worst case", () => {
  const problems = supply({ quizSetMap: { followup: "a", double: "b", links: "c" }, counts: counts({ a: 5, b: 10, c: 10, d: 10 }) });
  expect(problems).toContain("Set A has 5 questions, but 2 quizzes × 5 questions need 10 different ones.");
});

test("default question sets limit where quizzes without a set draw", () => {
  expect(supply({ counts: counts({ a: 10, b: 9, c: 50 }), defaultSets: ["a", "b"] })).toEqual([
    "Default question sets A, B has 19 questions, but 4 quizzes × 5 questions need 20 different ones."]);
  expect(supply({ quizSetMap: { links: "c" }, counts: counts({ a: 10, b: 5, c: 5 }), defaultSets: ["a", "b"] })).toEqual([]);
});

test.each(["random", "balanced_random"] as const)("%s needs a full quiz in every set", (quizSetMode) => {
  expect(supply({ quizSetMode, counts: counts({ a: 5, b: 5, c: 5, d: 5 }) })).toEqual([]);
  expect(supply({ quizSetMode, counts: counts({ a: 5, b: 5, c: 50, d: 4 }) })).toEqual([
    "Set D has 4 questions; every set needs at least 5 because any quiz can draw from any set."]);
});

test("an empty bank reports every shortfall", () => {
  expect(supply({ quizSetMode: "random" })).toHaveLength(4);
  expect(supply()).toEqual(["The whole question bank has 0 questions, but 4 quizzes × 5 questions need 20 different ones."]);
});

test("missing counts are treated as empty sets", () => {
  expect(supply({ quizSetMap: allOn("c"), counts: {} })).toEqual([
    "Set C has 0 questions, but 4 quizzes × 5 questions need 20 different ones."]);
});

test("participant quiz combinations follow the study's structure", () => {
  expect(participantQuizCombinations("all_variants", VARIANTS)).toEqual([ALL_QUIZZES]);
  expect(participantQuizCombinations("single_variant", VARIANTS)).toEqual(VARIANTS.map((v) => ["base", v]));
});

test("shared sets are listed once each", () => {
  expect(sharedSets({ base: "c", followup: "c", double: "a", links: "a" })).toEqual(["a", "c"]);
  expect(sharedSets({ base: "a", followup: "b" })).toEqual([]);
});
