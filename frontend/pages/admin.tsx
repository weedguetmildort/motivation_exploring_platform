import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import Link from "next/link";


export default function AdminPage() {

  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

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
      {/* Header */}
      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Admin Panel</h1>
            <p className="text-sm text-gray-600">Manage quiz questions and survey questions</p>
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

      <div className="max-w-6xl mx-auto p-6">
        <div className="grid gap-4 sm:grid-cols-2">
  
          {user?.is_admin && (
            <Link
              href="/questions-panel"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg font-semibold">Quiz Questions Panel</h2>
              <p className="text-sm text-gray-600">Manage quiz questions and answers</p>
            </Link>
          )}

          {user?.is_admin && (
            <Link
              href="/surveys-panel"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg font-semibold">Survey Questions Panel</h2>
              <p className="text-sm text-gray-600">Manage stage-based surveys</p>
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
