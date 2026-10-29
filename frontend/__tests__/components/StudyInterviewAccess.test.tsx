import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import StudyInterviewAccess from "../../components/StudyInterviewAccess";
import { apiFetch } from "../../lib/fetcher";
jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));

test("admin can approve and revoke interview access without resetting progress", async () => {
  const person = { id: "student", name: "Test Student", email: "student@example.com", approved: false,
    available: false, reason: "Available during your interview", status: "not_approved", completed_steps: 0,
    total_steps: 0, approved_at: null, interview_at: null, notes: "", access_history: [] };
  (apiFetch as jest.Mock).mockImplementation((url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") { person.approved = JSON.parse(init.body as string).approved; person.status = "approved"; return Promise.resolve({}); }
    return Promise.resolve({ participants: [{ ...person }], total: 1 });
  });
  render(<StudyInterviewAccess />);
  fireEvent.click(await screen.findByRole("button", { name: "Approve Study 2 access" }));
  expect(await screen.findByText(/Study 2 access approved/)).toBeInTheDocument();
  const patch = (apiFetch as jest.Mock).mock.calls.find(([, init]) => init?.method === "PATCH");
  expect(patch[0]).toBe("/api/studies/participants/student/study-2-access");
  expect(JSON.parse(patch[1].body)).toEqual({ approved: true, notes: "", interview_at: null });
  fireEvent.click(await screen.findByRole("button", { name: "Revoke access" }));
  expect(await screen.findByText(/Study 2 access revoked/)).toHaveTextContent("Saved progress is preserved");
});

test("approval-free mode explains that removing approval does not block access", async () => {
  (apiFetch as jest.Mock).mockResolvedValue({ participants: [{ id: "student", name: "Test Student", email: "student@example.com", approved: true,
    available: true, status: "in_progress", completed_steps: 1, total_steps: 9, notes: "", access_history: [] }], total: 1,
    access_policy: { mode: "independent", requires_approval: false, requires_study1_completion: false } });
  render(<StudyInterviewAccess />);
  expect(await screen.findByText(/removing approval does not block access/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Remove approval" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Revoke access" })).not.toBeInTheDocument();
});
