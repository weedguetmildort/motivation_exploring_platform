import SurveyItemFields from "../components/SurveyItemFields";
import { surveyDraft, surveyItemPayload } from "../lib/surveyEditor";
import type { SurveyItem } from "../lib/surveys";
import EffectiveSurveyPreview from "../components/EffectiveSurveyPreview";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { apiFetch } from "../lib/fetcher";
import { getStudyConfig, type SurveyStages } from "../lib/study";
import { DEFAULT_SURVEY_STAGES, questionTarget, targetFields } from "../lib/surveyConfig";
import { selectedStudy } from "../lib/studySelection";

export default function SurveyPanelPage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  // Create form
  const [settings, setSettings] = useState<SurveyStages>(DEFAULT_SURVEY_STAGES);
  const [previewStage, setPreviewStage] = useState("pre_quiz");
  const [draft, setDraft] = useState(() => surveyDraft());
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // List + edit
  const [items, setItems] = useState<SurveyItem[]>([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [itemsError, setItemsError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState(() => surveyDraft());
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const stages = useMemo(() => [
    { value: "all_surveys", label: "All surveys in this study" },
    { value: "post_quiz", label: "All post-quiz surveys" },
    ...Object.entries(settings).map(([value, item]) => ({ value, label: item.name })),
  ], [settings]);
  useEffect(() => {
    const requested = [router.query?.stage].flat()[0];
    if (requested && Object.keys(settings).includes(requested)) { setDraft(current => ({ ...current, ...targetFields(requested) })); setPreviewStage(requested); }
  }, [router.query?.stage, settings]);
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    getStudyConfig().then(config => { if (!cancelled && config?.survey_stages) setSettings(config.survey_stages); }).catch(() => {});
    return () => { cancelled = true; };
  }, [user]);

  // --- auth gate (admin only) ---
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
        setUser(res.user);
      } catch {
        if (!cancel) router.replace("/login");
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
    e.preventDefault(); setMessage(null);
    let payload;
    try { payload = surveyItemPayload(draft); }
    catch (error) { setMessage((error as Error).message); return; }
    setSaving(true);
    try {
      const created = await apiFetch<SurveyItem>("/api/surveys/items", { method: "POST", body: JSON.stringify(payload) });
      setItems(previous => [created, ...previous]);
      setDraft({ ...surveyDraft(), ...targetFields(questionTarget(draft), draft.stages) });
      setMessage("Survey item added.");
    } catch { setMessage("Failed to add survey item."); }
    finally { setSaving(false); }
  }

  function beginEdit(item: SurveyItem) { setEditingId(item.id); setEditDraft(surveyDraft(item)); }
  function cancelEdit() { setEditingId(null); setEditDraft(surveyDraft()); }
  async function saveEdit(id: string) {
    let payload;
    try { payload = surveyItemPayload(editDraft); }
    catch (error) { alert((error as Error).message); return; }
    setSavingEdit(true);
    try {
      const updated = await apiFetch<SurveyItem>(`/api/surveys/items/${id}`, { method: "PUT", body: JSON.stringify(payload) });
      setItems(previous => previous.map(item => item.id === id ? updated : item)); cancelEdit();
    } catch { alert("Failed to update survey item."); }
    finally { setSavingEdit(false); }
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
      <header className="site-header">
        <div className="site-header-inner">
          <div>
            <h1 className="page-title">
              Survey Questions Panel
            </h1>
            <p className="page-subtitle">
              {selectedStudy() === "study-1" ? "Study 1 · Base + one assigned variant" : "Study 2 · Base + all variants"}. Shared questions and stage-specific additions stay within this study.
            </p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="btn-primary"
            >
              Back to Dashboard
            </button>
            <button
              onClick={onLogout}
              className="btn-secondary"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Create */}
      <div className="page-container">
        <EffectiveSurveyPreview settings={settings} stage={previewStage} onStageChange={setPreviewStage} revision={items} />
        <div className="bg-white rounded-xl p-8 shadow-sm border">
          <h2 className="text-xl 2xl:text-2xl font-semibold mb-4">Add Survey Item</h2>

          <form onSubmit={onCreate} className="space-y-4">
            <SurveyItemFields value={draft} onChange={setDraft} settings={settings} />

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
      <div className="max-w-6xl 2xl:max-w-screen-2xl mx-auto pt-0 px-6 pb-6">
        <div className="bg-white rounded-xl p-8 shadow-sm border">
          <h2 className="text-xl 2xl:text-2xl font-semibold mb-2">View Survey Items</h2>

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
                          Stage: <span className="font-medium">{stages.find(target => target.value === questionTarget(it))?.label ?? it.stage}{it.scope === "stages" && (it.stages?.length ?? 0) > 1 ? ` (+${it.stages!.length - 1} more)` : ""}</span>
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
                          <SurveyItemFields value={editDraft} onChange={setEditDraft} settings={settings} editing />
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
