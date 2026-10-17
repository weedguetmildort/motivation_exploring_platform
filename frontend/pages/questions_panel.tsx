import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { apiFetch } from "../lib/fetcher";

export default function QuestionPanelPage() {
  type ChoiceInput = { id: string; label: string };

  type SetId = "a" | "b" | "c" | "d";
  type Difficulty = "easy" | "medium" | "hard";

  type Question = {
    id: string;
    stem: string;
    subtitle?: string | null;
    choices: { id: string; label: string }[];
    correct_choice_id: string;
    set?: SetId | null;
    difficulty?: Difficulty | null;
    difficulty_source?: "ai" | "manual" | null;
    difficulty_checked?: boolean;
  };

  const SETS: SetId[] = ["a", "b", "c", "d"];
  const DIFFICULTIES: Difficulty[] = ["easy", "medium", "hard"];

  const DIFFICULTY_BADGE: Record<Difficulty, string> = {
    easy: "bg-green-100 text-green-800",
    medium: "bg-yellow-100 text-yellow-800",
    hard: "bg-red-100 text-red-800",
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
  const [editChoices, setEditChoices] = useState<
    { id: string; label: string }[]
  >([]);
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [correctChoiceId, setCorrectChoiceId] = useState("");
  const [editCorrectChoiceId, setEditCorrectChoiceId] = useState("");

  const [judging, setJudging] = useState(false);
  const [judgeMessage, setJudgeMessage] = useState<string | null>(null);

  function beginEdit(q: Question) {
    setEditingId(q.id);
    setEditStem(q.stem);
    setEditSubtitle(q.subtitle ?? "");
    setEditChoices(q.choices.map((c) => ({ ...c })));
    setEditCorrectChoiceId(q.correct_choice_id);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditStem("");
    setEditSubtitle("");
    setEditChoices([]);
    setEditCorrectChoiceId("");
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
          correct_choice_id: editCorrectChoiceId,
        }),
      });

      setQuestions((prev) =>
        prev.map((q) => (q.id === questionId ? updated : q)),
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

  async function assignSet(questionId: string, value: SetId | null) {
    try {
      const updated = await apiFetch<Question>(`/api/questions/${questionId}/set`, {
        method: "PATCH",
        body: JSON.stringify({ set: value }),
      });
      setQuestions((prev) => prev.map((q) => (q.id === questionId ? updated : q)));
    } catch (e) {
      console.error("Failed to assign set", e);
      alert("Failed to assign set.");
    }
  }

  async function overrideDifficulty(questionId: string, value: Difficulty | null) {
    try {
      const updated = await apiFetch<Question>(`/api/questions/${questionId}/difficulty`, {
        method: "PATCH",
        body: JSON.stringify({ difficulty: value }),
      });
      setQuestions((prev) => prev.map((q) => (q.id === questionId ? updated : q)));
    } catch (e) {
      console.error("Failed to set difficulty", e);
      alert("Failed to set difficulty.");
    }
  }

  async function judgeDifficultyNow() {
    setJudging(true);
    setJudgeMessage(null);
    try {
      const result = await apiFetch<{ judged: number; skipped: number }>(
        "/api/questions/judge-difficulty",
        { method: "POST" },
      );
      const data = await apiFetch<Question[]>("/api/questions/");
      setQuestions(data);
      setJudgeMessage(
        `Judged ${result.judged} question${result.judged === 1 ? "" : "s"}` +
          (result.skipped ? `, ${result.skipped} left unjudged.` : "."),
      );
    } catch (e) {
      console.error("Failed to judge difficulty", e);
      setJudgeMessage("Failed to run difficulty judging.");
    } finally {
      setJudging(false);
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
            router.replace("/dashboard");
            return;
          }
          setUser(res.user);
        }
      } catch {
        // Not logged in → send to login
        if (!cancel) router.replace("/login");
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
        <div className="text-gray-500">Loading quiz questions panel…</div>
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

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const created = await apiFetch<Question>("/api/questions/", {
        // [UPDATE]
        method: "POST",
        body: JSON.stringify({ stem, subtitle, choices, correct_choice_id: correctChoiceId }),
      });

      setQuestions((prev) => [created, ...prev]);
      setMessage("Question saved!");
      setStem("");
      setSubtitle("");
      setChoices([
        { id: "a", label: "" },
        { id: "b", label: "" },
        { id: "c", label: "" },
        { id: "d", label: "" },
      ]);
      setCorrectChoiceId("");
    } catch (err: any) {
      setMessage("Failed to save question.");
    } finally {
      setSaving(false);
    }
  }

  // ── Summary counts (client-side over the loaded list) ──────────────────────
  const topicCounts = (() => {
    const map = new Map<string, number>();
    for (const q of questions) {
      const key = (q.stem || "").trim() || "(untitled)";
      map.set(key, (map.get(key) ?? 0) + 1);
    }
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]);
  })();

  const difficultyCounts = {
    easy: questions.filter((q) => q.difficulty === "easy").length,
    medium: questions.filter((q) => q.difficulty === "medium").length,
    hard: questions.filter((q) => q.difficulty === "hard").length,
    unjudged: questions.filter((q) => !q.difficulty).length,
  };

  const setCounts = {
    a: questions.filter((q) => q.set === "a").length,
    b: questions.filter((q) => q.set === "b").length,
    c: questions.filter((q) => q.set === "c").length,
    d: questions.filter((q) => q.set === "d").length,
    unassigned: questions.filter((q) => !q.set).length,
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="site-header">
        <div className="site-header-inner">
          <div>
            <h1 className="page-title">
              Quiz Questions Panel
            </h1>
            <p className="page-subtitle">
              Manage quiz questions and answers
            </p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={judgeDifficultyNow}
              disabled={judging}
              className="btn-secondary disabled:opacity-60"
            >
              {judging ? "Judging…" : "Judge difficulty now"}
            </button>
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

      {/* Main Content */}
      <div className="page-container">
        <div className="bg-white rounded-xl p-8 shadow-sm border text-center">
          <h2 className="text-xl 2xl:text-2xl font-semibold mb-2">Add Question</h2>

          <form onSubmit={onSubmit} className="space-y-4 text-left">
            <div>
              <label className="block text-sm font-medium mb-1">
                Topic
              </label>
              <textarea
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={stem}
                onChange={(e) => setStem(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Question
              </label>
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

            <div>
              <label className="block text-sm font-medium mb-1">
                Correct answer
              </label>
              <div className="flex gap-4">
                {choices.map((c) => (
                  <label key={c.id} className="flex items-center gap-1 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name="correct_choice"
                      value={c.id}
                      checked={correctChoiceId === c.id}
                      onChange={() => setCorrectChoiceId(c.id)}
                      required
                    />
                    {c.id.toUpperCase()}
                  </label>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={saving || !correctChoiceId}
              className="mt-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save question"}
            </button>

            {message && <p className="text-sm mt-2 text-gray-700">{message}</p>}
          </form>
        </div>
      </div>
      <div className="max-w-6xl 2xl:max-w-screen-2xl mx-auto pt-0 px-6 pb-6">
        <div className="bg-white rounded-xl p-8 shadow-sm border text-center">
          <h2 className="text-xl 2xl:text-2xl font-semibold mb-2">View Questions</h2>

          {/* Summary counts */}
          {questions.length > 0 && (
            <div className="mb-4 space-y-2 text-left">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold text-gray-500 uppercase tracking-wide mr-1">Topic</span>
                {topicCounts.map(([topic, count]) => (
                  <span key={topic} className="rounded-full bg-gray-100 px-2 py-0.5 font-medium text-gray-700">
                    {topic} {count}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold text-gray-500 uppercase tracking-wide mr-1">Difficulty</span>
                <span className="rounded-full bg-green-100 px-2 py-0.5 font-medium text-green-800">Easy {difficultyCounts.easy}</span>
                <span className="rounded-full bg-yellow-100 px-2 py-0.5 font-medium text-yellow-800">Medium {difficultyCounts.medium}</span>
                <span className="rounded-full bg-red-100 px-2 py-0.5 font-medium text-red-800">Hard {difficultyCounts.hard}</span>
                <span className="rounded-full bg-gray-100 px-2 py-0.5 font-medium text-gray-600">Unjudged {difficultyCounts.unjudged}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold text-gray-500 uppercase tracking-wide mr-1">Set</span>
                {SETS.map((s) => (
                  <span key={s} className="rounded-full bg-blue-100 px-2 py-0.5 font-medium text-blue-800">
                    {s.toUpperCase()} {setCounts[s]}
                  </span>
                ))}
                <span className="rounded-full bg-gray-100 px-2 py-0.5 font-medium text-gray-600">Unassigned {setCounts.unassigned}</span>
              </div>
            </div>
          )}

          {judgeMessage && (
            <p className="mb-3 text-sm text-gray-700 text-left" role="status">{judgeMessage}</p>
          )}

          {loadingQuestions && (
            <p className="text-sm text-gray-500 text-center">
              Loading questions…
            </p>
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
                          <div className="mt-1 text-xs text-gray-600">
                            {q.subtitle}
                          </div>
                        )}
                        {!isEditing && (
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            {q.difficulty ? (
                              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${DIFFICULTY_BADGE[q.difficulty]}`}>
                                {q.difficulty[0].toUpperCase() + q.difficulty.slice(1)}
                                {q.difficulty_source === "manual"
                                  ? " · manual"
                                  : q.difficulty_source === "ai"
                                  ? " · AI"
                                  : ""}
                              </span>
                            ) : (
                              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                                Unjudged
                              </span>
                            )}
                            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">
                              Set {q.set ? q.set.toUpperCase() : "—"}
                            </span>
                          </div>
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
                            <span className="font-medium uppercase mr-1">
                              {c.id.toUpperCase()}:
                            </span>
                            {c.label}
                            {c.id === q.correct_choice_id && (
                              <span className="ml-2 text-green-600 font-semibold">(correct)</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}

                    {/* Inline set + difficulty controls */}
                    {!isEditing && (
                      <div className="mt-3 flex flex-wrap items-center gap-4 text-xs">
                        <label className="flex items-center gap-1">
                          <span className="text-gray-500">Set</span>
                          <select
                            aria-label={`Set for ${q.stem}`}
                            value={q.set ?? ""}
                            onChange={(e) =>
                              assignSet(q.id, (e.target.value || null) as SetId | null)
                            }
                            className="rounded border px-2 py-1"
                          >
                            <option value="">Unassigned</option>
                            {SETS.map((s) => (
                              <option key={s} value={s}>{s.toUpperCase()}</option>
                            ))}
                          </select>
                        </label>
                        <label className="flex items-center gap-1">
                          <span className="text-gray-500">Difficulty</span>
                          <select
                            aria-label={`Difficulty for ${q.stem}`}
                            value={q.difficulty ?? ""}
                            onChange={(e) =>
                              overrideDifficulty(q.id, (e.target.value || null) as Difficulty | null)
                            }
                            className="rounded border px-2 py-1"
                          >
                            <option value="">Unjudged</option>
                            {DIFFICULTIES.map((d) => (
                              <option key={d} value={d}>{d[0].toUpperCase() + d.slice(1)}</option>
                            ))}
                          </select>
                        </label>
                      </div>
                    )}

                    {/* Edit form */}
                    {isEditing && (
                      <div className="mt-3 space-y-3 text-xs">
                        <div>
                          <label className="block font-medium mb-1">
                            Topic
                          </label>
                          <textarea
                            className="w-full rounded border px-2 py-1"
                            rows={2}
                            value={editStem}
                            onChange={(e) => setEditStem(e.target.value)}
                          />
                        </div>

                        <div>
                          <label className="block font-medium mb-1">
                            Question
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
                                  copy[idx] = {
                                    ...copy[idx],
                                    label: e.target.value,
                                  };
                                  setEditChoices(copy);
                                }}
                              />
                            </div>
                          ))}
                        </div>

                        <div>
                          <label className="block font-medium mb-1">
                            Correct answer
                          </label>
                          <div className="flex gap-4">
                            {editChoices.map((c) => (
                              <label key={c.id} className="flex items-center gap-1 cursor-pointer">
                                <input
                                  type="radio"
                                  name="edit_correct_choice"
                                  value={c.id}
                                  checked={editCorrectChoiceId === c.id}
                                  onChange={() => setEditCorrectChoiceId(c.id)}
                                />
                                {c.id.toUpperCase()}
                              </label>
                            ))}
                          </div>
                        </div>

                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => saveEdit(q.id)}
                            disabled={savingEdit || !editCorrectChoiceId}
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
