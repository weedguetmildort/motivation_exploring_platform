import { render, screen } from "@testing-library/react";
import StudyShell from "../../components/StudyShell";
import { apiFetch } from "../../lib/fetcher";
jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));
jest.mock("../../lib/auth", () => ({ invalidateMeCache: jest.fn() }));
let route = "/dashboard";
const router = { pathname: route, asPath: route, push: jest.fn(), replace: jest.fn() };
jest.mock("next/router", () => ({ useRouter: () => router }));
beforeEach(() => { sessionStorage.clear(); window.history.replaceState({}, "", "/dashboard"); router.pathname = "/dashboard"; router.asPath = "/dashboard"; });
const first = { study_id: "study-1", label: "Study 1", approved: true, available: true, reason: null, finished: false, total_steps: 5, completed_steps: 2 };
const second = { study_id: "study-2", label: "Study 2", approved: false, available: false, reason: "Available during your interview", finished: false, total_steps: 0, completed_steps: 0 };

test("shows independent progress and a locked interview study", async () => {
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, second] });
  render(<StudyShell><p>Study dashboard</p></StudyShell>);
  expect(await screen.findByRole("button", { name: /Study 1/ })).toHaveTextContent("2 of 5 steps");
  expect(screen.getByRole("button", { name: /Study 2/ })).toBeDisabled();
  expect(screen.getByText("Study dashboard")).toBeInTheDocument();
});

test("an unapproved Study 2 URL never mounts the study page", async () => {
  window.history.replaceState({}, "", "/dashboard?study=study-2");
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, second] });
  render(<StudyShell><p>Protected quiz</p></StudyShell>);
  expect(await screen.findByRole("heading", { name: "Study 2 is locked" })).toBeInTheDocument();
  expect(screen.queryByText("Protected quiz")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Study 1/ })).toBeEnabled();
});

test("quiz pages require leaving the active question before switching", async () => {
  router.pathname = "/quiz/[quiz_id]";
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, { ...second, approved: true, available: true, reason: null }] });
  render(<StudyShell><p>Question</p></StudyShell>);
  expect(await screen.findByRole("button", { name: /Study 2/ })).toBeDisabled();
  expect(screen.getByText(/Return to the dashboard/)).toBeInTheDocument();
});
