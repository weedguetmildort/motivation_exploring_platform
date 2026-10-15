import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../lib/fetcher";
import { demographicLabel, formatMetric, type ParticipantResults, type QuestionResult, type QuestionTrace } from "../lib/researchResults";
import ResearchComparison from "./ResearchComparison";
import MarkdownMessage from "./MarkdownMessage";

const yesNo = (value: boolean | null) => value == null ? "—" : value ? "Yes" : "No";

function QuestionDetails({ participantId, question, options, onClose }: { participantId: string; question: QuestionResult; options: string; onClose: () => void }) {
  const [trace, setTrace] = useState<QuestionTrace | null>(null);
  const [error, setError] = useState(false);
  const [eventPage, setEventPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [showIntervals, setShowIntervals] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (element?.showModal) element.showModal();
    else element?.setAttribute("open", "");
    return () => element?.close?.();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(false);
    apiFetch<QuestionTrace>(`/api/research/participants/${encodeURIComponent(participantId)}/questions/${encodeURIComponent(question.attempt_id)}/${encodeURIComponent(question.question_id)}?${options}&event_page=${eventPage}`, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setTrace(data); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [participantId, question.attempt_id, question.question_id, options, eventPage]);
  const selected = trace?.answer ? trace.answer.choice_id : question.choice_id;
  const correct = trace?.answer ? trace.answer.correct_choice_id : question.correct_choice_id;
  const grade = trace?.answer ? trace.answer.correct : question.correct;
  return <dialog ref={dialog} aria-labelledby="inspected-question-title" onClose={onClose} onCancel={onClose}
    className="m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-[960px] overflow-y-auto rounded-xl border bg-white p-5 shadow-xl backdrop:bg-black/40">
    <div className="space-y-4">
    <div className="flex items-start justify-between gap-4"><h4 id="inspected-question-title" className="font-semibold text-lg">{question.quiz_id} · Question {question.question_position}{question.archived ? " (reset attempt)" : ""}</h4>
      <button type="button" onClick={onClose} className="shrink-0 rounded border px-3 py-1 text-sm">Close question</button></div>
    <p className="text-sm">Student answer: {selected || "—"} · Correct answer: {correct || "—"} · Result: {grade == null ? "Unscored" : grade ? "Correct" : "Incorrect"} · Matched wrong AI: {yesNo(question.matched_wrong_ai)}</p>
    {question.quality_flags.length > 0 && <p className="text-sm text-amber-800">Data quality: {question.quality_flags.map(v => v.replaceAll("_", " ")).join(", ")}</p>}
    <details><summary className="cursor-pointer text-sm font-medium">All recorded question measurements</summary><dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 mt-3 text-sm">{Object.entries(question).filter(([key]) => !["participant_id", "question_stem", "quality_flags"].includes(key)).map(([key, value]) => <div key={key} className="rounded border bg-white p-2"><dt className="text-gray-600">{key.replaceAll("_", " ")}</dt><dd className="break-words">{value == null ? "—" : Array.isArray(value) ? value.join(", ") || "—" : String(value)}</dd></div>)}</dl></details>
    {loading && <p role="status">Loading question interactions…</p>}
    {error && <p role="alert">Unable to load this question’s details. Close it and try Inspect question again.</p>}
    {trace && !loading && !error && <>
      {trace.snapshot ? <section aria-label="Question as presented" className="rounded-lg border p-4 space-y-3">
        <h5 className="font-medium">Question as presented</h5>
        <p className="text-xs text-gray-500">Saved with this quiz attempt.</p>
        {trace.snapshot.stem && <MarkdownMessage content={trace.snapshot.stem} />}
        {trace.snapshot.subtitle && <MarkdownMessage content={trace.snapshot.subtitle} />}
        <ul className="space-y-2 text-sm">{trace.snapshot.choices?.map(choice => <li key={choice.id}
          className={`rounded border p-3 ${choice.id === correct ? "border-green-400 bg-green-50" : choice.id === selected ? "border-red-300 bg-red-50" : "border-gray-200"}`}>
          <div className="flex gap-2 mb-1"><strong className="uppercase">{choice.id}.</strong>{choice.id === selected && <span className="font-medium">Student selected</span>}{choice.id === correct && <span className="font-medium text-green-800">Correct answer</span>}</div>
          <MarkdownMessage content={choice.label} />
        </li>)}</ul>
      </section> : <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">The exact question and choices were not saved with this older attempt. They cannot be reconstructed reliably from the current question bank. Any saved conversation is shown below.</p>}
      <div><h5 className="font-medium mb-2">Conversation</h5>{!trace.messages.length && <p className="text-sm text-gray-600">No completed messages were saved for this question.</p>}
        <div className="space-y-3">{trace.messages.map(message => <div key={message.id} className="rounded border bg-white p-3">
          <p className="text-sm text-gray-600 mb-2">{message.role === "user" ? "Student" : "Assistant"} · {message.created_at}{message.trigger ? ` · ${message.trigger.replaceAll("_", " ")}` : ""}</p>
          {message.intent_labels_heuristic.length > 0 && <p className="text-xs text-gray-500 mb-2">Exploratory prompt labels: {message.intent_labels_heuristic.join(", ")}</p>}
          {(Array.isArray(message.content) ? message.content : [message.content]).map((content, index) => <MarkdownMessage key={index} content={content} />)}
        </div>)}</div>
      </div>
      <details><summary className="cursor-pointer text-sm font-medium">AI requests, failures, and generated follow-up questions ({trace.requests.length})</summary><div className="space-y-2 mt-3">{trace.requests.map(request => <div key={request.request_id} className="rounded border bg-white p-3 text-sm"><p className="font-medium">{request.status} · {request.started_at}</p><p className="whitespace-pre-wrap mt-1">{request.prompt}</p>{request.partial_visible_replies && <div className="mt-2"><p className="text-gray-600">Partial streamed responses:</p>{Object.entries(request.partial_visible_replies).map(([agent, text]) => <p key={agent} className="whitespace-pre-wrap">{agent}: {text}</p>)}</div>}{request.followup_text && <p className="mt-2 whitespace-pre-wrap">Generated questions: {request.followup_text}</p>}</div>)}</div></details>
      <details><summary className="cursor-pointer text-sm font-medium">Recorded interactions ({trace.events_total})</summary>
        <p className="mt-2 text-xs text-gray-500">Elapsed time starts again on each new page or reload. Page identifiers distinguish those timelines.</p>
        <label className="flex gap-2 items-center text-sm mt-3"><input type="checkbox" checked={showIntervals} onChange={e => setShowIntervals(e.target.checked)} />Show periodic timing samples</label>
        <div className="overflow-x-auto mt-3"><table className="w-full text-sm text-left"><thead><tr>{["Time", "Interaction", "Page / sequence", "Details"].map(label => <th key={label} className="p-2 border-b">{label}</th>)}</tr></thead><tbody>{trace.events.filter(e => showIntervals || e.event_type !== "activity_interval").map(event => <tr key={event.event_id} className="border-b"><td className="p-2 whitespace-nowrap">{(event.elapsed_ms / 1000).toFixed(1)}s</td><td className="p-2">{event.event_type.replaceAll("_", " ")}</td><td className="p-2">{event.page_id.slice(0, 8)} / {event.sequence}</td><td className="p-2"><pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(event.data, null, 2)}</pre></td></tr>)}</tbody></table></div>
        <div className="flex gap-3 items-center text-sm mt-3"><button type="button" disabled={eventPage <= 1} onClick={() => setEventPage(v => v - 1)} className="rounded border px-3 py-1 disabled:opacity-40">Earlier interactions</button><span>Page {eventPage} of {Math.max(1, trace.events_pages)}</span><button type="button" disabled={eventPage >= trace.events_pages} onClick={() => setEventPage(v => v + 1)} className="rounded border px-3 py-1 disabled:opacity-40">Later interactions</button></div>
      </details>
      <details><summary className="cursor-pointer text-sm font-medium">Copied text ({trace.copies.length})</summary><div className="space-y-2 mt-3">{trace.copies.map(copy => <div key={copy.id} className="rounded border bg-white p-3 text-sm"><p className="text-gray-600">{copy.created_at}</p><p className="whitespace-pre-wrap mt-1">{copy.text}</p></div>)}</div></details>
    </>}
    </div>
  </dialog>;
}

export default function ResearchParticipant({ participantId, includeTests, includeArchived, onClose }: { participantId: string; includeTests: boolean; includeArchived: boolean; onClose: () => void }) {
  const [data, setData] = useState<ParticipantResults | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedQuestion, setSelectedQuestion] = useState<QuestionResult | null>(null);
  const options = `include_tests=${includeTests}&include_archived=${includeArchived}`;
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(false); setSelectedQuestion(null);
    apiFetch<ParticipantResults>(`/api/research/participants/${encodeURIComponent(participantId)}?${options}`, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setData(result); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [participantId, options]);
  return <section className="rounded-xl border-2 border-blue-200 p-4" aria-label="Individual participant results">
    <div className="flex justify-between gap-3 items-center mb-4"><h2 className="font-semibold text-lg">Participant results</h2><button type="button" className="rounded border px-3 py-2 text-sm" onClick={onClose}>Close participant</button></div>
    {loading && <p role="status">Loading participant results…</p>}{error && <p role="alert">Unable to load participant results.</p>}
    {data && !loading && !error && <div className="space-y-5">
      <div><h3 className="text-lg font-semibold">{data.participant.name || data.participant.participant_id}</h3><p>{data.participant.email}</p><p className="text-sm text-gray-600">ID: {data.participant.participant_id} · Study version: {data.participant.study_flow_version ?? "—"} · Completed study steps: {data.participant.completed_steps.length}/{data.participant.step_order.length}</p></div>
      <dl className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-sm">{Object.entries(data.participant.demographics).map(([key, value]) => <div key={key}><dt className="text-gray-600">{key.replaceAll("_", " ")}</dt><dd>{demographicLabel(key, value)}</dd></div>)}</dl>
      <ResearchComparison overall={data.overall} variants={data.variants} definitions={data.metric_definitions} />
      <div><h3 className="font-semibold mb-3">Question results</h3><div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr>{["Quiz / question", "Answer", "Correct", "Wrong AI exposed", "Matches wrong AI", "Active time", "Typed / suggested prompts", "Selection revisions", "Details"].map(label => <th key={label} className="p-2 border-b">{label}</th>)}</tr></thead><tbody>{data.questions.map(question => <tr key={`${question.attempt_id}:${question.question_id}`} className="border-b">
        <td className="p-2">{question.quiz_id} / {question.question_position}{question.archived ? " (reset)" : ""}<div className="text-xs text-gray-500">Set {question.question_set ?? "—"} · Position {question.variant_position ?? "—"} · {question.attempt_status}</div></td>
        <td className="p-2">{question.choice_id || "—"}</td><td className="p-2">{yesNo(question.correct)}</td><td className="p-2">{yesNo(question.wrong_ai_exposed)}</td><td className="p-2">{yesNo(question.matched_wrong_ai)}</td><td className="p-2">{formatMetric(question.active_ms, "seconds")}</td>
        <td className="p-2">{question.ai_requests ? `${question.manual_prompts} / ${question.suggested_prompts}` : "—"}</td><td className="p-2">{question.telemetry_available ? question.answer_revision_count : "—"}</td>
        <td className="p-2"><button type="button" className="text-blue-700 underline" aria-haspopup="dialog" aria-label={`Inspect ${question.quiz_id} question ${question.question_position}`} onClick={() => setSelectedQuestion(question)}>Inspect question</button></td>
      </tr>)}</tbody></table></div>{!data.questions.length && <p className="mt-3 text-gray-600">This participant has no quiz attempts.</p>}</div>
      {selectedQuestion && <QuestionDetails key={`${selectedQuestion.attempt_id}:${selectedQuestion.question_id}`} participantId={participantId} question={selectedQuestion} options={options} onClose={() => setSelectedQuestion(null)} />}
    </div>}
  </section>;
}
