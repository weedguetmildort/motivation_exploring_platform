import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ResearchCoding from "../../components/ResearchCoding";
import { apiFetch } from "../../lib/fetcher";
jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));
const fetchMock = apiFetch as jest.Mock;
const data = { packet: { packet_hash: "a".repeat(64), answer: { answered_at: "2026-01-01" }, limitations: [],
  turns: [{ turn_id: "m1", role: "user", text: "I computed 2+2=4", trigger: "manual" }], suggestions: [] },
  rubric_version: "conversation-1", partition: "validation", annotations: [],
  rubric: [{ key: "student_reasoning", description: "Observable student reasoning", options: ["not_observed", "specific_step", "insufficient_evidence"] }],
  evaluator: { enabled: false, model: null, reason: "Configure the research evaluator" } };
beforeEach(() => fetchMock.mockReset());

test("loads evidence and saves a human review with current packet hash", async () => {
  fetchMock.mockResolvedValueOnce(data).mockResolvedValueOnce({ _id: "review", source: "human", reviewer_id: "admin", labels: { student_reasoning: "specific_step" }, evidence: [], notes: "" });
  render(<ResearchCoding path="/api/research/participants/u/questions/a/q?include_tests=false" />);
  fireEvent.change(await screen.findByLabelText("student reasoning"), { target: { value: "specific_step" } });
  fireEvent.change(screen.getByLabelText("Evidence source for student reasoning"), { target: { value: "m1" } });
  fireEvent.change(screen.getByLabelText("Exact quote for student reasoning"), { target: { value: "2+2=4" } });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Save human review" }));
  expect(await screen.findByText(/Human review saved/)).toBeInTheDocument();
  const body = JSON.parse(fetchMock.mock.calls[1][1].body);
  expect(body.packet_hash).toBe(data.packet.packet_hash);
  expect(body.independent_review).toBe(true);
  expect(body.evidence).toEqual([{ dimension: "student_reasoning", turn_id: "m1", quote: "2+2=4" }]);
  expect(fetchMock.mock.calls[1][0]).toContain("/coding/review?include_tests=false");
  expect(screen.getByRole("button", { name: "Run optional AI coding" })).toBeDisabled();
});

test("model coding is explicit and remains provisional", async () => {
  fetchMock.mockResolvedValueOnce({ ...data, evaluator: { enabled: true, model: "research-model", reason: null } })
    .mockResolvedValueOnce({ _id: "model", source: "llm", model: "research-model", labels: { student_reasoning: "specific_step" }, evidence: [], notes: "" });
  render(<ResearchCoding path="/api/research/participants/u/questions/a/q" />);
  const run = await screen.findByRole("button", { name: "Run optional AI coding" });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/sends the saved conversation text/)).toBeInTheDocument();
  fireEvent.click(run);
  expect(await screen.findByText(/Provisional model coding saved/)).toBeInTheDocument();
  expect(fetchMock.mock.calls[1][0]).toContain("/coding/evaluate?");
});

test("stale-packet errors are visible and packet reload is available", async () => {
  fetchMock.mockResolvedValueOnce(data).mockRejectedValueOnce(new Error("Conversation changed; reload the packet"));
  render(<ResearchCoding path="/api/research/participants/u/questions/a/q" />);
  fireEvent.click(await screen.findByRole("button", { name: "Save human review" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Conversation changed");
  fetchMock.mockResolvedValueOnce(data);
  fireEvent.click(screen.getByRole("button", { name: "Reload coding packet" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
});
