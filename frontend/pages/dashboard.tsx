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
        const { user } = await getMe();
        if (!cancelled) setUser(user);
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
    <div className="min-h-screen p-6">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-sm text-gray-600">Welcome, {user.email}</p>
        </div>
        <div className="flex items-center gap-3">
          
          <button
            onClick={onLogout}
            className="rounded-xl border px-4 py-2 text-sm hover:bg-gray-50"
          >
            Log out
          </button>
        </div>
      </header>


      <div className="grid gap-4 sm:grid-cols-2">
        {user?.is_admin && (
          <a
            href="/chat"
            className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
          >
            <h2 className="mb-1 text-lg font-semibold">Open Chat</h2>
            <p className="text-sm text-gray-600">
              Ask questions and explore motivation signals.
            </p>
          </a>
        )}
        
        {user?.is_admin && (
          <a
            href="/playground"
            className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
          >
            <h2 className="mb-1 text-lg font-semibold">Playground</h2>
            <p className="text-sm text-gray-600">Cases access</p>
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


        <div className="rounded-2xl border p-5 opacity-70">
          <h2 className="mb-1 text-lg font-semibold">Quiz</h2>
          <p className="text-sm text-gray-600">Begin the Quiz</p>
        </div>
      </div>
    </div>
  );
}
