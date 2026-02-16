import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";

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
  }, [router]);

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
      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
            <p className="text-sm text-gray-600">Welcome to the dashboard, {user.email}</p>
          </div>
          <div className="flex items-center gap-4">
            <button 
              onClick={() => router.push("/profile")}
              className="text-sm px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
            >
              Profile
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

      <div className="max-w-6xl mx-auto p-6">
        <div className="grid gap-4 sm:grid-cols-2">
          {user?.is_admin && (
            <a
              href="/chat"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg font-semibold">Chat</h2>
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
              <h2 className="mb-1 text-lg font-semibold">Playground</h2>
              <p className="text-sm text-gray-600">Sandbox to see how the different quiz styles look</p>
            </a>
          )}

          {user?.is_admin && (
            <a
              href="/admin"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg font-semibold">Admin Panel</h2>
              <p className="text-sm text-gray-600">Manage questions and content</p>
            </a>
          )}
          {/*Default quiz */}
          <a
            href="/quiz/1"
            className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
          >
            <h2 className="mb-1 text-lg font-semibold">Quiz</h2>
            <p className="text-sm text-gray-600">Begin the Quiz</p>
          </a>
          {/*Additional Quiz*/}
          <a
            href="/quiz/2"
            className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
          >
            <h2 className="mb-1 text-lg font-semibold">Test New Quiz</h2>
            <p className="text-sm text-gray-600">Begin the Quiz</p>
          </a>
        </div>
      </div>
    </div>
  );
}
