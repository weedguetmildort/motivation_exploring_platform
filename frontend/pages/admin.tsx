import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import Link from "next/link";

export default function AdminPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  // Define admin emails - only these users can access this page
  const ADMIN_EMAILS = [
    'javian.sandino@ufl.edu',
    'admin@example.com',
    'teacher@school.edu',
  ];

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { user } = await getMe();
        if (!cancelled) {
          // Check if user is admin
          if (!ADMIN_EMAILS.includes(user.email.toLowerCase())) {
            router.replace("/dashboard");
            return;
          }
          setUser(user);
        }
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
        <div className="text-gray-500">Loading admin panel…</div>
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
            <p className="text-sm text-gray-600">Welcome, {user.email}</p>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="text-blue-600 hover:underline text-sm">
              ← Back to Dashboard
            </Link>
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
          <h2 className="text-xl font-semibold mb-2">Admin Dashboard</h2>
          <p className="text-gray-600">This page is currently under development.</p>
          <p className="text-sm text-gray-500 mt-2">Features coming soon...</p>
        </div>
      </div>
    </div>
  );
}
