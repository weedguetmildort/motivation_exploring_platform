import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import DashboardStudyAccess from "../../components/DashboardStudyAccess";
import { apiFetch } from "../../lib/fetcher";
import { invalidateMeCache, type User } from "../../lib/auth";

jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));
import { invalidateStudyCatalog } from "../../lib/studyCatalog";
jest.mock("../../lib/auth", () => ({ invalidateMeCache: jest.fn() }));
const push = jest.fn();
jest.mock("next/router", () => ({ useRouter: () => ({ push }) }));
const first = { study_id: "study-1", label: "Study 1", available: true, completed_steps: 4, total_steps: 9, consent_required: false };
const second = { study_id: "study-2", label: "Study 2", available: true, completed_steps: 0, total_steps: 9, consent_required: true };
// Invitation tests exercise the sequential flow; the default mode is independent_approval.
const access_policy = { mode: "sequential_approval", requires_study1_completion: true, requires_approval: true };
const user = { id: "synthetic", study_id: "study-1", is_admin: false } as User;
beforeEach(() => {
  invalidateStudyCatalog(); jest.clearAllMocks(); sessionStorage.clear(); window.history.replaceState({}, "", "/dashboard");
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, second], access_policy });
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
  (apiFetch as jest.Mock).mockResolvedValueOnce({ studies: [first, { ...second, available: false }], access_policy });
  render(<DashboardStudyAccess user={user} />);
  await act(async () => {});
  expect(screen.queryByText("Your interview is available")).not.toBeInTheDocument();
  fireEvent(window, new Event("focus"));
  expect(await screen.findByText("Your interview is available")).toBeInTheDocument();
});

test("a cancelled navigation does not replace the saved tab selection", async () => {
  push.mockResolvedValueOnce(false);
  render(<DashboardStudyAccess user={user} />);
  fireEvent.click(await screen.findByRole("button", { name: "Continue to interview" }));
  await waitFor(() => expect(push).toHaveBeenCalled());
  expect(sessionStorage.getItem("mep.selectedStudy")).toBeNull();
});

test.each(["independent", "independent_approval"])("%s shows the selector to participants, with accurate approval rules", async mode => {
  const approval = mode === "independent_approval";
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, { ...second, available: !approval, reason: approval ? "Available during your interview" : null }],
    access_policy: { mode, requires_study1_completion: false, requires_approval: approval } });
  render(<DashboardStudyAccess user={user} />);
  expect(await screen.findByRole("heading", { name: "Choose a study" })).toBeInTheDocument();
  expect(screen.queryByText("Admin only")).not.toBeInTheDocument();
  expect(screen.queryByText(/Preview progress/)).not.toBeInTheDocument();
  expect(screen.queryByText("Your interview is available")).not.toBeInTheDocument();
  if (approval) {
    expect(screen.getByRole("button", { name: "Locked" })).toBeDisabled();
    expect(screen.getByText("Approval required")).toBeInTheDocument();
    expect(screen.getByText("Available during your interview")).toBeInTheDocument();
  } else {
    fireEvent.click(screen.getByRole("button", { name: "Open Study 2" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/consent?study=study-2"));
    expect(screen.queryByText("Approval required")).not.toBeInTheDocument();
  }
});

test("independent mode supports returning to Study 1 from the participant's Study 2 dashboard", async () => {
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, second], access_policy: {
    mode: "independent", requires_study1_completion: false, requires_approval: false,
  } });
  render(<DashboardStudyAccess user={{ ...user, study_id: "study-2" }} />);
  fireEvent.click(await screen.findByRole("button", { name: "Open Study 1" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/dashboard?study=study-1"));
});

test("sequential mode provides a next-study action without interview or approval copy", async () => {
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, second], access_policy: {
    mode: "sequential", requires_study1_completion: true, requires_approval: false,
  } });
  render(<DashboardStudyAccess user={user} />);
  expect(await screen.findByText("Study 2 is ready")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Choose a study" })).not.toBeInTheDocument();
  expect(screen.queryByText(/researcher asks/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Continue to Study 2" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/consent?study=study-2"));
});

