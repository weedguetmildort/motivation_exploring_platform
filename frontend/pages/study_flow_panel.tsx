import { selectedStudy } from "../lib/studySelection";
// frontend/pages/study_flow_panel.tsx
//
// Admin control over the participant flow ordering. What a step *is* stays in
// code (backend services/study_flow.py STEP_REGISTRY); this page controls only
// the order variants run in, and whether the order is counterbalanced.
//
// Changes apply to participants who sign up afterwards. Anyone already in the
// study keeps the sequence snapshotted onto their user document, so a mid-study
// reorder cannot scramble a participant's run.
import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout } from "../lib/auth";
import {
  getStudyConfig,
  updateStudyConfig,
  type StudyConfig,
  type QuizSetMode,
} from "../lib/study";

export default function StudyFlowPanel() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [config, setConfig] = useState<StudyConfig | null>(null);

  const [order, setOrder] = useState<string[]>([]);
  const [mode, setMode] = useState<"all_variants" | "single_variant">(
    "all_variants",
  );
  const [counterbalance, setCounterbalance] = useState(true);
  const [quizSetMode, setQuizSetMode] = useState<QuizSetMode>("balanced_random");
  // quiz_id -> set letter. "" means unmapped (draws from the whole pool).
  const [quizSetMap, setQuizSetMap] = useState<Record<string, string>>({});

  const [questionCount, setQuestionCount] = useState(5);
  const [wrongCount, setWrongCount] = useState(3);
  const [wrongRate, setWrongRate] = useState("");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  function applyConfig(c: StudyConfig) {
    setConfig(c);
    setQuestionCount(c.questions_per_quiz ?? 5); setWrongCount(c.wrong_ai_count ?? 3);
    setWrongRate(c.wrong_ai_rate == null ? "" : String(c.wrong_ai_rate));
    setOrder(c.variant_order);
    setMode(c.mode);
    setCounterbalance(c.counterbalance);
    setQuizSetMode(c.quiz_set_mode);
    setQuizSetMap(c.quiz_set_map);
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

        const c = await getStudyConfig();
        if (!cancel) applyConfig(c);
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

  function move(index: number, delta: number) {
    setOrder((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function onSave() {
    setSaving(true);
    setError(null);
    try {
      const c = await updateStudyConfig({
        questions_per_quiz: questionCount, wrong_ai_count: wrongCount,
        wrong_ai_rate: wrongRate === "" ? null : Number(wrongRate),
        mode,
        variant_order: order,
        counterbalance,
        quiz_set_mode: quizSetMode,
        ...(quizSetMode === "preset" ? { quiz_set_map: quizSetMap } : {}),
      });
      applyConfig(c);
      setSavedAt(new Date().toLocaleTimeString());
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Failed to save the flow.");
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

  const serializeMap = (m: Record<string, string>) =>
    Object.entries(m)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([q, s]) => `${q}:${s}`)
      .join(",");

  const dirty =
    !!config &&
    (questionCount !== (config.questions_per_quiz ?? 5) ||
      wrongCount !== (config.wrong_ai_count ?? 3) ||
      wrongRate !== (config.wrong_ai_rate == null ? "" : String(config.wrong_ai_rate)) ||
      mode !== config.mode ||
      counterbalance !== config.counterbalance ||
      order.join(",") !== config.variant_order.join(",") ||
      quizSetMode !== config.quiz_set_mode ||
      serializeMap(quizSetMap) !== serializeMap(config.quiz_set_map));

  // Two quizzes sharing a set is exactly the repetition per-quiz sets exist to
  // prevent, so surface it before the server refuses the save.
  const duplicateSets = (() => {
    const used = Object.values(quizSetMap);
    return [...new Set(used.filter((s) => used.filter((x) => x === s).length > 1))];
  })();

  const unmappedQuizzes = (config?.known_quiz_ids ?? []).filter(
    (q) => !quizSetMap[q],
  );

  // Mirrors backend build_step_order: pre-quiz survey, base quiz, post-base
  // survey, then each variant followed by its own survey.
  function previewSteps(sequence: string[]): string[] {
    const labels = config?.variant_labels ?? {};
    const steps = ["Pre-Quiz Survey", "Base Quiz", "Post-Base Quiz Survey"];
    for (const v of sequence) {
      const label = labels[v] ?? v;
      steps.push(`${label} Quiz`, `Post-${label} Survey`);
    }
    return steps;
  }

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }

  if (!config) return null;

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
            <h1 className="page-title">Study Flow</h1>
            <p className="page-subtitle">
              Control the order participants work through the quiz variants
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
        <div className="rounded-xl border-l-4 border-amber-400 bg-amber-50 p-4 text-sm text-amber-900">
          Changes apply to <strong>new participants only</strong>. Anyone already
          in the study keeps the order they were assigned, so an edit here cannot
          disrupt a run in progress. Saving bumps the flow version (currently{" "}
          <strong>v{config.version}</strong>), which is recorded on each
          participant so cohorts stay distinguishable in analysis.
        </div>

        {error && (
          <div className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700" role="alert">
            {error}
          </div>
        )}

        {/* Mode */}
        <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold">Mode</h2>

          <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-lg border p-3 hover:bg-gray-50">
            <input
              type="radio"
              name="mode"
              className="mt-1"
              checked={mode === "all_variants"}
              onChange={() => setMode("all_variants")}
            />
            <span>
              <span className="block text-sm font-medium">
                Every variant (within-subjects)
              </span>
              <span className="block text-sm text-gray-600">
                Each participant does the base quiz, then all{" "}
                {config.known_variants.length} variants, with a survey after
                each.
              </span>
            </span>
          </label>

          <label className="mt-2 flex cursor-pointer items-start gap-3 rounded-lg border p-3 hover:bg-gray-50">
            <input
              type="radio"
              name="mode"
              className="mt-1"
              checked={mode === "single_variant"}
              onChange={() => setMode("single_variant")}
            />
            <span>
              <span className="block text-sm font-medium">
                One variant per participant (between-subjects)
              </span>
              <span className="block text-sm text-gray-600">
                The original behaviour, kept as a fallback: the base quiz plus a
                single round-robin-assigned variant.
              </span>
            </span>
          </label>
        </section>

        {/* Order */}
        <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold">Variant order</h2>
          <p className="mt-1 text-sm text-gray-600">
            The base quiz always runs first — it is the no-assistance baseline.
            This list controls the variants that follow it.
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

        <section className="rounded-xl border bg-white p-4 space-y-3">
          <h2 className="text-lg font-semibold">Quiz size and AI advice</h2>
          <p className="text-sm text-gray-600">These settings apply to future enrollments. Existing participants keep their saved protocol. A rate overrides the wrong-advice count; question pools smaller than the requested count produce fewer questions, recorded in the export.</p>
          <label className="block">Questions per quiz<input type="number" min={1} max={100} value={questionCount} onChange={e => setQuestionCount(Number(e.target.value))} className="ml-3 rounded border p-2" /></label>
          <label className="block">Questions assigned wrong AI advice<input type="number" min={0} max={100} value={wrongCount} onChange={e => setWrongCount(Number(e.target.value))} className="ml-3 rounded border p-2" /></label>
          <label className="block">Wrong AI advice rate (optional, 0–1)<input type="number" min={0} max={1} step={.05} value={wrongRate} onChange={e => setWrongRate(e.target.value)} className="ml-3 rounded border p-2" /></label>
          {selectedStudy() === "study-2" && <p className="text-sm text-gray-600">Study access is controlled by the backend STUDY_ACCESS_MODE setting ({config.study_access_mode ?? "sequential_approval"}). Study 1 completion: {config.requires_study1_completion ? "required" : "optional"}. Administrator approval: {config.requires_study2_approval !== false ? "required" : "optional"}.</p>}
        </section>
        {/* Question sets */}
        <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold">Question sets</h2>
          <p className="mt-1 text-sm text-gray-600">
            Each quiz draws from its own set, so a participant never sees the
            same question twice. A quiz left unmapped draws from the whole
            question bank and can overlap with other unmapped quizzes.
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
              <span className="block text-sm font-medium">Preset</span>
              <span className="block text-sm text-gray-600">
                A fixed set per quiz, the same for every participant.
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
                Random per participant
              </span>
              <span className="block text-sm text-gray-600">
                Each participant gets their own random set-to-quiz mapping,
                fixed at sign-up. Set usage balances on average, but can be
                uneven in a small sample.
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
                Balanced random (default)
              </span>
              <span className="block text-sm text-gray-600">
                Randomize assignments in blocks of {config.known_sets?.length ?? 4}
                {" "}participants within each quiz order. Each quiz receives every
                question set once per complete block, and each participant uses
                distinct sets. Assignments stay fixed at sign-up. Populate all
                question sets before enrolling participants. Balance applies to
                assigned participants; dropouts can make completed results uneven.
              </span>
            </span>
          </label>

          {quizSetMode === "preset" && (
            <div className="mt-4">
              <ul className="space-y-2">
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
                      <option value="">— whole pool</option>
                      {(config.known_sets ?? []).map((setId) => (
                        <option key={setId} value={setId}>
                          Set {setId.toUpperCase()}
                        </option>
                      ))}
                    </select>
                  </li>
                ))}
              </ul>

              {duplicateSets.length > 0 && (
                <p
                  role="alert"
                  className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700"
                >
                  Set {duplicateSets.map((x) => x.toUpperCase()).join(", ")} is
                  used by more than one quiz. Questions could repeat across those
                  quizzes — give each its own set.
                </p>
              )}

              {duplicateSets.length === 0 && unmappedQuizzes.length > 0 && (
                <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                  {unmappedQuizzes.length} quiz
                  {unmappedQuizzes.length === 1 ? "" : "zes"} still draw from the
                  whole pool and can overlap:{" "}
                  {unmappedQuizzes
                    .map((q) => config.quiz_labels?.[q] ?? q)
                    .join(", ")}
                  .
                </p>
              )}
            </div>
          )}
        </section>

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

        <div className="mt-6 flex items-center justify-end gap-3 pb-10">
          {savedAt && !dirty && (
            <span className="text-sm text-green-700">Saved at {savedAt}</span>
          )}
          <button
            onClick={() => applyConfig(config)}
            disabled={!dirty || saving}
            className="btn-secondary disabled:opacity-50"
          >
            Reset
          </button>
          <button
            onClick={onSave}
            disabled={!dirty || saving || questionCount < 1 || questionCount > 100 || wrongCount < 0 || wrongCount > 100 || (wrongRate !== "" && (Number(wrongRate) < 0 || Number(wrongRate) > 1)) || (quizSetMode === "preset" && duplicateSets.length > 0)}
            className="btn-primary disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save flow"}
          </button>
        </div>
      </div>
    </div>
  );
}
