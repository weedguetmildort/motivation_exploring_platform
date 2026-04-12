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
      <header className="site-header">
        <div className="site-header-inner">
          <div>
            <h1 className="page-title">Admin Panel</h1>
            <p className="page-subtitle">Manage quiz questions and survey questions</p>
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

      <div className="page-container">
        <div className="grid gap-4 sm:grid-cols-2">
  
          {user?.is_admin && (
            <Link
              href="/questions_panel"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Quiz Questions Panel</h2>
              <p className="text-sm text-gray-600">Manage quiz questions and answers</p>
            </Link>
          )}

          {user?.is_admin && (
            <Link
              href="/surveys_panel"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Survey Questions Panel</h2>
              <p className="text-sm text-gray-600">Manage stage-based surveys</p>
            </Link>
          )}

          {user?.is_admin && (
            <Link
              href="/links_panel"
              className="rounded-2xl border p-5 shadow-sm hover:shadow transition"
            >
              <h2 className="mb-1 text-lg 2xl:text-xl font-semibold">Links Panel</h2>
              <p className="text-sm text-gray-600">Manage links</p>
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
