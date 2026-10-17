// frontend/pages/my_reports.tsx
import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import PageHeader from "../components/PageHeader";
import {
  getMyReports,
  addComment,
  type Report,
  type ReportStatus,
} from "../lib/reports";

type StatusTab = "all" | "open" | "in_progress" | "resolved" | "closed";

const STATUS_TABS: { value: StatusTab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

const CATEGORY_LABELS: Record<string, string> = {
  bug: "Bug",
  unclear_question: "Unclear Question",
  wrong_answer: "Wrong Answer",
  technical: "Technical Issue",
  other: "Other",
};

function ReportStatusBadge({ status }: { status: ReportStatus }) {
  const cfg: Record<ReportStatus, { label: string; cls: string }> = {
    open:        { label: "Open",        cls: "bg-blue-100 text-blue-800 border-blue-200" },
    in_progress: { label: "In Progress", cls: "bg-yellow-100 text-yellow-800 border-yellow-200" },
    resolved:    { label: "Resolved",    cls: "bg-green-100 text-green-800 border-green-200" },
    closed:      { label: "Closed",      cls: "bg-gray-100 text-gray-500 border-gray-200" },
  };
  const { label, cls } = cfg[status] ?? cfg.open;
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${cls}`}>
      {label}
    </span>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MyReportsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [activeTab, setActiveTab] = useState<StatusTab>("all");
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [commentText, setCommentText] = useState<Record<string, string>>({});
  const [commentSubmitting, setCommentSubmitting] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const res = await getMe();
        if (!cancel) setUser(res.user);
      } catch {
        if (!cancel) router.replace("/login");
      } finally {
        if (!cancel) setChecking(false);
      }
    })();
    return () => { cancel = true; };
  }, []);

  useEffect(() => {
    if (!user) return;
    let cancel = false;
    setLoading(true);
    (async () => {
      try {
        const status = activeTab === "all" ? undefined : activeTab as ReportStatus;
        const data = await getMyReports(status);
        if (!cancel) setReports(data);
      } catch (e) {
        console.error(e);
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => { cancel = true; };
  }, [user, activeTab]);

  async function onAddComment(reportId: string) {
    const body = (commentText[reportId] ?? "").trim();
    if (!body) return;
    setCommentSubmitting((prev) => ({ ...prev, [reportId]: true }));
    try {
      const updated = await addComment(reportId, body);
      setReports((prev) => prev.map((r) => r.id === reportId ? updated : r));
      setCommentText((prev) => ({ ...prev, [reportId]: "" }));
    } catch (e) {
      console.error(e);
    } finally {
      setCommentSubmitting((prev) => ({ ...prev, [reportId]: false }));
    }
  }

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }

  if (!user) return null;

  async function onLogout() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  const canComment = (report: Report) =>
    report.status === "open" || report.status === "in_progress";

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="My Reports"
        subtitle="Track issues you've submitted and read admin responses."
        onDashboard={() => router.push("/dashboard")}
        onLogout={onLogout}
      />

      <div className="page-container flex flex-col gap-6">
        {/* Status filter tabs */}
        <div className="flex gap-1 border-b border-gray-200">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === tab.value
                  ? "border-blue-600 text-blue-700"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {loading && <p className="text-sm text-gray-500">Loading…</p>}

        {!loading && reports.length === 0 && (
          <div className="rounded-xl border bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
            No reports found. You can submit a report from the quiz page if you encounter any issues.
          </div>
        )}

        <div className="flex flex-col gap-4">
          {reports.map((report) => {
            const isExpanded = expandedId === report.id;
            return (
              <div key={report.id} className="rounded-xl border bg-white shadow-sm overflow-hidden">
                {/* Collapsed header row */}
                <button
                  onClick={() => setExpandedId(isExpanded ? null : report.id)}
                  className="w-full text-left px-5 py-4 flex items-start gap-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <ReportStatusBadge status={report.status} />
                      <span className="text-xs font-medium text-gray-500 bg-gray-100 rounded-full px-2 py-0.5">
                        {CATEGORY_LABELS[report.category] ?? report.category}
                      </span>
                      {report.quiz_id && (
                        <span className="text-xs text-gray-400">Quiz: {report.quiz_id}</span>
                      )}
                      {report.comments.length > 0 && (
                        <span className="text-xs text-gray-400">
                          {report.comments.length} comment{report.comments.length !== 1 ? "s" : ""}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-900 line-clamp-2">{report.description}</p>
                    <p className="text-xs text-gray-400 mt-1">{formatDate(report.created_at)}</p>
                  </div>
                  <svg
                    className={`h-4 w-4 text-gray-400 shrink-0 mt-1 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="border-t px-5 py-4 flex flex-col gap-4">
                    {/* Description */}
                    <div className="bg-gray-50 rounded-lg px-4 py-3 text-sm text-gray-800 whitespace-pre-wrap">
                      {report.description}
                    </div>

                    {/* Comment thread */}
                    {report.comments.length > 0 && (
                      <div className="flex flex-col gap-2">
                        <p className="text-xs font-semibold uppercase tracking-widest text-gray-400">
                          Comments
                        </p>
                        {report.comments.map((c) => (
                          <div
                            key={c.id}
                            className={`rounded-lg px-4 py-3 text-sm ${
                              c.is_admin
                                ? "bg-blue-50 border border-blue-100"
                                : "bg-gray-50 border border-gray-100"
                            }`}
                          >
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-medium text-gray-900">{c.author_email}</span>
                              {c.is_admin && (
                                <span className="text-xs bg-blue-100 text-blue-700 rounded-full px-1.5 py-0.5 font-semibold">
                                  Admin
                                </span>
                              )}
                              <span className="text-xs text-gray-400 ml-auto">{formatDate(c.created_at)}</span>
                            </div>
                            <p className="text-gray-700 whitespace-pre-wrap">{c.body}</p>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Add comment — only while open or in progress */}
                    {canComment(report) && (
                      <div className="flex flex-col gap-2">
                        <textarea
                          value={commentText[report.id] ?? ""}
                          onChange={(e) =>
                            setCommentText((prev) => ({ ...prev, [report.id]: e.target.value }))
                          }
                          placeholder="Add a follow-up comment…"
                          rows={3}
                          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
                        />
                        <div className="flex justify-end">
                          <button
                            onClick={() => onAddComment(report.id)}
                            disabled={
                              commentSubmitting[report.id] ||
                              !(commentText[report.id] ?? "").trim()
                            }
                            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition"
                          >
                            {commentSubmitting[report.id] ? "Posting…" : "Post comment"}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
