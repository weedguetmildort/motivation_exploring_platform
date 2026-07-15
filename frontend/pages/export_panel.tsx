import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import PageHeader from "../components/PageHeader";

type ExportType = "participants" | "quiz-answers" | "survey-responses" | "events" | "chat-messages";

const EXPORTS: { key: ExportType; label: string; description: string }[] = [
  {
    key: "participants",
    label: "Participants",
    description: "All enrolled participants with study progress, consent, and variant assignment.",
  },
  {
    key: "quiz-answers",
    label: "Quiz Answers",
    description: "One row per answered question: choice selected, correctness, and timing data.",
  },
  {
    key: "survey-responses",
    label: "Survey Responses",
    description: "One row per survey item response, across all stages and participants.",
  },
  {
    key: "events",
    label: "Events (Copy + Links)",
    description: "Merged copy events and link clicks, sorted by timestamp.",
  },
  {
    key: "chat-messages",
    label: "Chat Messages",
    description: "Assistant messages with stated choice IDs and answer-incorrectly flags.",
  },
];

export default function ExportPanelPage() {
  const router = useRouter();
  const [user, setUser]         = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [downloading, setDownloading] = useState<Set<ExportType>>(new Set());

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const res = await getMe();
        if (!cancel) {
          if (!res.user.is_admin) { router.replace("/dashboard"); return; }
          setUser(res.user);
        }
      } catch {
        if (!cancel) router.replace("/login");
      } finally {
        if (!cancel) setChecking(false);
      }
    })();
    return () => { cancel = true; };
  }, []);

  async function onLogout() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  function handleDownload(key: ExportType) {
    setDownloading((prev) => new Set(prev).add(key));
    window.open(`/api/export/${key}`, "_blank");
    setTimeout(() => {
      setDownloading((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }, 2000);
  }

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading export panel…</div>
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Export Data"
        subtitle="Download study data as CSV files"
        onDashboard={() => router.push("/dashboard")}
        onLogout={onLogout}
      />

      <div className="page-container">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {EXPORTS.map(({ key, label, description }) => {
            const busy = downloading.has(key);
            return (
              <div
                key={key}
                className="flex flex-col justify-between rounded-lg border bg-white p-5 shadow-sm"
              >
                <div>
                  <h2 className="mb-1 font-semibold text-gray-900">{label}</h2>
                  <p className="text-sm text-gray-500">{description}</p>
                </div>
                <button
                  onClick={() => handleDownload(key)}
                  disabled={busy}
                  className="btn-primary mt-4 w-full disabled:opacity-60"
                >
                  {busy ? "Opening…" : "Download CSV"}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
