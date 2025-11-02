import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import ChatBox from "../components/ChatBox";
import { getMe, type User } from "../lib/auth";

// Simple client-side guard. For stronger security, also check auth on the backend per request.
export default function ChatPage() {
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
    return () => {
      cancelled = true;
    };
  }, [router]);

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
        <a href="/dashboard" className="text-sm text-blue-600 underline">
          Back to dashboard
        </a>
      </header>
      <ChatBox />
    </div>
  );
}