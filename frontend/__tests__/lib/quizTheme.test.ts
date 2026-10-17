import { QUIZ_THEMES, getQuizTheme } from "../../lib/quizTheme";

describe("quizTheme", () => {
  it("returns the matching theme for each known quiz id", () => {
    expect(getQuizTheme("base")).toEqual(QUIZ_THEMES.base);
    expect(getQuizTheme("followup")).toEqual(QUIZ_THEMES.followup);
    expect(getQuizTheme("double")).toEqual(QUIZ_THEMES.double);
    expect(getQuizTheme("links")).toEqual(QUIZ_THEMES.links);
  });

  it("falls back to the base theme for unknown quiz ids", () => {
    expect(getQuizTheme("not-a-real-quiz")).toEqual(QUIZ_THEMES.base);
    expect(getQuizTheme("")).toEqual(QUIZ_THEMES.base);
  });

  it("each theme's id matches its dataTheme and its key in QUIZ_THEMES", () => {
    (Object.keys(QUIZ_THEMES) as Array<keyof typeof QUIZ_THEMES>).forEach((key) => {
      const theme = QUIZ_THEMES[key];
      expect(theme.id).toBe(key);
      expect(theme.dataTheme).toBe(key);
    });
  });
});
