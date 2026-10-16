import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import DashboardStudyAccess from "../../components/DashboardStudyAccess";
import { apiFetch } from "../../lib/fetcher";
import { invalidateMeCache, type User } from "../../lib/auth";

jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));
jest.mock("../../lib/auth", () => ({ invalidateMeCache: jest.fn() }));
const push = jest.fn();
jest.mock("next/router", () => ({ useRouter: () => ({ push }) }));
const first = { study_id: "study-1", label: "Study 1", available: true, completed_steps: 4, total_steps: 9, consent_required: false };
const second = { study_id: "study-2", label: "Study 2", available: true, completed_steps: 0, total_steps: 9, consent_required: true };
const user = { id: "synthetic", study_id: "study-1", is_admin: false } as User;
beforeEach(() => {
  jest.clearAllMocks(); sessionStorage.clear(); window.history.replaceState({}, "", "/dashboard");
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, second] });
  push.mockResolvedValue(true);
});

test("only admins see the study workspace with separate preview progress", async () => {
  render(<DashboardStudyAccess user={{ ...user, is_admin: true }} />);
  expect(await screen.findByRole("heading", { name: "Study workspace" })).toBeInTheDocument();
  expect(screen.getByText("Preview progress: 4 of 9 steps")).toBeInTheDocument();
  expect(screen.getByText("Preview progress: 0 of 9 steps")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Selected" })).toBeDisabled();
  expect(screen.queryByText("Your interview is available")).not.toBeInTheDocument();
});

test("approved participants get an interview invitation without a study selector", async () => {
  render(<DashboardStudyAccess user={user} />);
  expect(await screen.findByText("Your interview is available")).toBeInTheDocument();
  expect(screen.queryByText("Study workspace")).not.toBeInTheDocument();
  expect(screen.queryByText("Study 1")).not.toBeInTheDocument();
  expect(screen.queryByText("Study 2")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Continue to interview" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/consent?study=study-2"));
  expect(apiFetch).toHaveBeenCalledWith("/api/studies/study-2/studies/start", { method: "POST" });
  expect(invalidateMeCache).toHaveBeenCalled();
  expect(sessionStorage.getItem("mep.selectedStudy")).toBe("study-2");
});

test.each([false, undefined])("unavailable interview is hidden: %s", async available => {
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, { ...second, available }] });
  render(<DashboardStudyAccess user={user} />);
  await waitFor(() => expect(apiFetch).toHaveBeenCalled());
  expect(screen.queryByText("Your interview is available")).not.toBeInTheDocument();
  expect(screen.queryByText("Study workspace")).not.toBeInTheDocument();
});

test("an approved session resumes its existing progress without repeating consent", async () => {
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, { ...second, consent_required: false, completed_steps: 4 }] });
  render(<DashboardStudyAccess user={{ ...user, is_admin: true }} />);
  fireEvent.click(await screen.findByRole("button", { name: "Open Study 2" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/dashboard?study=study-2"));
});

test("switching back to Study 1 does not start an interview enrollment", async () => {
  render(<DashboardStudyAccess user={{ ...user, study_id: "study-2", is_admin: true }} />);
  fireEvent.click(await screen.findByRole("button", { name: "Open Study 1" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/dashboard?study=study-1"));
  expect(apiFetch).toHaveBeenCalledTimes(1);
});

test("a rejected start keeps the user on the dashboard and displays the error", async () => {
  render(<DashboardStudyAccess user={user} />);
  await screen.findByText("Your interview is available");
  (apiFetch as jest.Mock).mockRejectedValueOnce(new Error("Approval expired"));
  fireEvent.click(screen.getByRole("button", { name: "Continue to interview" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Approval expired");
  expect(push).not.toHaveBeenCalled();
  expect(sessionStorage.getItem("mep.selectedStudy")).toBeNull();
});

test("approval received during an interview appears on window focus", async () => {
  (apiFetch as jest.Mock).mockResolvedValueOnce({ studies: [first, { ...second, available: false }] });
  render(<DashboardStudyAccess user={user} />);
  await act(async () => {});
  expect(screen.queryByText("Your interview is available")).not.toBeInTheDocument();
  fireEvent(window, new Event("focus"));
  expect(await screen.findByText("Your interview is available")).toBeInTheDocument();
});
