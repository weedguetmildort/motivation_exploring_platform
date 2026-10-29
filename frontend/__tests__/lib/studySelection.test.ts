import { forgetStudy, rememberStudy, selectedStudy, studyApiPath, studyPageUrl } from "../../lib/studySelection";

beforeEach(() => { sessionStorage.clear(); window.history.replaceState({}, "", "/dashboard"); });

test("forgetting the selection returns the tab to Study 1", () => {
  rememberStudy("study-2");
  expect(selectedStudy()).toBe("study-2");
  forgetStudy();
  expect(sessionStorage.getItem("mep.selectedStudy")).toBeNull();
  expect(selectedStudy()).toBe("study-1");
});

test("forgetting the selection still honours an explicit URL", () => {
  rememberStudy("study-2");
  forgetStudy();
  window.history.replaceState({}, "", "/dashboard?study=study-2");
  expect(selectedStudy()).toBe("study-2");
});

test("forgetting the selection tolerates blocked storage", () => {
  const removeItem = jest.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(() => forgetStudy()).not.toThrow();
  removeItem.mockRestore();
});

test("explicit URLs override tab-local selection without changing another tab's state", () => {
  sessionStorage.setItem("mep.selectedStudy", "study-2");
  window.history.replaceState({}, "", "/dashboard?study=study-1");
  expect(selectedStudy()).toBe("study-1");
  expect(sessionStorage.getItem("mep.selectedStudy")).toBe("study-2");
  expect(studyPageUrl("/survey?stage=pre_quiz", "study-2")).toBe("/survey?stage=pre_quiz&study=study-2");
});

test("Study 2 requests use explicit routes while login and approvals stay global", () => {
  expect(studyApiPath("/api/quiz/base/state", "study-2")).toBe("/api/studies/study-2/quiz/base/state");
  expect(studyApiPath("/auth/me", "study-2")).toBe("/api/studies/study-2/auth/me");
  expect(studyApiPath("/auth/consent", "study-2")).toBe("/api/studies/study-2/auth/consent");
  expect(studyApiPath("/auth/login", "study-2")).toBe("/auth/login");
  expect(studyApiPath("/api/studies/participants?search=test", "study-2")).toBe("/api/studies/participants?search=test");
  expect(studyApiPath("/api/studies/access-code/redeem", "study-2")).toBe("/api/studies/access-code/redeem");
  expect(studyApiPath("/api/studies/study-2/chat/double", "study-2")).toBe("/api/studies/study-2/chat/double");
});
