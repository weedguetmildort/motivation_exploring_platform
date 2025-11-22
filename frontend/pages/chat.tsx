import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import ChatBox from "../components/ChatBox";
import { getMe, logout, type User } from "../lib/auth";

// Simple client-side guard. For stronger security, also check auth on the backend per request.
export default function ChatPage() {
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
            window.location.href = "/dashboard";
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

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Checking session…</div>
      </div>
    );
  }

  if (!user) return null; // redirected

  return (
    <div className="min-h-screen p-6">
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Chat</h1>
        <div className="text-sm text-gray-600">Signed in as {user.email}</div>
          <button 
            onClick={() => router.push("/dashboard")}
            className="text-sm px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
          >
            Back to Dashboard
          </button>
      </header>
      <ChatBox />
    </div>
  );
}