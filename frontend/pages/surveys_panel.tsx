import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { apiFetch } from "../lib/fetcher";

export default function SurveyPanelPage() {
  type SurveyStage = "pre_quiz" | "post_quiz" | string;
  type SurveyItemType = "likert" | "single_select";

  type SurveyOption = { id: string; label: string };

  type SurveyScale = {
    min: number;
    max: number;
    anchors?: string[] | null; // [left, right]
  };

  type SurveyItem = {
    id: string;
    stage: SurveyStage;
    prompt: string;
    type: SurveyItemType;
    required: boolean;
    order: number;
    active: boolean;

    category?: string | null;
    reverse_scored?: boolean;

    // Likert
    scale?: SurveyScale | null;

    // single_select
    options?: SurveyOption[] | null;

    created_at?: string;
    updated_at?: string;
  };

  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  // Create form
  const [stage, setStage] = useState<SurveyStage>("pre_quiz");
  const [type, setType] = useState<SurveyItemType>("likert");
  const [category, setCategory] = useState("");
  const [prompt, setPrompt] = useState("");
  const [required, setRequired] = useState(true);
  const [reverseScored, setReverseScored] = useState(false);

  // Likert inputs (UI state)
  const [scaleMin, setScaleMin] = useState(1);
  const [scaleMax, setScaleMax] = useState(5);
  const [scaleLeftLabel, setScaleLeftLabel] = useState("Strongly disagree");
  const [scaleRightLabel, setScaleRightLabel] = useState("Strongly agree");

  // single_select options (UI state)
  const [options, setOptions] = useState<SurveyOption[]>([
    { id: "a", label: "" },
    { id: "b", label: "" },
    { id: "c", label: "" },
    { id: "d", label: "" },
    { id: "e", label: "" },
  ]);

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
      { value: "pre_quiz", label: "Pre-Quiz" },
      { value: "post_quiz", label: "Post-Quiz" },
    ],
    [],
  );

  function sanitizeOptions(opts: SurveyOption[]) {
    return opts
      .map((o) => ({ id: o.id, label: (o.label ?? "").trim() }))
      .filter((o) => o.label.length > 0);
  }

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
        const data = await apiFetch<SurveyItem[]>("/api/surveys/items");
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

    if (type === "likert") {
      if (scaleMin >= scaleMax) {
        setMessage("Likert scale min must be less than max.");
        return;
      }
    } else {
      const cleaned = sanitizeOptions(options);
      if (cleaned.length < 2) {
        setMessage("Single-select requires at least 2 options.");
        return;
      }
    }

    setSaving(true);
    try {
      const payload: any = {
        stage,
        category: category.trim() || null,
        prompt: prompt.trim(),
        type,
        required,
        reverse_scored: reverseScored,
        order: 0,
        active: true,
      };

      if (type === "likert") {
        payload.scale = {
          min: scaleMin,
          max: scaleMax,
          anchors: [scaleLeftLabel || "Strongly disagree", scaleRightLabel || "Strongly agree"],
        };
      } else {
        payload.options = sanitizeOptions(options);
      }

      const created = await apiFetch<SurveyItem>("/api/surveys/items", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setItems((prev) => [created, ...prev]);

      // reset form
      setPrompt("");
      setCategory("");
      setReverseScored(false);
      setRequired(true);
      setType("likert");
      setScaleMin(1);
      setScaleMax(5);
      setScaleLeftLabel("Strongly disagree");
      setScaleRightLabel("Strongly agree");
      setOptions([
        { id: "a", label: "" },
        { id: "b", label: "" },
        { id: "c", label: "" },
        { id: "d", label: "" },
        { id: "e", label: "" },
      ]);

      setMessage("Survey item added.");
    } catch (e) {
      console.error(e);
      setMessage("Failed to add survey item.");
    } finally {
      setSaving(false);
    }
  }

  function beginEdit(it: SurveyItem) {
    setEditingId(it.id);

    // Make a safe editable copy
    setEditDraft({
      ...it,
      category: it.category ?? "",
      scale: it.scale ?? { min: 1, max: 5, anchors: ["Strongly disagree", "Strongly agree"] },
      options: it.options ?? [
        { id: "a", label: "" },
        { id: "b", label: "" },
        { id: "c", label: "" },
        { id: "d", label: "" },
        { id: "e", label: "" },
      ],
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditDraft({});
  }

  async function saveEdit(id: string) {
    setSavingEdit(true);
    try {
      const t = (editDraft.type ?? "likert") as SurveyItemType;

      const payload: any = {
        stage: editDraft.stage,
        category: (editDraft.category as any)?.trim?.()
          ? (editDraft.category as any).trim()
          : null,
        prompt: (editDraft.prompt ?? "").toString().trim(),
        type: t,
        required: !!editDraft.required,
        reverse_scored: !!editDraft.reverse_scored,
        active: editDraft.active ?? true,
        order: editDraft.order ?? 0,
      };

      if (t === "likert") {
        const sc = editDraft.scale ?? { min: 1, max: 5, anchors: ["Strongly disagree", "Strongly agree"] };
        const left = sc.anchors?.[0] ?? "Strongly disagree";
        const right = sc.anchors?.[1] ?? "Strongly agree";

        if ((sc.min ?? 1) >= (sc.max ?? 5)) {
          alert("Likert scale min must be less than max.");
          setSavingEdit(false);
          return;
        }

        payload.scale = {
          min: sc.min ?? 1,
          max: sc.max ?? 5,
          anchors: [left, right],
        };
        payload.options = null;
      } else {
        const cleaned = sanitizeOptions((editDraft.options ?? []) as SurveyOption[]);
        if (cleaned.length < 2) {
          alert("Single-select requires at least 2 options.");
          setSavingEdit(false);
          return;
        }
        payload.options = cleaned;
        payload.scale = null;
      }

      const updated = await apiFetch<SurveyItem>(`/api/surveys/items/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });

      setItems((prev) => prev.map((x) => (x.id === id ? updated : x)));
      cancelEdit();
    } catch (e) {
      console.error(e);
      alert("Failed to update survey item.");
    } finally {
      setSavingEdit(false);
    }
  }

  async function deleteItem(id: string) {
    if (!window.confirm("Delete this survey item?")) return;

    setDeletingId(id);
    try {
      await apiFetch<void>(`/api/surveys/items/${id}`, { method: "DELETE" });
      setItems((prev) => prev.filter((x) => x.id !== id));
    } catch (e) {
      console.error(e);
      alert("Failed to delete survey item.");
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
          <h2 className="text-xl font-semibold mb-4">Add Survey Item</h2>

          <form onSubmit={onCreate} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
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
                <label className="block text-sm font-medium mb-1">Type</label>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value as SurveyItemType)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                >
                  <option value="likert">Likert (1–5)</option>
                  <option value="single_select">Single select</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">
                  Category
                </label>
                <input
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  placeholder="e.g., TRUST, NFC, AI Literacy"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Prompt</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                rows={3}
                required
              />
            </div>

            {/* Likert config */}
            {type === "likert" && (
              <>
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
                  <div>
                    <label className="block text-sm font-medium mb-1">Min</label>
                    <input
                      type="number"
                      value={scaleMin}
                      onChange={(e) => setScaleMin(Number(e.target.value))}
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Max</label>
                    <input
                      type="number"
                      value={scaleMax}
                      onChange={(e) => setScaleMax(Number(e.target.value))}
                      className="w-full rounded-lg border px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              </>
            )}

            {/* Single select config */}
            {type === "single_select" && (
              <div className="rounded-lg border bg-gray-50 p-4">
                <div className="text-sm font-medium text-gray-900 mb-2">
                  Options (at least 2)
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {options.map((o, idx) => (
                    <div key={o.id}>
                      <label className="block text-xs font-medium mb-1">
                        Option {o.id.toUpperCase()}
                      </label>
                      <input
                        className="w-full rounded-lg border px-3 py-2 text-sm"
                        value={o.label}
                        onChange={(e) => {
                          const copy = [...options];
                          copy[idx] = { ...copy[idx], label: e.target.value };
                          setOptions(copy);
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  id="required"
                  type="checkbox"
                  checked={required}
                  onChange={(e) => setRequired(e.target.checked)}
                />
                Required
              </label>

              <label className="flex items-center gap-2 text-sm">
                <input
                  id="reverse"
                  type="checkbox"
                  checked={reverseScored}
                  onChange={(e) => setReverseScored(e.target.checked)}
                />
                Reverse-scored (R)
              </label>
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
              {saving ? "Saving…" : "Save survey item"}
            </button>
          </form>
        </div>
      </div>

      {/* List */}
      <div className="max-w-6xl mx-auto pt-0 px-6 pb-6">
        <div className="bg-white rounded-xl p-8 shadow-sm border">
          <h2 className="text-xl font-semibold mb-2">View Survey Items</h2>

          {loadingItems && (
            <p className="text-sm text-gray-500">Loading survey items…</p>
          )}
          {itemsError && (
            <p className="text-sm text-red-600 mb-2">{itemsError}</p>
          )}
          {!loadingItems && !itemsError && items.length === 0 && (
            <p className="text-sm text-gray-500">No survey items yet.</p>
          )}

          {!loadingItems && items.length > 0 && (
            <div className="mt-4 space-y-3">
              {items.map((it) => {
                const isEditing = editingId === it.id;

                const scaleMinV = it.scale?.min ?? 1;
                const scaleMaxV = it.scale?.max ?? 5;
                const left = it.scale?.anchors?.[0] ?? "Strongly disagree";
                const right = it.scale?.anchors?.[1] ?? "Strongly agree";

                return (
                  <div key={it.id} className="rounded-lg border px-4 py-3 bg-gray-50">
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
                          ) : null}
                          {" "}
                          • Type: <span className="font-medium">{it.type}</span>
                        </div>

                        {!isEditing ? (
                          <>
                            <div className="mt-1 text-sm font-semibold text-gray-900">
                              {it.prompt}
                            </div>

                            {it.type === "likert" && (
                              <div className="mt-2 text-xs text-gray-600">
                                Scale: {scaleMinV}–{scaleMaxV} • {left} ↔ {right}
                                {it.reverse_scored ? " • (R)" : ""}
                                {it.required ? " • required" : " • optional"}
                              </div>
                            )}

                            {it.type === "single_select" && (
                              <ul className="mt-2 text-xs text-gray-700 list-disc list-inside space-y-1">
                                {(it.options ?? []).map((o) => (
                                  <li key={o.id}>
                                    <span className="font-medium uppercase mr-1">{o.id}:</span>
                                    {o.label}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </>
                        ) : (
                          <div className="mt-2 space-y-3 text-sm">
                            <div className="grid gap-3 sm:grid-cols-3">
                              <div>
                                <label className="block text-xs font-medium mb-1">Stage</label>
                                <input
                                  value={(editDraft.stage as string) ?? ""}
                                  onChange={(e) =>
                                    setEditDraft((d) => ({ ...d, stage: e.target.value }))
                                  }
                                  className="w-full rounded border px-2 py-1 text-sm"
                                />
                              </div>

                              <div>
                                <label className="block text-xs font-medium mb-1">Type</label>
                                <select
                                  value={(editDraft.type as SurveyItemType) ?? "likert"}
                                  onChange={(e) =>
                                    setEditDraft((d) => ({
                                      ...d,
                                      type: e.target.value as SurveyItemType,
                                    }))
                                  }
                                  className="w-full rounded border px-2 py-1 text-sm"
                                >
                                  <option value="likert">likert</option>
                                  <option value="single_select">single_select</option>
                                </select>
                              </div>

                              <div>
                                <label className="block text-xs font-medium mb-1">Category</label>
                                <input
                                  value={(editDraft.category as any) ?? ""}
                                  onChange={(e) =>
                                    setEditDraft((d) => ({ ...d, category: e.target.value }))
                                  }
                                  className="w-full rounded border px-2 py-1 text-sm"
                                />
                              </div>
                            </div>

                            <div>
                              <label className="block text-xs font-medium mb-1">Prompt</label>
                              <textarea
                                value={(editDraft.prompt as string) ?? ""}
                                onChange={(e) =>
                                  setEditDraft((d) => ({ ...d, prompt: e.target.value }))
                                }
                                className="w-full rounded border px-2 py-1 text-sm"
                                rows={3}
                              />
                            </div>

                            {(editDraft.type ?? "likert") === "likert" && (
                              <>
                                <div className="grid gap-3 sm:grid-cols-2">
                                  <div>
                                    <label className="block text-xs font-medium mb-1">Min</label>
                                    <input
                                      type="number"
                                      value={editDraft.scale?.min ?? 1}
                                      onChange={(e) =>
                                        setEditDraft((d) => ({
                                          ...d,
                                          scale: {
                                            ...(d.scale ?? { min: 1, max: 5, anchors: ["Strongly disagree", "Strongly agree"] }),
                                            min: Number(e.target.value),
                                          },
                                        }))
                                      }
                                      className="w-full rounded border px-2 py-1 text-sm"
                                    />
                                  </div>
                                  <div>
                                    <label className="block text-xs font-medium mb-1">Max</label>
                                    <input
                                      type="number"
                                      value={editDraft.scale?.max ?? 5}
                                      onChange={(e) =>
                                        setEditDraft((d) => ({
                                          ...d,
                                          scale: {
                                            ...(d.scale ?? { min: 1, max: 5, anchors: ["Strongly disagree", "Strongly agree"] }),
                                            max: Number(e.target.value),
                                          },
                                        }))
                                      }
                                      className="w-full rounded border px-2 py-1 text-sm"
                                    />
                                  </div>
                                </div>

                                <div className="grid gap-3 sm:grid-cols-2">
                                  <div>
                                    <label className="block text-xs font-medium mb-1">
                                      Left label
                                    </label>
                                    <input
                                      value={editDraft.scale?.anchors?.[0] ?? ""}
                                      onChange={(e) =>
                                        setEditDraft((d) => {
                                          const anchors = (d.scale?.anchors ?? ["", ""]).slice(0, 2);
                                          anchors[0] = e.target.value;
                                          return {
                                            ...d,
                                            scale: {
                                              ...(d.scale ?? { min: 1, max: 5 }),
                                              anchors,
                                            },
                                          };
                                        })
                                      }
                                      className="w-full rounded border px-2 py-1 text-sm"
                                    />
                                  </div>
                                  <div>
                                    <label className="block text-xs font-medium mb-1">
                                      Right label
                                    </label>
                                    <input
                                      value={editDraft.scale?.anchors?.[1] ?? ""}
                                      onChange={(e) =>
                                        setEditDraft((d) => {
                                          const anchors = (d.scale?.anchors ?? ["", ""]).slice(0, 2);
                                          anchors[1] = e.target.value;
                                          return {
                                            ...d,
                                            scale: {
                                              ...(d.scale ?? { min: 1, max: 5 }),
                                              anchors,
                                            },
                                          };
                                        })
                                      }
                                      className="w-full rounded border px-2 py-1 text-sm"
                                    />
                                  </div>
                                </div>
                              </>
                            )}

                            {(editDraft.type ?? "likert") === "single_select" && (
                              <div className="rounded-lg border bg-white p-3">
                                <div className="text-xs font-medium mb-2">Options (at least 2)</div>
                                <div className="grid gap-2 sm:grid-cols-2">
                                  {(editDraft.options ?? []).map((o, idx) => (
                                    <div key={o.id}>
                                      <label className="block text-xs font-medium mb-1">
                                        Option {o.id.toUpperCase()}
                                      </label>
                                      <input
                                        className="w-full rounded border px-2 py-1 text-sm"
                                        value={o.label}
                                        onChange={(e) => {
                                          const copy = [...((editDraft.options ?? []) as SurveyOption[])];
                                          copy[idx] = { ...copy[idx], label: e.target.value };
                                          setEditDraft((d) => ({ ...d, options: copy }));
                                        }}
                                      />
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            <div className="flex items-center gap-4 text-sm">
                              <label className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={!!editDraft.required}
                                  onChange={(e) =>
                                    setEditDraft((d) => ({ ...d, required: e.target.checked }))
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

                              <label className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  checked={editDraft.active ?? true}
                                  onChange={(e) =>
                                    setEditDraft((d) => ({ ...d, active: e.target.checked }))
                                  }
                                />
                                Active
                              </label>
                            </div>
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
