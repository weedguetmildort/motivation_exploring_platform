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
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-600">{user.email}</span>
          <button
            onClick={onLogout}
            className="rounded-xl border px-3 py-1 text-sm hover:bg-gray-50"
          >
            Log out
          </button>
        </div>
      </header>


      <div className="grid gap-4 sm:grid-cols-2">
        <a
          href="/chat"
          className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
        >
          <h2 className="mb-1 text-lg font-semibold">Open Chat</h2>
          <p className="text-sm text-gray-600">
            Ask questions and explore motivation signals.
          </p>
        </a>
        
        <a
          href="/playground"
          className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
        >
          <h2 className="mb-1 text-lg font-semibold">Playground</h2>
          <p className="text-sm text-gray-600">Cases access</p>
        </a>


        {/* Add more cards later: history, profile, settings, etc. */}
        <div className="rounded-2xl border p-5 opacity-70">
          <h2 className="mb-1 text-lg font-semibold">Coming soon</h2>
          <p className="text-sm text-gray-600">Conversation history, analytics…</p>
        </div>
      </div>
    </div>
  );
}
