import SurveyTimeline from "../components/SurveyTimeline";
import NewParticipantSettings from "../components/NewParticipantSettings";
import { DEFAULT_SURVEY_STAGES } from "../lib/surveyConfig";
import type { SurveyStages, VariantSurveyMode } from "../lib/study";
import { selectedStudy, type StudyId } from "../lib/studySelection";
import { questionSupplyProblems, sharedSets, SET_IDS } from "../lib/questionSupply";
// frontend/pages/study_flow_panel.tsx
//
// Admin control over each study's participant flow: survey schedule, variant
// order, quiz size and question sets. Study 1 and Study 2 keep separate
// settings; the tabs choose which one this page edits, independently of the
// admin workspace. What a step *is* stays in code (backend STEP_REGISTRY).
//
// Changes apply to participants who sign up afterwards. Anyone already in the
// study keeps the flow snapshotted onto their record, unless the admin chooses
// to move their unstarted quizzes onto the saved question sets.
import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, invalidateMeCache } from "../lib/auth";
import {
  getStudyConfig,
  updateStudyConfig,
  type StudyConfig,
  type QuizSetMode,
} from "../lib/study";

const STUDIES: { id: StudyId; label: string }[] = [
  { id: "study-1", label: "Study 1" },
  { id: "study-2", label: "Study 2" },
];
const studyLabel = (id: StudyId) => STUDIES.find((s) => s.id === id)?.label ?? id;

function initialStudy(query: Record<string, unknown>): StudyId {
  return query.study === "study-1" || query.study === "study-2" ? query.study : selectedStudy();
}