test("sequential mode hides Study 2 until the prerequisite is satisfied", async () => {
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, { ...second, available: false }], access_policy: {
    mode: "sequential", requires_study1_completion: true, requires_approval: false,
  } });
  render(<DashboardStudyAccess user={user} />);
  await act(async () => {});
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(screen.queryByText("Study 2 is ready")).not.toBeInTheDocument();
});

const locked = { ...second, available: false, approved: false, reason: "Enter the access code from your interviewer" };

test("participants unlock Study 2 with the interview access code", async () => {
  const unlocked = { ...second, approved: true };
  (apiFetch as jest.Mock).mockImplementation((url: string) => Promise.resolve(
    url === "/api/studies/access-code/redeem" ? unlocked : url === "/api/studies/catalog" ? { studies: [first, locked] } : {}));
  render(<DashboardStudyAccess user={user} />);
  fireEvent.change(await screen.findByRole("textbox", { name: "Study 2 access code" }), { target: { value: " abcd-efgh " } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock Study 2" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/consent?study=study-2"));
  const redeem = (apiFetch as jest.Mock).mock.calls.find(([url]) => url === "/api/studies/access-code/redeem");
  expect(JSON.parse(redeem[1].body)).toEqual({ code: "abcd-efgh" });
  expect(apiFetch).toHaveBeenCalledWith("/api/studies/study-2/studies/start", { method: "POST" });
});

test("an invalid access code shows the server message and stays retryable", async () => {
  (apiFetch as jest.Mock).mockImplementation((url: string) => url === "/api/studies/access-code/redeem"
    ? Promise.reject(new Error("That access code is not valid. Check it with your interviewer."))
    : Promise.resolve({ studies: [first, locked] }));
  render(<DashboardStudyAccess user={user} />);
  fireEvent.change(await screen.findByRole("textbox", { name: "Study 2 access code" }), { target: { value: "WRONG" } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock Study 2" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("not valid");
  expect(screen.getByRole("button", { name: "Unlock Study 2" })).toBeEnabled();
  expect(push).not.toHaveBeenCalled();
});

test("a code that approves but still needs Study 1 does not navigate", async () => {
  const pending = { ...locked, approved: true, reason: "Complete Study 1 first" };
  (apiFetch as jest.Mock).mockImplementation((url: string) => Promise.resolve(
    url === "/api/studies/access-code/redeem" ? pending : { studies: [first, locked] }));
  render(<DashboardStudyAccess user={user} />);
  fireEvent.change(await screen.findByRole("textbox", { name: "Study 2 access code" }), { target: { value: "ABCD-EFGH" } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock Study 2" }));
  await waitFor(() => expect(screen.queryByRole("textbox", { name: "Study 2 access code" })).not.toBeInTheDocument());
  expect(push).not.toHaveBeenCalled();
});

test("the code form is hidden for admins and when approval is not required", async () => {
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, locked] });
  const { unmount } = render(<DashboardStudyAccess user={{ ...user, is_admin: true }} />);
  await screen.findByRole("heading", { name: "Study workspace" });
  expect(screen.queryByRole("textbox", { name: "Study 2 access code" })).not.toBeInTheDocument();
  unmount(); invalidateStudyCatalog();
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, locked], access_policy: { mode: "independent", requires_study1_completion: false, requires_approval: false } });
  render(<DashboardStudyAccess user={user} />);
  await waitFor(() => expect(apiFetch).toHaveBeenCalled());
  await act(async () => {});
  expect(screen.queryByRole("textbox", { name: "Study 2 access code" })).not.toBeInTheDocument();
});

