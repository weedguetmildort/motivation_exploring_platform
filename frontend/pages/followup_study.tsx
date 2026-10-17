import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import PageHeader from "../components/PageHeader";
import {
  QUIZ2_PLACEHOLDER_TITLE,
  QUIZ2_PLACEHOLDER_BODY,
  isFollowupEligible,
} from "../lib/quiz2";

// Phase 13 — placeholder landing for the admin-granted follow-up study.
// The Start button on the dashboard routes here. Only reachable once an admin
// has granted access AND the participant has completed the original study;
// ineligible visitors are bounced back to the dashboard.
export default function FollowupStudyPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getMe();
        if (cancelled) return;
        if (!isFollowupEligible(res.user)) {
          router.replace("/dashboard");
          return;
        }
        setUser(res.user);
      } catch {
        if (!cancelled) router.replace("/login");
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  async function onLogout() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Follow-Up Study"
        subtitle="A second study you've been invited to."
        onDashboard={() => router.push("/dashboard")}
        onLogout={onLogout}
      />

      <div className="page-container">
        <div className="mx-auto max-w-2xl rounded-2xl border-2 border-blue-200 bg-white p-8 text-center shadow-sm">
          <h1 className="text-2xl font-bold text-gray-900">{QUIZ2_PLACEHOLDER_TITLE}</h1>
          <p className="mt-3 leading-relaxed text-gray-600">{QUIZ2_PLACEHOLDER_BODY}</p>
          <button
            onClick={() => router.push("/dashboard")}
            className="mt-6 rounded-xl bg-blue-600 px-6 py-3 text-base font-semibold text-white shadow hover:bg-blue-700 active:scale-[0.98] transition-all"
          >
            Return to dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
