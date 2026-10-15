import { render, screen, fireEvent, waitFor, act, within } from "@testing-library/react";
import ResearchSummary from "../../components/ResearchSummary";
import { apiFetch } from "../../lib/fetcher";
import { results, person, trace } from "../../testFixtures/researchResults";
jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));

jest.mock("../../components/MarkdownMessage", () => ({ __esModule: true, default: ({ content }: { content: string }) => <div>{content}</div> }));
beforeEach(() => { (apiFetch as jest.Mock).mockReset(); });

test("distinguishes unavailable rates from zero and shows contributing counts", async () => {
  (apiFetch as jest.Mock).mockResolvedValue(results);
  render(<ResearchSummary />);
  expect(await screen.findByText("Alice Student")).toBeInTheDocument();
  expect(screen.getAllByText("50.0%").length).toBeGreaterThan(0);
  expect(screen.getByText("0.0%")).toBeInTheDocument();
  expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.getByText("1 person · 1 question")).toBeInTheDocument();
  expect(screen.getByText(/does not establish that AI changed/)).toBeInTheDocument();
});

test("combines demographic and quiz filters in the server request", async () => {
  (apiFetch as jest.Mock).mockResolvedValue(results);
  render(<ResearchSummary />);
  fireEvent.change(await screen.findByLabelText("Gender"), { target: { value: "Female" } });
  fireEvent.change(screen.getByLabelText("Year in program"), { target: { value: "first" } });
  fireEvent.change(screen.getByLabelText("Quiz type"), { target: { value: "links" } });
  await waitFor(() => {
    const url = (apiFetch as jest.Mock).mock.calls.at(-1)[0];
    const params = new URL(url, "http://localhost").searchParams;
    expect(JSON.parse(params.get("filters")!)).toEqual({ gender: "Female", year: "first" });
    expect(params.get("quiz_id")).toBe("links");
  });
});

test("debounces identity search and resets to the first directory page", async () => {
  (apiFetch as jest.Mock).mockResolvedValue(results);
  render(<ResearchSummary />);
  await screen.findByText("Alice Student");
  jest.useFakeTimers();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "alice@test.edu" } });
  await act(async () => { jest.advanceTimersByTime(300); });
  expect(new URL((apiFetch as jest.Mock).mock.calls.at(-1)[0], "http://localhost").searchParams.get("search")).toBe("alice@test.edu");
  jest.useRealTimers();
});

test("opens an individual participant and their question transcript", async () => {
  (apiFetch as jest.Mock).mockImplementation((url: string) => Promise.resolve(url.includes("/questions/") ? trace : url.includes("/participants/") ? person : results));
  render(<ResearchSummary />);
  fireEvent.click(await screen.findByRole("button", { name: "View results for Alice Student" }));
  const detail = await screen.findByRole("region", { name: "Individual participant results" });
  fireEvent.click(await within(detail).findByRole("button", { name: "Inspect links question 1" }));
  expect(await screen.findByText("Please double check this answer")).toBeInTheDocument();
  expect(screen.getByText(/Exploratory prompt labels: double_check/)).toBeInTheDocument();
});

test("ignores stale filter responses", async () => {
  let resolveOld: (value: typeof results) => void = () => {};
  let calls = 0;
  (apiFetch as jest.Mock).mockImplementation(() => {
    calls++;
    return calls === 1 ? new Promise(resolve => { resolveOld = resolve; }) : Promise.resolve({ ...results, participants: [], matched_accounts: 0 });
  });
  render(<ResearchSummary />);
  fireEvent.change(screen.getByLabelText("Attempt status"), { target: { value: "all" } });
  await screen.findByText("No participants match these filters.");
  await act(async () => { resolveOld(results); });
  expect(screen.queryByText("Alice Student")).not.toBeInTheDocument();
});

test("shows a server validation error and allows resetting filters", async () => {
  (apiFetch as jest.Mock).mockResolvedValueOnce(results).mockRejectedValueOnce(new Error("Minimum age cannot exceed maximum age")).mockResolvedValue(results);
  render(<ResearchSummary />);
  await screen.findByText("Alice Student");
  fireEvent.change(screen.getByLabelText("Minimum age"), { target: { value: "90" } });
  expect(await screen.findByRole("alert")).toHaveTextContent("Minimum age cannot exceed maximum age");
  fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
  expect(await screen.findByText("Alice Student")).toBeInTheDocument();
});
