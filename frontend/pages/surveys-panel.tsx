import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { apiFetch } from "../lib/fetcher";

export default function SurveyPanelPage() {
  type SurveyStage = "pre_quiz" | "mid_quiz" | "end_quiz" | "final" | string;

  type SurveyItemType = "likert" | "text" | "single_select" | "multi_select";

  type SurveyOption = { id: string; label: string };

  type SurveyItem = {
    id: string;
    stage: SurveyStage;
    category?: string | null;
    prompt: string;
    type: SurveyItemType;
    required?: boolean;
    reverse_scored?: boolean;

    // Likert
    scale_min?: number;
    scale_max?: number;
    scale_left_label?: string | null;
    scale_right_label?: string | null;

    // Select types (future)
    options?: SurveyOption[];

    created_at?: string;
    updated_at?: string;
  };

  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  // Create form
  const [stage, setStage] = useState<SurveyStage>("pre_quiz");
  const [category, setCategory] = useState("");
  const [prompt, setPrompt] = useState("");
  const [required, setRequired] = useState(true);
  const [reverseScored, setReverseScored] = useState(false);

  // Likert fields (default 1–5)
  const [scaleMin, setScaleMin] = useState(1);
  const [scaleMax, setScaleMax] = useState(5);
  const [scaleLeftLabel, setScaleLeftLabel] = useState("Strongly disagree");
  const [scaleRightLabel, setScaleRightLabel] = useState("Strongly agree");

  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // List + edit
  const [items, setItems] = useState<SurveyItem[]>([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [itemsError, setItemsError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Partial<SurveyItem>>({});
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const stages = useMemo(
    () => [
      { value: "pre_quiz", label: "Pre-quiz" },
      { value: "mid_quiz", label: "Mid-quiz" },
      { value: "end_quiz", label: "End-quiz" },
      { value: "final", label: "Final" },
    ],
    [],
  );

  // --- auth gate (admin only) ---
  useEffect(() => {
    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;

        if (!res.user.is_admin) {
          window.location.href = "/dashboard";
          return;
        }
        setUser(res.user);
      } catch {
        if (!cancel) window.location.href = "/login";
      } finally {
        if (!cancel) setChecking(false);
      }
    })();

    return () => {
      cancel = true;
    };
  }, []);

  // --- load survey items ---
  useEffect(() => {
    if (!user) return;

    let cancel = false;

    async function loadItems() {
      setLoadingItems(true);
      setItemsError(null);
      try {
        // [NOTE] adjust path if your backend differs
        const data = await apiFetch<SurveyItem[]>("/api/surveys/items"); // [IMPORTANT]
        if (!cancel) setItems(data);
      } catch (e) {
        console.error(e);
        if (!cancel) setItemsError("Failed to load survey questions.");
      } finally {
        if (!cancel) setLoadingItems(false);
      }
    }

    loadItems();

    return () => {
      cancel = true;
    };
  }, [user]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading survey questions panel…</div>
      </div>
    );
  }

  if (!user) return null;

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);

    if (!prompt.trim()) {
      setMessage("Prompt is required.");
      return;
    }
    if (scaleMin >= scaleMax) {
      setMessage("Likert scale min must be less than max.");
      return;
    }

    setSaving(true);
    try {
      // [NOTE] adjust path if your backend differs
      const created = await apiFetch<SurveyItem>("/api/surveys/items", {
        method: "POST",
        body: JSON.stringify({
          stage,
          category: category.trim() || null,
          prompt: prompt.trim(),
          type: "likert",
          required,
          reverse_scored: reverseScored,
          scale_min: scaleMin,
          scale_max: scaleMax,
          scale_left_label: scaleLeftLabel || null,
          scale_right_label: scaleRightLabel || null,
        }),
      });

      setItems((prev) => [created, ...prev]);
      setPrompt("");
      setCategory("");
      setReverseScored(false);
      setRequired(true);
      setMessage("Survey question added.");
    } catch (e) {
      console.error(e);
      setMessage("Failed to add survey question.");
    } finally {
      setSaving(false);
    }
  }

  function beginEdit(it: SurveyItem) {
    setEditingId(it.id);
    setEditDraft({
      ...it,
      category: it.category ?? "",
      scale_left_label: it.scale_left_label ?? "",
      scale_right_label: it.scale_right_label ?? "",
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditDraft({});
  }

  async function saveEdit(id: string) {
    setSavingEdit(true);
    try {
      // Only send editable fields
      const payload = {
        stage: editDraft.stage,
        category: (editDraft.category as any)?.trim?.()
          ? editDraft.category
          : null,
        prompt: (editDraft.prompt ?? "").toString().trim(),
        required: !!editDraft.required,
        reverse_scored: !!editDraft.reverse_scored,

        // likert fields
        scale_min: editDraft.scale_min,
        scale_max: editDraft.scale_max,
        scale_left_label: editDraft.scale_left_label || null,
        scale_right_label: editDraft.scale_right_label || null,
      };

      // [NOTE] adjust path if your backend differs
      const updated = await apiFetch<SurveyItem>(`/api/surveys/items/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });

      setItems((prev) => prev.map((x) => (x.id === id ? updated : x)));
      cancelEdit();
    } catch (e) {
      console.error(e);
      alert("Failed to update survey question.");
    } finally {
      setSavingEdit(false);
    }
  }

  async function deleteItem(id: string) {
    if (!window.confirm("Delete this survey question?")) return;

    setDeletingId(id);
    try {
      // [NOTE] adjust path if your backend differs
      await apiFetch<void>(`/api/surveys/items/${id}`, { method: "DELETE" });
      setItems((prev) => prev.filter((x) => x.id !== id));
    } catch (e) {
      console.error(e);
      alert("Failed to delete survey question.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">
              Survey Questions Panel
            </h1>
            <p className="text-sm text-gray-600">
              Manage stage-based surveys (pre-quiz, mid-quiz, end-quiz, final).
            </p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="text-sm px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
            >
              Back to Dashboard
            </button>
            <button
              onClick={onLogout}
              className="bg-gray-100 hover:bg-gray-200 px-4 py-2 rounded-lg text-sm"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Create */}
      <div className="max-w-6xl mx-auto p-6">
        <div className="bg-white rounded-xl p-8 shadow-sm border">
          <h2 className="text-xl font-semibold mb-4">Add Survey Question</h2>

          <form onSubmit={onCreate} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium mb-1">Stage</label>
                <select
                  value={stage}
                  onChange={(e) => setStage(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                >
                  {stages.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">
                  Category (optional)
                </label>
                <input
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  placeholder="e.g., TRUST, NFC, AI Literacy"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Prompt (Likert statement)
              </label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                rows={3}
                placeholder="e.g., I could rely on an AI chatbot for assistance while problem-solving."
                required
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium mb-1">
                  Left label
                </label>
                <input
                  value={scaleLeftLabel}
                  onChange={(e) => setScaleLeftLabel(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">
                  Right label
                </label>
                <input
                  value={scaleRightLabel}
                  onChange={(e) => setScaleRightLabel(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex items-center gap-2">
                <input
                  id="required"
                  type="checkbox"
                  checked={required}
                  onChange={(e) => setRequired(e.target.checked)}
                />
                <label htmlFor="required" className="text-sm">
                  Required
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="reverse"
                  type="checkbox"
                  checked={reverseScored}
                  onChange={(e) => setReverseScored(e.target.checked)}
                />
                <label htmlFor="reverse" className="text-sm">
                  Reverse-scored (R)
                </label>
              </div>
            </div>

            {message && (
              <div className="text-sm text-gray-700" role="status">
                {message}
              </div>
            )}

            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save survey question"}
            </button>
          </form>
        </div>
      </div>

      {/* List */}
      <div className="max-w-6xl mx-auto pt-0 px-6 pb-6">
        <div className="bg-white rounded-xl p-8 shadow-sm border">
          <h2 className="text-xl font-semibold mb-2">View Survey Questions</h2>

          {loadingItems && (
            <p className="text-sm text-gray-500">Loading survey questions…</p>
          )}
          {itemsError && (
            <p className="text-sm text-red-600 mb-2">{itemsError}</p>
          )}
          {!loadingItems && !itemsError && items.length === 0 && (
            <p className="text-sm text-gray-500">No survey questions yet.</p>
          )}

          {!loadingItems && items.length > 0 && (
            <div className="mt-4 space-y-3">
              {items.map((it) => {
                const isEditing = editingId === it.id;

                return (
                  <div
                    key={it.id}
                    className="rounded-lg border px-4 py-3 bg-gray-50"
                  >
                    <div className="flex justify-between items-start gap-4">
                      <div className="min-w-0">
                        <div className="text-xs text-gray-500">
                          Stage: <span className="font-medium">{it.stage}</span>
                          {it.category ? (
                            <>
                              {" "}
                              • Category:{" "}
                              <span className="font-medium">{it.category}</span>
                            </>
                          ) : null}{" "}
                          • Type: <span className="font-medium">{it.type}</span>
                        </div>

                        {!isEditing ? (
                          <div className="mt-1 text-sm font-semibold text-gray-900">
                            {it.prompt}
                          </div>
                        ) : (
                          <div className="mt-2 space-y-3 text-sm">
                            <div className="grid gap-3 sm:grid-cols-2">
                              <div>
                                <label className="block text-xs font-medium mb-1">
                                  Stage
                                </label>
                                <input
                                  value={(editDraft.stage as string) ?? ""}
                                  onChange={(e) =>
                                    setEditDraft((d) => ({
                                      ...d,
                                      stage: e.target.value,
                                    }))
                                  }
                                  className="w-full rounded border px-2 py-1 text-sm"
                                />
                              </div>
                              <div>
                                <label className="block text-xs font-medium mb-1">
                                  Category
                                </label>
                                <input
                                  value={(editDraft.category as any) ?? ""}
                                  onChange={(e) =>
                                    setEditDraft((d) => ({
                                      ...d,
                                      category: e.target.value,
                                    }))
                                  }
                                  className="w-full rounded border px-2 py-1 text-sm"
                                />
                              </div>
                            </div>

                            <div>
                              <label className="block text-xs font-medium mb-1">
                                Prompt
                              </label>
                              <textarea
                                value={(editDraft.prompt as string) ?? ""}
                                onChange={(e) =>
                                  setEditDraft((d) => ({
                                    ...d,
                                    prompt: e.target.value,
                                  }))
                                }
                                className="w-full rounded border px-2 py-1 text-sm"
                                rows={3}
                              />
                            </div>

                            <div className="grid gap-3 sm:grid-cols-2">
                              <div>
                                <label className="block text-xs font-medium mb-1">
                                  Left label
                                </label>
                                <input
                                  value={
                                    (editDraft.scale_left_label as any) ?? ""
                                  }
                                  onChange={(e) =>
                                    setEditDraft((d) => ({
                                      ...d,
                                      scale_left_label: e.target.value,
                                    }))
                                  }
                                  className="w-full rounded border px-2 py-1 text-sm"
                                />
                              </div>
                              <div>
                                <label className="block text-xs font-medium mb-1">
                                  Right label
                                </label>
                                <input
                                  value={
                                    (editDraft.scale_right_label as any) ?? ""
                                  }
                                  onChange={(e) =>
                                    setEditDraft((d) => ({
                                      ...d,
                                      scale_right_label: e.target.value,
                                    }))
                                  }
                                  className="w-full rounded border px-2 py-1 text-sm"
                                />
                              </div>
                            </div>

                            <div className="flex items-center gap-4 text-sm">
                              <label className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={!!editDraft.required}
                                  onChange={(e) =>
                                    setEditDraft((d) => ({
                                      ...d,
                                      required: e.target.checked,
                                    }))
                                  }
                                />
                                Required
                              </label>

                              <label className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={!!editDraft.reverse_scored}
                                  onChange={(e) =>
                                    setEditDraft((d) => ({
                                      ...d,
                                      reverse_scored: e.target.checked,
                                    }))
                                  }
                                />
                                Reverse-scored (R)
                              </label>
                            </div>
                          </div>
                        )}

                        {!isEditing && it.type === "likert" && (
                          <div className="mt-2 text-xs text-gray-600">
                            Scale: {it.scale_min ?? 1}–{it.scale_max ?? 5}
                            {" • "}
                            {it.scale_left_label ?? "Strongly disagree"}
                            {" ↔ "}
                            {it.scale_right_label ?? "Strongly agree"}
                            {it.reverse_scored ? " • (R)" : ""}
                            {it.required ? " • required" : " • optional"}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-2 text-xs shrink-0">
                        {!isEditing ? (
                          <>
                            <button
                              type="button"
                              onClick={() => beginEdit(it)}
                              className="px-2 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100"
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => deleteItem(it.id)}
                              disabled={deletingId === it.id}
                              className="px-2 py-1 rounded border border-red-300 bg-white text-red-600 hover:bg-red-50 disabled:opacity-60"
                            >
                              {deletingId === it.id ? "Deleting…" : "Delete"}
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => saveEdit(it.id)}
                              disabled={savingEdit}
                              className="px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                            >
                              {savingEdit ? "Saving…" : "Save"}
                            </button>
                            <button
                              type="button"
                              onClick={cancelEdit}
                              className="px-3 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100"
                            >
                              Cancel
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
