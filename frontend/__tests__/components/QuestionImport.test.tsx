import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import QuestionImport, { IMPORT_COLUMNS, type ImportReport } from "../../components/QuestionImport";
import { apiFetch } from "../../lib/fetcher";

jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));
const mockApiFetch = apiFetch as jest.Mock;

const CSV = "topic,question,a,b,c,d,correct,set\nT,Q,1,2,3,4,a,c\nU,R,5,6,7,8,b,\n";
const report = (overrides: Partial<ImportReport> = {}): ImportReport => ({
  dry_run: true, valid: true, rows: 2, to_import: 2, imported: 0,
  by_set: { a: 0, b: 0, c: 1, d: 0, unassigned: 1 }, errors: [], skipped: [], ...overrides,
});

function choose(text = CSV, name = "bank.csv") {
  fireEvent.change(screen.getByLabelText("Question CSV"), { target: { files: [new File([text], name, { type: "text/csv" })] } });
}
const bodies = () => mockApiFetch.mock.calls.map(([, init]) => JSON.parse(init.body));

beforeEach(() => mockApiFetch.mockReset());

test("choosing a file checks it without importing and shows what would be added", async () => {
  mockApiFetch.mockResolvedValue(report());
  render(<QuestionImport onImported={jest.fn()} />);
  choose();
  expect(await screen.findByText("2 new questions in bank.csv (Set C 1 · Unassigned 1).")).toBeInTheDocument();
  expect(mockApiFetch).toHaveBeenCalledWith("/api/questions/import", expect.objectContaining({ method: "POST" }));
  expect(bodies()).toEqual([{ csv: CSV, dry_run: true }]);
  expect(screen.getByRole("button", { name: "Import 2 questions" })).toBeEnabled();
});

test("importing sends the same file, reports the result and refreshes the list", async () => {
  const onImported = jest.fn();
  mockApiFetch.mockResolvedValueOnce(report()).mockResolvedValueOnce(report({ dry_run: false, imported: 2 }));
  render(<QuestionImport onImported={onImported} />);
  choose();
  fireEvent.click(await screen.findByRole("button", { name: "Import 2 questions" }));
  expect(await screen.findByText('Imported 2 questions. Use "Judge difficulty" to set their difficulty.')).toBeInTheDocument();
  expect(bodies()[1]).toEqual({ csv: CSV, dry_run: false });
  expect(onImported).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("button", { name: /Import \d/ })).not.toBeInTheDocument();
  expect((screen.getByLabelText("Question CSV") as HTMLInputElement).value).toBe("");
});

test("row errors are listed and block the import", async () => {
  mockApiFetch.mockResolvedValue(report({ valid: false, to_import: 1, errors: [
    { row: 3, message: "correct must be a, b, c or d (found 'z')" },
    { row: 7, message: "choice b ('2/5/2026') looks like a date; format the answer columns as plain text before exporting" },
  ] }));
  render(<QuestionImport onImported={jest.fn()} />);
  choose();
  expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was imported. Fix these rows and choose the file again.");
  expect(screen.getByText("Row 3: correct must be a, b, c or d (found 'z')")).toBeInTheDocument();
  expect(screen.getByText(/Row 7: choice b \('2\/5\/2026'\) looks like a date/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Import/ })).not.toBeInTheDocument();
});

