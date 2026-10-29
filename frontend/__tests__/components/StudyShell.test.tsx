import { act, render, screen, waitFor } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { useEffect } from "react";
import StudyShell from "../../components/StudyShell";
import { invalidateStudyCatalog } from "../../lib/studyCatalog";
import { apiFetch, ApiError } from "../../lib/fetcher";
const { renderToString } = require("react-dom/server.node");
jest.mock("../../lib/fetcher", () => ({ ...jest.requireActual("../../lib/fetcher"), apiFetch: jest.fn() }));
const mockPush = jest.fn(), mockReplace = jest.fn();
const router = { pathname: "/dashboard", asPath: "/dashboard", isReady: true, push: mockPush, replace: mockReplace };
jest.mock("next/router", () => ({ useRouter: () => router }));
beforeEach(() => { invalidateStudyCatalog(); jest.clearAllMocks(); sessionStorage.clear(); window.history.replaceState({}, "", "/dashboard"); router.pathname = "/dashboard"; router.asPath = "/dashboard"; router.isReady = true; });
const first = { study_id: "study-1", label: "Study 1", approved: true, available: true, finished: false, total_steps: 5, completed_steps: 2 };
const second = { study_id: "study-2", label: "Study 2", approved: false, available: false, reason: "Available during your interview", finished: false, total_steps: 0, completed_steps: 0 };

test("quiz pages have no global study switcher", async () => {
  router.pathname = "/quiz/[quiz_id]";
  render(<StudyShell><p>Question</p></StudyShell>);
  expect(await screen.findByText("Question")).toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "Choose study" })).not.toBeInTheDocument();
  expect(apiFetch).not.toHaveBeenCalled();
});

test("an unapproved interview URL never mounts the study page", async () => {
  window.history.replaceState({}, "", "/dashboard?study=study-2");
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, second] });
  render(<StudyShell><p>Protected quiz</p></StudyShell>);
  expect(await screen.findByRole("heading", { name: "Study access unavailable" })).toBeInTheDocument();
  expect(screen.queryByText("Protected quiz")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Return to dashboard" })).toHaveAttribute("href", "/dashboard?study=study-1");
});

test("a participant who needs the access code is sent to where they can enter it", async () => {
  window.history.replaceState({}, "", "/dashboard?study=study-2");
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, { ...second, code_required: true,
    reason: "Enter the access code from your interviewer" }] });
  render(<StudyShell><p>Protected quiz</p></StudyShell>);
  expect(await screen.findByText("Enter the access code from your interviewer")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Enter your access code on the dashboard" })).toHaveAttribute("href", "/dashboard?study=study-1");
});

test("a revoked participant is not told to enter a code", async () => {
  window.history.replaceState({}, "", "/dashboard?study=study-2");
  (apiFetch as jest.Mock).mockResolvedValue({ studies: [first, { ...second, revoked: true, code_required: false,
    reason: "Study 2 access was revoked. Contact the research team." }] });
  render(<StudyShell><p>Protected quiz</p></StudyShell>);
  expect(await screen.findByText("Study 2 access was revoked. Contact the research team.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Return to dashboard" })).toBeInTheDocument();
  expect(screen.queryByText(/access code on the dashboard/)).not.toBeInTheDocument();
});

test("an explicit Study 1 URL replaces stale tab selection before page effects run", async () => {
  sessionStorage.setItem("mep.selectedStudy", "study-2");
  window.history.replaceState({}, "", "/dashboard?study=study-1");
  const loaded = jest.fn();
  function Page() { useEffect(() => { loaded(sessionStorage.getItem("mep.selectedStudy")); }, []); return <p>Page</p>; }
  render(<StudyShell><Page /></StudyShell>);
  await waitFor(() => expect(loaded).toHaveBeenCalledWith("study-1"));
});

test("Study 2 hydrates server markup without replacing it or mounting protected children early", async () => {
  let resolve!: (value: unknown) => void;
  (apiFetch as jest.Mock).mockReturnValue(new Promise(r => { resolve = r; }));
  const page = <StudyShell><p>Protected quiz</p></StudyShell>;
  const container = document.createElement("div");
  // SSR has no browser selection; the initial HTML is always the same.
  window.history.replaceState({}, "", "/dashboard?study=study-1");
  container.innerHTML = renderToString(page);
  const serverStatus = container.firstChild;
  document.body.appendChild(container);
  window.history.replaceState({}, "", "/dashboard?study=study-2");
  const recover = jest.fn();
  let root!: ReturnType<typeof hydrateRoot>;
  await act(async () => { root = hydrateRoot(container, page, { onRecoverableError: recover }); });
  expect(container.firstChild).toBe(serverStatus);
  expect(container).toHaveTextContent("Loading your study");
  expect(container).not.toHaveTextContent("Protected quiz");
  await act(async () => { resolve({ studies: [first, { ...second, available: true }] }); });
  expect(container).toHaveTextContent("Protected quiz");
  expect(recover).not.toHaveBeenCalled();
  act(() => root.unmount()); container.remove();
});

test.each([{}, { studies: [] }])("missing catalog entries fail closed: %j", async result => {
  window.history.replaceState({}, "", "/dashboard?study=study-2");
  (apiFetch as jest.Mock).mockResolvedValue(result);
  render(<StudyShell><p>Protected quiz</p></StudyShell>);
  expect(await screen.findByRole("alert")).toHaveTextContent(/Unable to check study access/);
  expect(screen.queryByText("Protected quiz")).not.toBeInTheDocument();
});

test("expired interview sessions return to login", async () => {
  window.history.replaceState({}, "", "/dashboard?study=study-2");
  (apiFetch as jest.Mock).mockRejectedValue(new ApiError("Expired", 401, "/api/studies/catalog"));
  render(<StudyShell><p>Protected quiz</p></StudyShell>);
  await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login", undefined, undefined));
});

test("explicit study switches survive object navigation", async () => {
  render(<StudyShell><p>Page</p></StudyShell>);
  await screen.findByText("Page");
  await router.push({ pathname: "/dashboard", query: { study: "study-2" } } as never);
  expect(mockPush).toHaveBeenCalledWith({ pathname: "/dashboard", query: { study: "study-2" } }, undefined, undefined);
});

test("a transient access refresh preserves an active page, but revocation unmounts it", async () => {
  jest.useFakeTimers();
  try {
    window.history.replaceState({}, "", "/dashboard?study=study-2");
    (apiFetch as jest.Mock).mockResolvedValueOnce({ studies: [{ ...second, available: true }] })
      .mockRejectedValueOnce(new Error("Network unavailable"))
      .mockResolvedValueOnce({ studies: [second] });
    const mounted = jest.fn(), unmounted = jest.fn();
    function Page() { useEffect(() => { mounted(); return unmounted; }, []); return <p>Active question</p>; }
    render(<StudyShell><Page /></StudyShell>);
    await act(async () => {});
    expect(screen.getByText("Active question")).toBeInTheDocument();
    await act(async () => { jest.advanceTimersByTime(15000); });
    expect(mounted).toHaveBeenCalledTimes(1);
    expect(unmounted).not.toHaveBeenCalled();
    await act(async () => { jest.advanceTimersByTime(15000); });
    expect(screen.getByRole("heading", { name: "Study access unavailable" })).toBeInTheDocument();
    expect(unmounted).toHaveBeenCalledTimes(1);
  } finally { jest.useRealTimers(); }
});
