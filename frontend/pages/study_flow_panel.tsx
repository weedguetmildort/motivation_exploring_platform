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

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  function applyConfig(c: StudyConfig) {
    setConfig(c);
    setOrder(c.variant_order);
    setMode(c.mode);
    setCounterbalance(c.counterbalance);
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
        mode,
        variant_order: order,
        counterbalance,
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

  const dirty =
    !!config &&
    (mode !== config.mode ||
      counterbalance !== config.counterbalance ||
      order.join(",") !== config.variant_order.join(","));

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
            disabled={!dirty || saving}
            className="btn-primary disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save flow"}
          </button>
        </div>
      </div>
    </div>
  );
}