export default function StudyFlowPanel() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [authorized, setAuthorized] = useState(false);
  const [study, setStudy] = useState<StudyId>(() => initialStudy(router.query ?? {}));
  const [config, setConfig] = useState<StudyConfig | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [order, setOrder] = useState<string[]>([]);
  const [counterbalance, setCounterbalance] = useState(true);
  const [quizSetMode, setQuizSetMode] = useState<QuizSetMode>("balanced_random");
  // quiz_id -> set letter. "" means unmapped (draws from the whole pool).
  const [quizSetMap, setQuizSetMap] = useState<Record<string, string>>({});

  const [surveyMode, setSurveyMode] = useState<VariantSurveyMode>("per_variant");
  const [surveys, setSurveys] = useState<SurveyStages>(DEFAULT_SURVEY_STAGES);
  const [questionCount, setQuestionCount] = useState(5);
  const [wrongCount, setWrongCount] = useState(3);
  const [wrongRate, setWrongRate] = useState("");
  // Study 1 sign-ups' default sets, kept live by the New participants section.
  const [defaultSets, setDefaultSets] = useState<string[] | null>(null);
  const [applyToEnrolled, setApplyToEnrolled] = useState(false);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  function applyConfig(c: StudyConfig) {
    setConfig(c);
    setSurveyMode(c.variant_survey_mode ?? "per_variant");
    setSurveys(c.survey_stages ?? DEFAULT_SURVEY_STAGES);
    setQuestionCount(c.questions_per_quiz ?? 5); setWrongCount(c.wrong_ai_count ?? 3);
    setWrongRate(c.wrong_ai_rate == null ? "" : String(c.wrong_ai_rate));
    setOrder(c.variant_order);
    setCounterbalance(c.counterbalance);
    setQuizSetMode(c.quiz_set_mode);
    setQuizSetMap(c.quiz_set_map);
    setDefaultSets(c.default_question_sets ?? null);
    setApplyToEnrolled(false);
  }

  function setQuizSet(quizId: string, setId: string) {
    setQuizSetMap((prev) => {
      const next = { ...prev };
      if (setId) next[quizId] = setId;
      else delete next[quizId];
      return next;
    });
  }

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;
        if (!res.user.is_admin) {
          router.replace("/dashboard");
          return;
        }
        setAuthorized(true);
      } catch {
        if (!cancel) router.replace("/login");
      } finally {
        if (!cancel) setChecking(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, [router]);

  useEffect(() => {
    if (!authorized) return;
    let cancel = false;
    setConfig(null); setLoadError(null); setError(null); setSaved(null);
    getStudyConfig(study)
      .then((c) => { if (!cancel) applyConfig(c); })
      .catch((e) => { if (!cancel) setLoadError(e instanceof Error ? e.message : "Failed to load the settings."); });
    return () => {
      cancel = true;
    };
  }, [authorized, study]);

  function move(index: number, delta: number) {
    setOrder((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  const serializeMap = (m: Record<string, string>) =>
    Object.entries(m)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([q, s]) => `${q}:${s}`)
      .join(",");

  const supplyChanged =
    !!config &&
    (questionCount !== (config.questions_per_quiz ?? 5) ||
      quizSetMode !== config.quiz_set_mode ||
      (quizSetMode === "preset" && serializeMap(quizSetMap) !== serializeMap(config.quiz_set_map)));

  const dirty =
    !!config &&
    (supplyChanged ||
      surveyMode !== (config.variant_survey_mode ?? "per_variant") ||
      JSON.stringify(surveys) !== JSON.stringify(config.survey_stages ?? DEFAULT_SURVEY_STAGES) ||
      wrongCount !== (config.wrong_ai_count ?? 3) ||
      wrongRate !== (config.wrong_ai_rate == null ? "" : String(config.wrong_ai_rate)) ||
      counterbalance !== config.counterbalance ||
      order.join(",") !== config.variant_order.join(","));

  function switchStudy(next: StudyId) {
    if (next === study) return;
    if (dirty && !window.confirm(`Discard your unsaved changes to ${studyLabel(study)}?`)) return;
    setStudy(next);
  }

  async function onSave() {
    setSaving(true);
    setError(null);
    setSaved(null);
    try {
      const c = await updateStudyConfig({
        survey_stages: surveys,
        variant_survey_mode: surveyMode,
        questions_per_quiz: questionCount, wrong_ai_count: wrongCount,
        wrong_ai_rate: wrongRate === "" ? null : Number(wrongRate),
        variant_order: order,
        counterbalance,
        quiz_set_mode: quizSetMode,
        ...(quizSetMode === "preset" ? { quiz_set_map: quizSetMap } : {}),
        ...(applyToEnrolled ? { apply_to_enrolled: true } : {}),
      }, study);
      applyConfig(c);
      invalidateMeCache();
      const applied = c.applied_participants;
      setSaved(`Saved ${studyLabel(study)} at ${new Date().toLocaleTimeString()}.` +
        (applied == null ? "" : ` Question sets updated for ${applied} participant${applied === 1 ? "" : "s"}.`));
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Failed to save the settings.");
    } finally {
      setSaving(false);
    }
  }

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  // Mirrors backend build_step_order: pre-quiz survey, base quiz, post-base
  // survey, then each variant followed by its own survey.
  function previewSteps(sequence: string[]): string[] {
    const labels = config?.variant_labels ?? {};
    const steps: string[] = [];
    function survey(key: string) { if (surveys[key]?.enabled !== false) steps.push(surveys[key]?.name ?? key); }
    survey("pre_quiz"); steps.push("Base Quiz"); survey("post_base");
    for (const v of sequence) { steps.push(`${labels[v] ?? v} Quiz`); if (surveyMode === "per_variant") survey(`post_${v}`); }
    if (surveyMode === "end_only") survey("post_variant");
    return steps;
  }

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }

  if (!authorized) return null;

  const mode = config?.mode ?? "all_variants";
  const counts = config?.question_counts ?? {};
  const supplyProblems = config
    ? questionSupplyProblems({
        mode, quizSetMode, quizSetMap: quizSetMode === "preset" ? quizSetMap : {}, questionsPerQuiz: questionCount,
        variants: config.known_variants, counts, defaultSets,
      })
    : [];
  const quizzesPerParticipant = mode === "single_variant" ? 2 : 1 + (config?.known_variants.length ?? 0);
  const shared = quizSetMode === "preset" ? sharedSets(quizSetMap) : [];
  const unmappedQuizzes = quizSetMode === "preset" ? (config?.known_quiz_ids ?? []).filter((q) => !quizSetMap[q]) : [];
  const enrolled = config?.enrolled_with_unstarted_quizzes ?? 0;
  const invalidNumbers = questionCount < 1 || questionCount > 100 || wrongCount < 0 || wrongCount > 100 ||
    (wrongRate !== "" && (Number(wrongRate) < 0 || Number(wrongRate) > 1));
  const blockedBySupply = supplyChanged && supplyProblems.length > 0;
  const defaultLabel = (setMode: QuizSetMode) => config?.default_quiz_set_mode === setMode ? ` (default for ${studyLabel(study)})` : "";

  const localPreview: string[][] =
    mode === "single_variant"
      ? order.map((_, i) => [order[(i % order.length + order.length) % order.length]])
      : counterbalance
        ? order.map((_, i) => order.map((__, j) => order[(i + j) % order.length]))
        : [order];

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="site-header">
        <div className="site-header-inner">
          <div>
            <h1 className="page-title">Study Flow · {studyLabel(study)}</h1>
            <p className="page-subtitle">
              Surveys, variant order, quiz size and question sets, set separately for each study
            </p>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => router.push("/admin")} className="btn-primary">
              Back to Admin
            </button>
            <button onClick={onLogout} className="btn-secondary">
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="page-container max-w-4xl">
        <div role="tablist" aria-label="Study to edit" className="flex gap-2 border-b">
          {STUDIES.map((s) => (
            <button key={s.id} type="button" role="tab" aria-selected={study === s.id} onClick={() => switchStudy(s.id)}
              className={`-mb-px rounded-t-lg border px-4 py-2 text-sm font-semibold ${study === s.id
                ? "border-b-white bg-white text-blue-800" : "border-transparent text-gray-500 hover:text-gray-800"}`}>
              {s.label}
            </button>
          ))}
        </div>
        <p className="mt-3 text-sm text-gray-600">
          You are editing <strong>{studyLabel(study)}</strong>. Study 1 and Study 2 keep separate settings; the
          question bank is shared.
        </p>

        {loadError && (
          <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">{loadError}</div>
        )}
        {!config && !loadError && <p className="mt-6 text-gray-500">Loading {studyLabel(study)}…</p>}

        {config && (
          <>
            <div className="mt-4 rounded-xl border-l-4 border-amber-400 bg-amber-50 p-4 text-sm text-amber-900">
              Changes apply to <strong>new participants</strong>. Enrolled participants keep the flow they were
              assigned; to move their unstarted quizzes onto the question sets below, tick the box next to Save.
              Saving bumps the flow version (currently <strong>v{config.version}</strong>), which is recorded on
              each participant so cohorts stay distinguishable in analysis.
            </div>

            {error && (
              <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">
                {error}
              </div>
            )}

            <p className="my-4 text-sm font-medium text-blue-800">
              Quiz structure: {mode === "single_variant" ? "the base quiz plus one assigned variant" : "the base quiz plus every variant"}.
              It is fixed for {studyLabel(study)}.
            </p>

            <SurveyTimeline stages={surveys} onChange={setSurveys} mode={surveyMode} onModeChange={setSurveyMode} />

            {/* Order */}
            <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold">Variant order</h2>
              <p className="mt-1 text-sm text-gray-600">
                The base interaction quiz always runs first.
                {mode === "single_variant"
                  ? " Each participant gets one of these variants, assigned in rotation."
                  : " This list controls the variants that follow it."}
              </p>

              <ul className="mt-4 space-y-2">
                {order.map((v, i) => (
                  <li
                    key={v}
                    className="flex items-center justify-between rounded-lg border bg-gray-50 px-3 py-2"
                  >
                    <span className="text-sm">
                      <span className="mr-2 inline-block w-5 text-gray-400">
                        {i + 1}.
                      </span>
                      <span className="font-medium">
                        {config.variant_labels[v] ?? v}
                      </span>
                      <span className="ml-2 text-xs text-gray-500">({v})</span>
                    </span>

                    <span className="flex gap-1">
                      <button
                        onClick={() => move(i, -1)}
                        disabled={i === 0}
                        aria-label={`Move ${v} up`}
                        className="rounded border px-2 py-1 text-xs disabled:opacity-40"
                      >
                        ↑
                      </button>
                      <button
                        onClick={() => move(i, 1)}
                        disabled={i === order.length - 1}
                        aria-label={`Move ${v} down`}
                        className="rounded border px-2 py-1 text-xs disabled:opacity-40"
                      >
                        ↓
                      </button>
                    </span>
                  </li>
                ))}
              </ul>

              <label className="mt-4 flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={counterbalance}
                  disabled={mode === "single_variant"}
                  onChange={(e) => setCounterbalance(e.target.checked)}
                />
                <span>
                  <span className="block text-sm font-medium">
                    Counterbalance across participants (recommended)
                  </span>
                  <span className="block text-sm text-gray-600">
                    Rotate the list per participant so each variant appears in each
                    position equally often. Without this, every participant sees the
                    same order and variant differences are confounded with position —
                    a variant late in the list looks worse purely from fatigue.
                  </span>
                </span>
              </label>
            </section>

            <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm space-y-3">
              <h2 className="text-lg font-semibold">Quiz size and AI advice</h2>
              <p className="text-sm text-gray-600">These apply to future enrollments; enrolled participants keep their saved quiz size. A rate overrides the wrong-advice count.</p>
              <label className="block">Questions per quiz<input type="number" min={1} max={100} value={questionCount} onChange={e => setQuestionCount(Number(e.target.value))} className="ml-3 rounded border p-2" /></label>
              <label className="block">Questions assigned wrong AI advice<input type="number" min={0} max={100} value={wrongCount} onChange={e => setWrongCount(Number(e.target.value))} className="ml-3 rounded border p-2" /></label>
              <label className="block">Wrong AI advice rate (optional, 0–1)<input type="number" min={0} max={1} step={.05} value={wrongRate} onChange={e => setWrongRate(e.target.value)} className="ml-3 rounded border p-2" /></label>
              {study === "study-2" && <p className="text-sm text-gray-600">Study access is controlled by the backend STUDY_ACCESS_MODE setting ({config.study_access_mode ?? "independent_approval"}). Study 1 completion: {config.requires_study1_completion ? "required" : "optional"}. Administrator approval: {config.requires_study2_approval !== false ? "required" : "optional"}.</p>}
            </section>

            {/* Question sets */}
            <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold">Question sets</h2>
              <p className="mt-1 text-sm text-gray-600">
                A participant never sees the same question twice in {studyLabel(study)}. Quizzes may share a set as
                long as it holds enough questions for all of them: each participant takes {quizzesPerParticipant} quizzes
                of {questionCount} questions.
              </p>

              <p className="mt-3 flex flex-wrap items-center gap-2 text-xs" aria-label="Questions per set">
                <span className="font-semibold uppercase tracking-wide text-gray-500">Question bank</span>
                {SET_IDS.map((s) => (
                  <span key={s} className="rounded-full bg-blue-100 px-2 py-0.5 font-medium text-blue-800">
                    Set {s.toUpperCase()} {counts[s] ?? 0}
                  </span>
                ))}
                <span className="rounded-full bg-gray-100 px-2 py-0.5 font-medium text-gray-600">Unassigned {counts.unassigned ?? 0}</span>
              </p>

              <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-lg border p-3 hover:bg-gray-50">
                <input
                  type="radio"
                  name="quizSetMode"
                  className="mt-1"
                  checked={quizSetMode === "preset"}
                  onChange={() => setQuizSetMode("preset")}
                />
                <span>
                  <span className="block text-sm font-medium">Preset{defaultLabel("preset")}</span>
                  <span className="block text-sm text-gray-600">
                    You choose the set for each quiz, the same for every participant. A quiz with no set draws
                    from the whole bank.
                  </span>
                </span>
              </label>

              <label className="mt-2 flex cursor-pointer items-start gap-3 rounded-lg border p-3 hover:bg-gray-50">
                <input
                  type="radio"
                  name="quizSetMode"
                  className="mt-1"
                  checked={quizSetMode === "random"}
                  onChange={() => setQuizSetMode("random")}
                />
                <span>
                  <span className="block text-sm font-medium">
                    Random per participant{defaultLabel("random")}
                  </span>
                  <span className="block text-sm text-gray-600">
                    Each participant gets their own random set for each quiz, a different set per quiz, fixed at
                    sign-up. Set usage balances on average, but can be uneven in a small sample.
                  </span>
                </span>
              </label>

              <label className="mt-2 flex cursor-pointer items-start gap-3 rounded-lg border p-3 hover:bg-gray-50">
                <input
                  type="radio"
                  name="quizSetMode"
                  className="mt-1"
                  checked={quizSetMode === "balanced_random"}
                  onChange={() => setQuizSetMode("balanced_random")}
                />
                <span>
                  <span className="block text-sm font-medium">
                    Balanced random{defaultLabel("balanced_random")}
                  </span>
                  <span className="block text-sm text-gray-600">
                    Like random, but in blocks of {config.known_sets?.length ?? 4} participants within each quiz
                    order, so each quiz receives every set once per complete block. Every set needs questions.
                    Balance applies to assigned participants; dropouts can make completed results uneven.
                  </span>
                </span>
              </label>

              {quizSetMode === "preset" && (
                <ul className="mt-4 space-y-2">
                  {(config.known_quiz_ids ?? []).map((quizId) => (
                    <li
                      key={quizId}
                      className="flex items-center justify-between rounded-lg border bg-gray-50 px-3 py-2"
                    >
                      <span className="text-sm font-medium">
                        {config.quiz_labels?.[quizId] ?? quizId}
                        <span className="ml-2 text-xs text-gray-500">({quizId})</span>
                      </span>

                      <select
                        aria-label={`Question set for ${config.quiz_labels?.[quizId] ?? quizId}`}
                        value={quizSetMap[quizId] ?? ""}
                        onChange={(e) => setQuizSet(quizId, e.target.value)}
                        className="rounded border px-2 py-1 text-sm"
                      >
                        <option value="">Whole bank</option>
                        {(config.known_sets ?? []).map((setId) => (
                          <option key={setId} value={setId}>
                            Set {setId.toUpperCase()} ({counts[setId] ?? 0} questions)
                          </option>
                        ))}
                      </select>
                    </li>
                  ))}
                </ul>
              )}

              {supplyProblems.length > 0 ? (
                <div role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                  <p className="font-medium">
                    {supplyChanged
                      ? "Not enough questions for these settings. Add questions or change the sets before saving:"
                      : "The saved settings no longer fit the question bank, so some quizzes will not start:"}
                  </p>
                  <ul className="mt-1 list-disc pl-5">
                    {supplyProblems.map((problem) => <li key={problem}>{problem}</li>)}
                  </ul>
                </div>
              ) : (
                <p role="status" className="mt-3 rounded-lg bg-green-50 p-3 text-sm text-green-800">
                  Enough questions: every participant gets {quizzesPerParticipant * questionCount} different questions.
                  {shared.length > 0 && ` Set ${shared.map((s) => s.toUpperCase()).join(", ")} is shared by more than one quiz, without repeats.`}
                  {unmappedQuizzes.length > 0 && ` ${unmappedQuizzes.map((q) => config.quiz_labels?.[q] ?? q).join(", ")} draw${unmappedQuizzes.length === 1 ? "s" : ""} from the whole bank.`}
                </p>
              )}
            </section>

            <NewParticipantSettings study={study} onDefaultSetsChange={setDefaultSets} />

            {/* Preview */}
            <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold">
                What the next participants will get
              </h2>

              <div className="mt-3 space-y-3">
                {localPreview.map((seq, i) => (
                  <div key={i} className="rounded-lg border bg-gray-50 p-3">
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
                      Participant {i + 1}
                      {localPreview.length > 1 &&
                        `, ${localPreview.length + i + 1}, …`}
                    </p>
                    <ol className="flex flex-wrap gap-1 text-xs">
                      {previewSteps(seq).map((label, j) => (
                        <li
                          key={j}
                          className="rounded bg-white px-2 py-1 text-gray-700 ring-1 ring-gray-200"
                        >
                          {j + 1}. {label}
                        </li>
                      ))}
                    </ol>
                  </div>
                ))}
              </div>
            </section>

            <div className="mt-6 flex flex-wrap items-center justify-end gap-3 pb-10">
              <label className="mr-auto flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={applyToEnrolled}
                  disabled={enrolled === 0}
                  onChange={(e) => setApplyToEnrolled(e.target.checked)}
                />
                <span>
                  Also apply the question sets to {enrolled} enrolled participant{enrolled === 1 ? "" : "s"}&apos; unstarted quizzes
                  <span className="block text-xs text-gray-500">
                    Started quizzes keep their questions. Participants already on these sets are not changed.
                  </span>
                </span>
              </label>
              {saved && !dirty && (
                <span role="status" className="text-sm text-green-700">{saved}</span>
              )}
              <button
                onClick={() => applyConfig(config)}
                disabled={(!dirty && !applyToEnrolled) || saving}
                className="btn-secondary disabled:opacity-50"
              >
                Reset
              </button>
              <button
                onClick={onSave}
                disabled={(!dirty && !applyToEnrolled) || saving || invalidNumbers || blockedBySupply}
                className="btn-primary disabled:opacity-50"
              >
                {saving ? "Saving…" : `Save ${studyLabel(study)} settings`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
