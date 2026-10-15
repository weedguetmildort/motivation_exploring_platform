import { useEffect, useState } from "react";
import { apiFetch } from "../lib/fetcher";
import { demographicLabel, formatMetric, type ParticipantResults, type QuestionResult, type QuestionTrace } from "../lib/researchResults";
import ResearchComparison from "./ResearchComparison";
import MarkdownMessage from "./MarkdownMessage";

const yesNo = (value: boolean | null) => value == null ? "—" : value ? "Yes" : "No";

function QuestionDetails({ participantId, question, options }: { participantId: string; question: QuestionResult; options: string }) {
  const [trace, setTrace] = useState<QuestionTrace | null>(null);
  const [error, setError] = useState(false);
  const [eventPage, setEventPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [showIntervals, setShowIntervals] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(false);
    apiFetch<QuestionTrace>(`/api/research/participants/${encodeURIComponent(participantId)}/questions/${encodeURIComponent(question.attempt_id)}/${encodeURIComponent(question.question_id)}?${options}&event_page=${eventPage}`, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setTrace(data); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [participantId, question.attempt_id, question.question_id, options, eventPage]);
  return <div className="rounded-lg border bg-gray-50 p-4 mt-3 space-y-4">
    <h4 className="font-semibold">Question {question.question_position}: {question.question_stem || question.question_id}</h4>
    <p className="text-sm">Selected: {question.choice_id || "—"} · Correct: {question.correct_choice_id || "—"} · Matched wrong AI: {yesNo(question.matched_wrong_ai)}</p>
    {question.quality_flags.length > 0 && <p className="text-sm text-amber-800">Data quality: {question.quality_flags.map(v => v.replaceAll("_", " ")).join(", ")}</p>}
    <details><summary className="cursor-pointer text-sm font-medium">All recorded question measurements</summary><dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 mt-3 text-sm">{Object.entries(question).filter(([key]) => !["participant_id", "question_stem", "quality_flags"].includes(key)).map(([key, value]) => <div key={key} className="rounded border bg-white p-2"><dt className="text-gray-600">{key.replaceAll("_", " ")}</dt><dd className="break-words">{value == null ? "—" : Array.isArray(value) ? value.join(", ") || "—" : String(value)}</dd></div>)}</dl></details>
    {loading && <p role="status">Loading question interactions…</p>}
    {error && <p role="alert">Unable to load this question’s interactions.</p>}
    {trace && !loading && !error && <>
      {trace.snapshot?.choices && <div><h5 className="font-medium mb-2">Question as presented</h5><p className="text-sm mb-2">{trace.snapshot.subtitle}</p><ul className="space-y-1 text-sm">{trace.snapshot.choices.map(choice => <li key={choice.id}>{choice.id}: {choice.label}</li>)}</ul></div>}
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
  </div>;
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
        <td className="p-2"><button type="button" className="text-blue-700 underline" aria-label={`Inspect ${question.quiz_id} question ${question.question_position}`} onClick={() => setSelectedQuestion(question)}>Inspect question</button></td>
      </tr>)}</tbody></table></div>{!data.questions.length && <p className="mt-3 text-gray-600">This participant has no quiz attempts.</p>}</div>
      {selectedQuestion && <QuestionDetails key={`${selectedQuestion.attempt_id}:${selectedQuestion.question_id}`} participantId={participantId} question={selectedQuestion} options={options} />}
    </div>}
  </section>;
}
