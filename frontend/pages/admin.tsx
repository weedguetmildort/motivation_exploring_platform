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
              {questions.map((q) => (
                <div
                  key={q.id}
                  className="rounded-lg border px-4 py-3 text-left bg-gray-50"
                >
                  <div className="flex justify-between items-start gap-4">
                    <div>
                      <div className="text-sm font-semibold text-gray-900">
                        {q.stem}
                      </div>
                      {q.subtitle && (
                        <div className="mt-1 text-xs text-gray-600">
                          {q.subtitle}
                        </div>
                      )}
                    </div>
                    <div className="text-xs text-gray-500 whitespace-nowrap">
                      {q.choices.length} choices
                    </div>
                  </div>
                  <ul className="mt-2 text-xs text-gray-700 list-disc list-inside space-y-1">
                    {q.choices.map((c) => (
                      <li key={c.id}>
                        <span className="font-medium uppercase mr-1">
                          {c.id}:
                        </span>
                        {c.label}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
              </div>
          )}

        </div>
      </div>
    </div>
  );
}
