import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import ProgressBar from "../components/ProgressBar";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getMe();
        const u = res.user

        if (!cancelled && !u.demographics_completed) {
          router.replace("/demographics");
          return;
        }

        if (!cancelled) setUser(u);
      } catch {
        if (!cancelled) router.replace("/login");
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading dashboard…</div>
      </div>
    );
  }

  if (!user) return null;

  async function onLogout() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="site-header">
        <div className="max-w-6xl 2xl:max-w-screen-2xl mx-auto flex items-center justify-between gap-4">
          <div className="min-w-0">
            <h1 className="page-title leading-tight">Dashboard</h1>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => router.push("/profile")}
              className="btn-primary"
            >
              Profile
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

      <div className="page-container">
        <div className="mb-4">
          <ProgressBar user={user} />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {user?.is_admin && (
            <a
              href="/chat"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Chat</h2>
              <p className="text-sm text-gray-600">
                Ask questions and interact with AI chatbot
              </p>
            </a>
          )}
          
          {user?.is_admin && (
            <a
              href="/playground"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Playground</h2>
              <p className="text-sm text-gray-600">Sandbox to see how the different quiz styles look</p>
            </a>
          )}

          {user?.is_admin && (
            <a
              href="/admin"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Admin Panel</h2>
              <p className="text-sm text-gray-600">Manage questions and content</p>
            </a>
          )}
          {/*Default quiz */}
          <a
            href="/quiz/base"
            className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
          >
            <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Quiz</h2>
            <p className="text-sm text-gray-600">Begin the Quiz</p>
          </a>
          {/*Additional Quizzes below*/}
          {user?.is_admin && (
          <a
            href="/quiz/double"
            className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
          >
            <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Dual Agent Quiz</h2>
            <p className="text-sm text-gray-600">Begin the Quiz</p>
          </a>
          )}
          {user?.is_admin && (
          <a
            href="/quiz/links"
            className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
          >
            <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Links Quiz</h2>
            <p className="text-sm text-gray-600">Begin the Quiz</p>
          </a>
          )}
          {user?.is_admin && (
          <a
            href="/quiz/followup"
            className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
          >
            <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Follow-up Questions Quiz</h2>
            <p className="text-sm text-gray-600">Begin the Quiz</p>
          </a>
          )}
        </div>
      </div>
    </div>
  );
}
