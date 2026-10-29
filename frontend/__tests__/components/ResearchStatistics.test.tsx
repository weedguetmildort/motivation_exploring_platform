import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ResearchStatistics from "../../components/ResearchStatistics";
import { apiFetch } from "../../lib/fetcher";
jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));
const fetchMock = apiFetch as jest.Mock;
const stats = { paired: { comparisons: [{ metric: "accuracy", left: "followup", right: "links", paired_participants: 12, difference: .2,
  participant_bootstrap_95_interval: [.1, .3], p_exploratory: .02, p_holm: .06 }], limitations: ["Base omitted"] },
  surveys: { associations: [], limitations: "Exploratory associations" } };
const validation = { human_agreement: [], model_validation: [], limitations: "Independent human validation required" };
beforeEach(() => fetchMock.mockReset());

test("analysis is on demand and displays effects in percentage points", async () => {
  fetchMock.mockImplementation((url: string) => Promise.resolve(url.includes("/statistics?") ? stats : validation));
  render(<ResearchStatistics query="search=alice&status=completed" includeTests={false} includeArchived={false} />);
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Compute research analysis" }));
  expect(await screen.findByText("20.0 pp")).toBeInTheDocument();
  expect(screen.getByText("10.0 pp to 30.0 pp")).toBeInTheDocument();
  expect(screen.getByText("0.060")).toBeInTheDocument();
  expect(screen.getByText(/Two independent reviewers/)).toBeInTheDocument();
  expect(fetchMock.mock.calls[0][0]).toContain("search=alice");
});

test("changing filters clears stale statistics until explicitly recomputed", async () => {
  fetchMock.mockImplementation((url: string) => Promise.resolve(url.includes("/statistics?") ? stats : validation));
  const { rerender } = render(<ResearchStatistics query="search=alice" includeTests={false} includeArchived={false} />);
  fireEvent.click(screen.getByRole("button", { name: "Compute research analysis" }));
  await screen.findByText("20.0 pp");
  rerender(<ResearchStatistics query="search=bob" includeTests={false} includeArchived={false} />);
  await waitFor(() => expect(screen.queryByText("20.0 pp")).not.toBeInTheDocument());
  expect(fetchMock).toHaveBeenCalledTimes(2);
});
