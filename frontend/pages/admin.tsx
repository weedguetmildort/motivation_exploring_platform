import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { apiFetch } from "../lib/fetcher";
import Link from "next/link";

export default function AdminPage() {
  type ChoiceInput = { id: string; label: string };

  type Question = {
    id: string;
    stem: string;
    subtitle?: string | null;
    choices: { id: string; label: string }[];
  };

  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  const [stem, setStem] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [choices, setChoices] = useState<ChoiceInput[]>([
    { id: "a", label: "" },
    { id: "b", label: "" },
    { id: "c", label: "" },
    { id: "d", label: "" },
  ]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [questions, setQuestions] = useState<Question[]>([]);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [questionsError, setQuestionsError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editStem, setEditStem] = useState("");
  const [editSubtitle, setEditSubtitle] = useState("");
  const [editChoices, setEditChoices] = useState<{ id: string; label: string }[]>([]);
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  function beginEdit(q: Question) {
    setEditingId(q.id);
    setEditStem(q.stem);
    setEditSubtitle(q.subtitle ?? "");
    setEditChoices(q.choices.map((c) => ({ ...c })));
  }

  function cancelEdit() {
    setEditingId(null);
    setEditStem("");
    setEditSubtitle("");
    setEditChoices([]);
  }

  async function saveEdit(questionId: string) {
    setSavingEdit(true);
    try {
      const updated = await apiFetch<Question>(`/api/questions/${questionId}`, {
        method: "PUT",
        body: JSON.stringify({
          stem: editStem,
          subtitle: editSubtitle || null,
          choices: editChoices,
        }),
      });

      setQuestions((prev) =>
        prev.map((q) => (q.id === questionId ? updated : q))
      );
      cancelEdit();
    } catch (e) {
      console.error("Failed to update question", e);
      alert("Failed to update question.");
    } finally {
      setSavingEdit(false);
    }
  }

  async function deleteQuestion(questionId: string) {
    if (!window.confirm("Are you sure you want to delete this question?")) {
      return;
    }

    setDeletingId(questionId);
    try {
      await apiFetch<void>(`/api/questions/${questionId}`, {
        method: "DELETE",
      });
      setQuestions((prev) => prev.filter((q) => q.id !== questionId));
    } catch (e) {
      console.error("Failed to delete question", e);
      alert("Failed to delete question.");
    } finally {
      setDeletingId(null);
    }
  }



  useEffect(() => {

    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (!cancel) {
          if (!res.user.is_admin) {
            // Non-admin → block access and redirect
            window.location.href = "/dashboard";   // [ADMIN BLOCK]
            return;
          }
          setUser(res.user);
        }
      } catch {
        // Not logged in → send to login
        if (!cancel) window.location.href = "/login";
      } finally {
        if (!cancel) setChecking(false);
      }
    })();

    return () => {
      cancel = true;
    };
  }, []);

  useEffect(() => {
    if (!user) return;

    let cancel = false;

    async function loadQuestions() {
      setLoadingQuestions(true);
      setQuestionsError(null);

      try {
        const data = await apiFetch<Question[]>("/api/questions/");
        if (!cancel) {
          setQuestions(data);
        }
      } catch (e) {
        console.error("Failed to load questions:", e);
        if (!cancel) setQuestionsError("Failed to load questions.");
      } finally {
        if (!cancel) setLoadingQuestions(false);
      }
    }

    loadQuestions();

    return () => {
      cancel = true;
    };
  }, [user]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading admin panel…</div>
      </div>
    );
  }

  if (!user) return null;

  async function onLogout() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const res = await apiFetch("/api/questions/", {
        method: "POST",
        body: JSON.stringify({ stem, subtitle, choices }),
      });
      setMessage("Question saved!");
      // optionally clear form or keep it
    } catch (err: any) {
      setMessage("Failed to save question.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Admin Panel</h1>
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
              className="bg-gray-100 hover:bg-gray-200 px-3 py-1 rounded-lg text-sm"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="max-w-6xl mx-auto p-6">
        <div className="bg-white rounded-xl p-8 shadow-sm border text-center">
          <h2 className="text-xl font-semibold mb-2">Add Question</h2>
          
          <form onSubmit={onSubmit} className="space-y-4 text-left">
            <div>
              <label className="block text-sm font-medium mb-1">Question stem</label>
              <textarea
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={stem}
                onChange={(e) => setStem(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Subtitle (optional)</label>
              <textarea
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={subtitle}
                onChange={(e) => setSubtitle(e.target.value)}
              />
            </div>

            <div className="grid gap-2">
              {choices.map((c, idx) => (
                <div key={c.id}>
                  <label className="block text-xs font-medium mb-1">
                    Choice {c.id.toUpperCase()}
                  </label>
                  <input
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    value={c.label}
                    onChange={(e) => {
                      const copy = [...choices];
                      copy[idx] = { ...copy[idx], label: e.target.value };
                      setChoices(copy);
                    }}
                    required
                  />
                </div>
              ))}
            </div>

            <button
              type="submit"
              disabled={saving}
              className="mt-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save question"}
            </button>

            {message && (
              <p className="text-sm mt-2 text-gray-700">
                {message}
              </p>
            )}
          </form>

        </div>

      </div>
      <div className="max-w-6xl mx-auto pt-0 px-6 pb-6">
        <div className="bg-white rounded-xl p-8 shadow-sm border text-center">
          <h2 className="text-xl font-semibold mb-2">View Questions</h2>

          {loadingQuestions && (
            <p className="text-sm text-gray-500 text-center">Loading questions…</p>
          )}

          {questionsError && (
            <p className="text-sm text-red-600 text-center mb-2">
              {questionsError}
            </p>
          )}

          {!loadingQuestions && !questionsError && questions.length === 0 && (
            <p className="text-sm text-gray-500 text-center">
              No questions have been created yet.
            </p>
          )}

          {!loadingQuestions && questions.length > 0 && (
            <div className="mt-4 space-y-3">
              {questions.map((q) => {
                const isEditing = editingId === q.id;

                return (
                  <div
                    key={q.id}
                    className="rounded-lg border px-4 py-3 bg-gray-50 text-left"
                  >
                    {/* Top row: title + actions */}
                    <div className="flex justify-between items-start gap-4">
                      <div>
                        <div className="text-sm font-semibold text-gray-900">
                          {isEditing ? "Editing question" : q.stem}
                        </div>
                        {!isEditing && q.subtitle && (
                          <div className="mt-1 text-xs text-gray-600">{q.subtitle}</div>
                        )}
                      </div>

                      <div className="flex items-center gap-2 text-xs">
                        {!isEditing && (
                          <>
                            <button
                              type="button"
                              onClick={() => beginEdit(q)}
                              className="px-2 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100"
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => deleteQuestion(q.id)}
                              disabled={deletingId === q.id}
                              className="px-2 py-1 rounded border border-red-300 bg-white text-red-600 hover:bg-red-50 disabled:opacity-60"
                            >
                              {deletingId === q.id ? "Deleting…" : "Delete"}
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Normal view (not editing) */}
                    {!isEditing && (
                      <ul className="mt-2 text-xs text-gray-700 list-disc list-inside space-y-1">
                        {q.choices.map((c) => (
                          <li key={c.id}>
                            <span className="font-medium uppercase mr-1">{c.id}:</span>
                            {c.label}
                          </li>
                        ))}
                      </ul>
                    )}

                    {/* Edit form */}
                    {isEditing && (
                      <div className="mt-3 space-y-3 text-xs">
                        <div>
                          <label className="block font-medium mb-1">Question stem</label>
                          <textarea
                            className="w-full rounded border px-2 py-1"
                            rows={2}
                            value={editStem}
                            onChange={(e) => setEditStem(e.target.value)}
                          />
                        </div>

                        <div>
                          <label className="block font-medium mb-1">
                            Subtitle (optional)
                          </label>
                          <textarea
                            className="w-full rounded border px-2 py-1"
                            rows={2}
                            value={editSubtitle}
                            onChange={(e) => setEditSubtitle(e.target.value)}
                          />
                        </div>

                        <div className="grid gap-2">
                          {editChoices.map((c, idx) => (
                            <div key={c.id}>
                              <label className="block font-medium mb-1">
                                Choice {c.id.toUpperCase()}
                              </label>
                              <input
                                className="w-full rounded border px-2 py-1"
                                value={c.label}
                                onChange={(e) => {
                                  const copy = [...editChoices];
                                  copy[idx] = { ...copy[idx], label: e.target.value };
                                  setEditChoices(copy);
                                }}
                              />
                            </div>
                          ))}
                        </div>

                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => saveEdit(q.id)}
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
                        </div>
                      </div>
                    )}
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
