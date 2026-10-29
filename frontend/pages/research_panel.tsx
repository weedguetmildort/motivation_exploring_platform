import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import PageHeader from "../components/PageHeader";
import ResearchSummary from "../components/ResearchSummary";

export default function ResearchPanelPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    let cancelled = false;
    getMe().then(result => {
      if (cancelled) return;
      if (!result.user.is_admin) router.replace("/dashboard");
      else setUser(result.user);
    }).catch(() => { if (!cancelled) router.replace("/login"); })
      .finally(() => { if (!cancelled) setChecking(false); });
    return () => { cancelled = true; };
  }, []);
  if (checking) return <div className="grid min-h-screen place-items-center">Loading research results…</div>;
  if (!user) return null;
  return <div className="min-h-screen bg-gray-50">
    <PageHeader title="Research Results" subtitle="Compare participants and inspect individual study results"
      onDashboard={() => router.push("/admin")} onLogout={async () => { try { await logout(); } finally { router.replace("/login"); } }} />
    <div className="page-container"><div className="rounded-xl border bg-white p-4 sm:p-6 shadow-sm"><ResearchSummary /></div></div>
  </div>;
}
