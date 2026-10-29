import { useState, type ChangeEvent } from "react";
import { apiFetch } from "../lib/fetcher";

type Issue = { row: number; message: string };
export type ImportReport = {
  dry_run: boolean; valid: boolean; rows: number; to_import: number; imported: number;
  by_set: Record<string, number>; errors: Issue[]; skipped: Issue[];
};

export const IMPORT_COLUMNS = ["topic", "question", "a", "b", "c", "d", "correct", "set"];
const TEMPLATE = `${IMPORT_COLUMNS.join(",")}\nBasic Probability,"A fair coin is flipped twice. What is the probability of two heads?",0.25,0.5,0.75,1,a,c\n`;
// A long error list is cut off; the first rows are enough to see the pattern.
const SHOWN_ISSUES = 50;

function readText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("Unable to read the file."));
    reader.readAsText(file);
  });
}

function IssueList({ title, issues, tone }: { title: string; issues: Issue[]; tone: "error" | "note" }) {
  if (!issues.length) return null;
  return <div className={tone === "error" ? "text-red-700" : "text-gray-700"}>
    <p className="font-medium">{title}</p>
    <ul className="mt-1 list-disc pl-5">
      {issues.slice(0, SHOWN_ISSUES).map(issue => <li key={`${issue.row}:${issue.message}`}>Row {issue.row}: {issue.message}</li>)}
    </ul>
    {issues.length > SHOWN_ISSUES && <p className="mt-1">…and {issues.length - SHOWN_ISSUES} more.</p>}
  </div>;
}

export default function QuestionImport({ onImported }: { onImported: () => void | Promise<void> }) {
  const [csv, setCsv] = useState<string | null>(null);
  const [fileName, setFileName] = useState("");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  // Changing the key clears the file input after an import.
  const [inputKey, setInputKey] = useState(0);

  async function check(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setReport(null); setError(""); setDone(""); setCsv(null); setFileName(file?.name ?? "");
    if (!file) return;
    setBusy(true);
    try {
      const text = await readText(file);
      setReport(await apiFetch<ImportReport>("/api/questions/import", { method: "POST", body: JSON.stringify({ csv: text, dry_run: true }) }));
      setCsv(text);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to check the file."); }
    finally { setBusy(false); }
  }

  async function runImport() {
    if (csv === null || busy) return;
    setBusy(true); setError("");
    try {
      const result = await apiFetch<ImportReport>("/api/questions/import", { method: "POST", body: JSON.stringify({ csv, dry_run: false }) });
      if (!result.valid) { setReport(result); return; } // the bank changed since the check
      setDone(`Imported ${result.imported} question${result.imported === 1 ? "" : "s"}` +
        (result.skipped.length ? `, skipped ${result.skipped.length} already in the bank` : "") +
        `. Use "Judge difficulty" to set their difficulty.`);
      setReport(null); setCsv(null); setFileName(""); setInputKey(key => key + 1);
      await onImported();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to import the questions."); }
    finally { setBusy(false); }
  }

  const sets = report ? Object.entries(report.by_set).filter(([, count]) => count > 0)
    .map(([set, count]) => `${set === "unassigned" ? "Unassigned" : `Set ${set.toUpperCase()}`} ${count}`) : [];
  return <section aria-labelledby="question-import-title" className="bg-white rounded-xl p-8 shadow-sm border space-y-4 text-left">
    <h2 id="question-import-title" className="text-xl 2xl:text-2xl font-semibold text-center">Import Questions from CSV</h2>
    <p className="text-sm text-gray-600">
      Columns: <code>{IMPORT_COLUMNS.join(", ")}</code>. <code>correct</code> is the letter of the right answer; <code>set</code> may be blank.
      Format the answer columns as plain text in your spreadsheet, or answers such as 2/5 become dates.{" "}
      <a className="text-blue-700 underline" download="questions_template.csv" href={`data:text/csv;charset=utf-8,${encodeURIComponent(TEMPLATE)}`}>Download a template</a>
    </p>
    <label className="block text-sm font-medium">
      Question CSV
      <input key={inputKey} type="file" accept=".csv,text/csv" onChange={check} disabled={busy} className="mt-1 block text-sm" />
    </label>
    {busy && !report && <p role="status" className="text-sm text-gray-600">Checking {fileName}…</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {done && <p role="status" className="text-sm text-green-700">{done}</p>}
    {report && <div className="space-y-3 text-sm">
      {report.valid
        ? <p>{report.to_import} new question{report.to_import === 1 ? "" : "s"} in {fileName}{sets.length ? ` (${sets.join(" · ")})` : ""}.</p>
        : <p role="alert" className="font-medium text-red-700">Nothing was imported. Fix these rows and choose the file again.</p>}
      <IssueList title="Errors" issues={report.errors} tone="error" />
      <IssueList title="Skipped (already in the question bank or repeated in this file)" issues={report.skipped} tone="note" />
      {report.valid && <button type="button" disabled={busy || report.to_import === 0} onClick={runImport}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
        {busy ? "Importing…" : report.to_import === 0 ? "Nothing new to import" : `Import ${report.to_import} question${report.to_import === 1 ? "" : "s"}`}
      </button>}
    </div>}
  </section>;
}
