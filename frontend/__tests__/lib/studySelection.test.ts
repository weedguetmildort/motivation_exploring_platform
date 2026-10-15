import { selectedStudy, studyApiPath, studyPageUrl } from "../../lib/studySelection";

beforeEach(() => { sessionStorage.clear(); window.history.replaceState({}, "", "/dashboard"); });

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
  expect(studyApiPath("/api/studies/study-2/chat/double", "study-2")).toBe("/api/studies/study-2/chat/double");
});
