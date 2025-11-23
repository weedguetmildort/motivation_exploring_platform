import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { getMe, logout, changePassword, type User } from "../lib/auth";

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  // password form state
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (!cancel) {
          setUser(res.user);
        }
      } catch {
        if (!cancel) {
          // Not logged in
          router.replace("/login");
        }
      } finally {
        if (!cancel) setChecking(false);
      }
    })();

    return () => {
      cancel = true;
    };
  }, [router]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading profile…</div>
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
    setError(null);
    setSuccess(null);

    if (!currentPw || !newPw || !confirmPw) {
      setError("Please fill out all fields.");
      return;
    }

    if (newPw !== confirmPw) {
      setError("New password and confirmation do not match.");
      return;
    }

    if (newPw.length < 6) {
      setError("New password must be at least 6 characters long.");
      return;
    }

    setSaving(true);
    try {
      await changePassword(currentPw, newPw);
      setSuccess("Password updated successfully.");
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
    } catch (err: any) {
      console.error("Failed to change password", err);
      // try to surface backend error if available
      const msg =
        err?.message ||
        (err?.detail as string | undefined) ||
        "Failed to change password.";
      setError(typeof msg === "string" ? msg : "Failed to change password.");
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
            <h1 className="text-2xl font-semibold text-gray-900">Profile</h1>
            <p className="text-sm text-gray-600">Edit your user password</p>
          </div>
          <div className="flex items-center gap-3">
            <button 
              onClick={() => router.push("/dashboard")}
              className="text-sm px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
            >
              Back to Dashboard
            </button>
            <button
              onClick={onLogout}
              className="text-sm px-4 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 transition"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-xl mx-auto p-6">
        <div className="bg-white rounded-xl p-6 shadow-sm border">
          <h2 className="text-lg font-semibold mb-4">Change Password</h2>
          <p className="text-sm text-gray-600 mb-4">
            Update your password by confirming your current password first.
          </p>

          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">
                Current password
              </label>
              <input
                type="password"
                className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring"
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                New password
              </label>
              <input
                type="password"
                className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring"
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Confirm new password
              </label>
              <input
                type="password"
                className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring"
                value={confirmPw}
                onChange={(e) => setConfirmPw(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>

            {error && (
              <div className="text-sm text-red-600" role="alert">
                {error}
              </div>
            )}

            {success && (
              <div className="text-sm text-green-600" role="status">
                {success}
              </div>
            )}

            <button
              type="submit"
              disabled={saving}
              className="mt-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {saving ? "Updating…" : "Update password"}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
