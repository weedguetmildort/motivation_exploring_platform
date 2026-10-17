import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import ChatBox from "../components/ChatBox";
import { getMe, logout, type User } from "../lib/auth";
import PageHeader from "../components/PageHeader";

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
      <PageHeader
        title="Chat"
        subtitle="Ask questions and interact with AI chatbot"
        onDashboard={() => router.push("/dashboard")}
        onLogout={onLogout}
      />

      <div className="page-container">
        <ChatBox quizId="default" />
      </div>
    </div>
  );
}