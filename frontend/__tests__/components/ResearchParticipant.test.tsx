import { fireEvent, render, screen, within } from "@testing-library/react";
import ResearchParticipant from "../../components/ResearchParticipant";
import { apiFetch } from "../../lib/fetcher";
import { person, question, trace } from "../../testFixtures/researchResults";

jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));
jest.mock("../../components/MarkdownMessage", () => ({ __esModule: true, default: ({ content }: { content: string }) => <div>{content}</div> }));
const fetchMock = apiFetch as jest.Mock;
const props = { participantId: "alice", includeTests: false, includeArchived: false, onClose: jest.fn() };
const exactTrace = { ...trace, snapshot_source: "attempt", snapshot: {
  stem: "What is the original value of $x$?", subtitle: "Use the original diagram.", correct_choice_id: "a",
  choices: [{ id: "a", label: "Original correct choice" }, { id: "b", label: "Original selected choice" }],
}, answer: { choice_id: "b", correct_choice_id: "a", correct: false, answered_at: "2026-01-01" } };

beforeEach(() => { fetchMock.mockReset(); });

test("inspection opens a visible dialog with the exact question and marked choices", async () => {
  fetchMock.mockImplementation((url: string) => Promise.resolve(url.includes("/questions/") ? exactTrace : person));
  render(<ResearchParticipant {...props} />);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect links question 1" }));
  const dialog = await screen.findByRole("dialog", { name: "links · Question 1" });
  expect(await within(dialog).findByText("What is the original value of $x$?")).toBeInTheDocument();
  expect(within(dialog).getByText("Use the original diagram.")).toBeInTheDocument();
  const questionSection = within(dialog).getByRole("region", { name: "Question as presented" });
  const choices = within(questionSection).getAllByRole("listitem");
  expect(choices[0]).toHaveTextContent("Correct answer");
  expect(choices[1]).toHaveTextContent("Student selected");
  expect(within(dialog).getByText(/Result: Incorrect/)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/participants/alice/questions/attempt/q1?include_tests=false&include_archived=false"), expect.anything());
  fireEvent.click(within(dialog).getByRole("button", { name: "Close question" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("legacy inspection explains an unavailable snapshot instead of an empty panel", async () => {
  fetchMock.mockImplementation((url: string) => Promise.resolve(url.includes("/questions/")
    ? { ...exactTrace, snapshot: null, snapshot_source: "unavailable", answer: { ...exactTrace.answer, correct: null, correct_choice_id: null } }
    : person));
  render(<ResearchParticipant {...props} />);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect links question 1" }));
  const dialog = await screen.findByRole("dialog");
  expect(await within(dialog).findByText(/exact question and choices were not saved/)).toBeInTheDocument();
  expect(within(dialog).getByText(/Result: Unscored/)).toBeInTheDocument();
  expect(within(dialog).queryByRole("region", { name: "Question as presented" })).not.toBeInTheDocument();
  fireEvent(dialog, new Event("cancel", { bubbles: false }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("failed inspection can be closed and retried", async () => {
  let attempts = 0;
  fetchMock.mockImplementation((url: string) => url.includes("/questions/")
    ? ++attempts === 1 ? Promise.reject(new Error("offline")) : Promise.resolve(exactTrace)
    : Promise.resolve(person));
  render(<ResearchParticipant {...props} />);
  const inspect = await screen.findByRole("button", { name: "Inspect links question 1" });
  fireEvent.click(inspect);
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load this question’s details");
  fireEvent.click(screen.getByRole("button", { name: "Close question" }));
  fireEvent.click(inspect);
  expect(await screen.findByText("What is the original value of $x$?")).toBeInTheDocument();
  expect(attempts).toBe(2);
});

test("opening another question loads the correct attempt and question", async () => {
  const second = { ...question, question_id: "q2", question_position: 2, attempt_id: "other-attempt", quiz_id: "double" };
  fetchMock.mockImplementation((url: string) => Promise.resolve(url.includes("/questions/")
    ? { ...exactTrace, snapshot: { ...exactTrace.snapshot, stem: url.includes("/q2?") ? "Second exact question" : "First exact question" } }
    : { ...person, questions: [question, second] }));
  render(<ResearchParticipant {...props} />);
  fireEvent.click(await screen.findByRole("button", { name: "Inspect links question 1" }));
  expect(await screen.findByText("First exact question")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Close question" }));
  fireEvent.click(screen.getByRole("button", { name: "Inspect double question 2" }));
  expect(await screen.findByText("Second exact question")).toBeInTheDocument();
  expect(screen.queryByText("First exact question")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/other-attempt/q2?"), expect.anything());
});
