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
        <div className="text-gray-500">Checking session…</div>
      </div>
    );
  }

  if (!user) return null; // redirected

  async function onLogout() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="site-header">
        <div className="site-header-inner">
          <div>
            <h1 className="page-title">Chat</h1>
            <p className="page-subtitle">Ask questions and interact with AI chatbot</p>
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
        <ChatBox quizId="default" />
      </div>
    </div>
  );
}