test("duplicates are listed as skipped and are not counted as new", async () => {
  const onImported = jest.fn();
  mockApiFetch.mockResolvedValueOnce(report({ to_import: 1, by_set: { a: 0, b: 0, c: 1, d: 0, unassigned: 0 },
    skipped: [{ row: 3, message: "Already in the question bank; skipped" }] }))
    .mockResolvedValueOnce(report({ dry_run: false, to_import: 1, imported: 1, skipped: [{ row: 3, message: "Already in the question bank; skipped" }] }));
  render(<QuestionImport onImported={onImported} />);
  choose();
  expect(await screen.findByText("1 new question in bank.csv (Set C 1).")).toBeInTheDocument();
  expect(screen.getByText("Row 3: Already in the question bank; skipped")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Import 1 question" }));
  expect(await screen.findByText(/Imported 1 question, skipped 1 already in the bank\./)).toBeInTheDocument();
});

test("a file with nothing new cannot be imported", async () => {
  mockApiFetch.mockResolvedValue(report({ to_import: 0, by_set: { a: 0, b: 0, c: 0, d: 0, unassigned: 0 },
    skipped: [{ row: 2, message: "Already in the question bank; skipped" }] }));
  render(<QuestionImport onImported={jest.fn()} />);
  choose();
  expect(await screen.findByRole("button", { name: "Nothing new to import" })).toBeDisabled();
});

test("a long error list is cut off with a count", async () => {
  const errors = Array.from({ length: 53 }, (_, index) => ({ row: index + 2, message: "topic is empty" }));
  mockApiFetch.mockResolvedValue(report({ valid: false, errors }));
  render(<QuestionImport onImported={jest.fn()} />);
  choose();
  expect(await screen.findByText("…and 3 more.")).toBeInTheDocument();
  expect(screen.getAllByText(/^Row \d+: topic is empty$/)).toHaveLength(50);
});

test("a failed check shows the server message", async () => {
  mockApiFetch.mockRejectedValue(new Error("Admin only"));
  render(<QuestionImport onImported={jest.fn()} />);
  choose();
  expect(await screen.findByRole("alert")).toHaveTextContent("Admin only");
  expect(screen.queryByRole("button", { name: /Import/ })).not.toBeInTheDocument();
});

test("a failed import keeps the preview so it can be retried", async () => {
  const onImported = jest.fn();
  mockApiFetch.mockResolvedValueOnce(report()).mockRejectedValueOnce(new Error("Network unavailable")).mockResolvedValueOnce(report({ dry_run: false, imported: 2 }));
  render(<QuestionImport onImported={onImported} />);
  choose();
  fireEvent.click(await screen.findByRole("button", { name: "Import 2 questions" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Network unavailable");
  expect(onImported).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Import 2 questions" }));
  await waitFor(() => expect(onImported).toHaveBeenCalledTimes(1));
});

test("an import the server now rejects shows the new errors instead of succeeding", async () => {
  const onImported = jest.fn();
  mockApiFetch.mockResolvedValueOnce(report())
    .mockResolvedValueOnce(report({ dry_run: false, valid: false, errors: [{ row: 2, message: "topic is empty" }] }));
  render(<QuestionImport onImported={onImported} />);
  choose();
  fireEvent.click(await screen.findByRole("button", { name: "Import 2 questions" }));
  expect(await screen.findByText("Row 2: topic is empty")).toBeInTheDocument();
  expect(onImported).not.toHaveBeenCalled();
});

test("choosing another file replaces the previous preview", async () => {
  mockApiFetch.mockResolvedValueOnce(report()).mockResolvedValueOnce(report({ to_import: 1, by_set: { a: 1, b: 0, c: 0, d: 0, unassigned: 0 } }));
  render(<QuestionImport onImported={jest.fn()} />);
  choose();
  await screen.findByText(/2 new questions in bank.csv/);
  choose("topic,question,a,b,c,d,correct,set\nV,S,1,2,3,4,a,a\n", "second.csv");
  expect(await screen.findByText("1 new question in second.csv (Set A 1).")).toBeInTheDocument();
  expect(screen.queryByText(/bank.csv/)).not.toBeInTheDocument();
});

test("the template link downloads the expected header", () => {
  render(<QuestionImport onImported={jest.fn()} />);
  const link = screen.getByRole("link", { name: "Download a template" });
  expect(link).toHaveAttribute("download", "questions_template.csv");
  const template = decodeURIComponent(link.getAttribute("href")!.split(",").slice(1).join(","));
  expect(template.split("\n")[0]).toBe(IMPORT_COLUMNS.join(","));
  expect(IMPORT_COLUMNS).toEqual(["topic", "question", "a", "b", "c", "d", "correct", "set"]);
  // The example answers must not be ones a spreadsheet turns into dates.
  expect(template).not.toMatch(/,\d{1,2}\/\d{1,2},/);
});