test("a background refresh does not clear the error from the last action", async () => {
  (apiFetch as jest.Mock).mockImplementation((url: string) => url === "/api/studies/access-code/redeem"
    ? Promise.reject(new Error("That access code is not valid. Check it with your interviewer."))
    : Promise.resolve({ studies: [first, locked] }));
  render(<DashboardStudyAccess user={user} />);
  fireEvent.change(await screen.findByRole("textbox", { name: "Study 2 access code" }), { target: { value: "WRONG" } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock Study 2" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("not valid");
  await act(async () => { fireEvent(window, new Event("focus")); });
  expect(screen.getByRole("alert")).toHaveTextContent("not valid");
});

const pending = { ...locked, approved: true, reason: "Complete Study 1 first" };
const revoked = { ...locked, revoked: true, reason: "Study 2 access was revoked. Contact the research team." };

test("an accepted code that still needs Study 1 says so when no selector is shown", async () => {
  (apiFetch as jest.Mock).mockImplementation((url: string) => Promise.resolve(
    url === "/api/studies/access-code/redeem" ? pending : { studies: [first, locked], access_policy }));
  render(<DashboardStudyAccess user={user} />);
  fireEvent.change(await screen.findByRole("textbox", { name: "Study 2 access code" }), { target: { value: "ABCD-EFGH" } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock Study 2" }));
  expect(await screen.findByRole("heading", { name: "Study 2 is unlocked" })).toBeInTheDocument();
  expect(screen.getByText("Complete Study 1 first. Study 2 opens here once you have finished.")).toBeInTheDocument();
  expect(push).not.toHaveBeenCalled();
});

test("a returning participant whose code was accepted still sees why Study 2 is closed", async () => {
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, pending], access_policy });
  render(<DashboardStudyAccess user={user} />);
  expect(await screen.findByRole("heading", { name: "Study 2 is unlocked" })).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Study 2 access code" })).not.toBeInTheDocument();
});

test.each([
  ["sequential_approval", true],
  ["independent_approval", false],
])("a revoked participant in %s mode gets the reason and no code form", async (mode, sequential) => {
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, revoked],
    access_policy: { mode, requires_study1_completion: sequential, requires_approval: true } });
  render(<DashboardStudyAccess user={user} />);
  expect(await screen.findByText("Study 2 access was revoked. Contact the research team.")).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Study 2 access code" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Study 2 is unlocked" })).not.toBeInTheDocument();
});

test("a participant who still needs the code sees the form, not a duplicate notice", async () => {
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, locked], access_policy });
  render(<DashboardStudyAccess user={user} />);
  expect(await screen.findByRole("textbox", { name: "Study 2 access code" })).toBeInTheDocument();
  expect(screen.queryByText("Enter the access code from your interviewer")).not.toBeInTheDocument();
});

test("a catalog poll sent before the code was redeemed cannot bring the form back", async () => {
  let catalogCalls = 0;
  let releaseStalePoll!: (value: unknown) => void;
  (apiFetch as jest.Mock).mockImplementation((url: string) => {
    if (url === "/api/studies/access-code/redeem") return Promise.resolve(pending);
    catalogCalls += 1;
    if (catalogCalls === 1) return Promise.resolve({ studies: [first, locked], access_policy });
    if (catalogCalls === 2) return new Promise(resolve => { releaseStalePoll = resolve; });
    return Promise.resolve({ studies: [first, pending], access_policy });
  });
  render(<DashboardStudyAccess user={user} />);
  const input = await screen.findByRole("textbox", { name: "Study 2 access code" });
  await act(async () => { fireEvent(window, new Event("focus")); }); // poll now in flight
  fireEvent.change(input, { target: { value: "ABCD-EFGH" } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock Study 2" }));
  expect(await screen.findByRole("heading", { name: "Study 2 is unlocked" })).toBeInTheDocument();
  await act(async () => { releaseStalePoll({ studies: [first, locked], access_policy }); });
  await waitFor(() => expect(catalogCalls).toBe(3));
  expect(screen.queryByRole("textbox", { name: "Study 2 access code" })).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Study 2 is unlocked" })).toBeInTheDocument();
});
