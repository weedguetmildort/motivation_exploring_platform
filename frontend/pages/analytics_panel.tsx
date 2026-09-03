import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { apiFetch } from "../lib/fetcher";
import PageHeader from "../components/PageHeader";

// ── Types ─────────────────────────────────────────────────────────────────────

type CopyEvent = {
  id: string;
  user_email: string;
  question_id: string | null;
  quiz_id: string | null;
  copied_text: string;
  created_at: string;
};

type LinkClick = {
  id: string;
  user_email: string;
  question_id: string | null;
  quiz_id: string | null;
  url: string;
  clicked_at: string;
};

type ChatMessage = {
  id: string;
  user_email: string | null;
  question_id: string | null;
  trigger: string | null;
  stated_choice_id: Record<string, string | null> | null;
  answer_incorrectly: boolean | null;
  manipulation_leaked: Record<string, boolean> | null;
  created_at: string;
};

type Tab = "copy" | "links" | "chat";

// ── Helpers ───────────────────────────────────────────────────────────────────

function ts(iso: string): string {
  return new Date(iso).toLocaleString();
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n) + "…";
}

function SearchInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="relative mb-3 max-w-xs">
      <input
        type="text"
        placeholder="Filter by email…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border px-3 py-1.5 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-accent-400"
      />
      {value && (
        <button
          onClick={() => onChange("")}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs"
        >
          ✕
        </button>
      )}
    </div>
  );
}

// ── Tab: Copy Events ──────────────────────────────────────────────────────────

function CopyEventsTab() {
  const [rows, setRows] = useState<CopyEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    apiFetch<CopyEvent[]>("/api/copy-events")
      .then(setRows)
      .catch(() => setError("Failed to load copy events."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-500 text-sm">Loading…</p>;
  if (error) return <p className="text-red-600 text-sm">{error}</p>;

  const filtered = search
    ? rows.filter((r) => r.user_email.toLowerCase().includes(search.toLowerCase()))
    : rows;

  return (
    <>
      <SearchInput value={search} onChange={setSearch} />
      <p className="mb-2 text-xs text-gray-400">{filtered.length} events</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-gray-500">
              <th className="pb-1 pr-4 font-medium">Timestamp</th>
              <th className="pb-1 pr-4 font-medium">Email</th>
              <th className="pb-1 pr-4 font-medium">Question</th>
              <th className="pb-1 font-medium">Copied Text</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.id} className="border-b last:border-0">
                <td className="py-1.5 pr-4 text-gray-500 whitespace-nowrap">{ts(r.created_at)}</td>
                <td className="py-1.5 pr-4">{r.user_email}</td>
                <td className="py-1.5 pr-4 text-gray-500">{r.question_id ?? "—"}</td>
                <td className="py-1.5 font-mono text-xs text-gray-700">{truncate(r.copied_text, 80)}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={4} className="py-4 text-center text-gray-400">No results.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Tab: Link Clicks ──────────────────────────────────────────────────────────

function LinkClicksTab() {
  const [rows, setRows] = useState<LinkClick[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    apiFetch<LinkClick[]>("/api/links/clicks")
      .then(setRows)
      .catch(() => setError("Failed to load link clicks."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-500 text-sm">Loading…</p>;
  if (error) return <p className="text-red-600 text-sm">{error}</p>;

  const filtered = search
    ? rows.filter((r) => r.user_email.toLowerCase().includes(search.toLowerCase()))
    : rows;

  return (
    <>
      <SearchInput value={search} onChange={setSearch} />
      <p className="mb-2 text-xs text-gray-400">{filtered.length} clicks</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-gray-500">
              <th className="pb-1 pr-4 font-medium">Timestamp</th>
              <th className="pb-1 pr-4 font-medium">Email</th>
              <th className="pb-1 pr-4 font-medium">Question</th>
              <th className="pb-1 font-medium">URL</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.id} className="border-b last:border-0">
                <td className="py-1.5 pr-4 text-gray-500 whitespace-nowrap">{ts(r.clicked_at)}</td>
                <td className="py-1.5 pr-4">{r.user_email}</td>
                <td className="py-1.5 pr-4 text-gray-500">{r.question_id ?? "—"}</td>
                <td className="py-1.5 text-xs text-blue-600 break-all">
                  <a href={r.url} target="_blank" rel="noreferrer">{truncate(r.url, 80)}</a>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={4} className="py-4 text-center text-gray-400">No results.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Tab: Chat Interactions ────────────────────────────────────────────────────

function choiceSummary(stated: Record<string, string | null> | null): string {
  if (!stated) return "—";
  return Object.entries(stated)
    .map(([k, v]) => (k === "default" ? v ?? "none" : `${k}:${v ?? "none"}`))
    .join(", ");
}

// True if the reply appears to have leaked the "answer incorrectly" instruction
// to the participant — this must never happen, so any true value here needs review.
function hasLeaked(leaked: Record<string, boolean> | null): boolean {
  return !!leaked && Object.values(leaked).some(Boolean);
}

function ChatInteractionsTab() {
  const [rows, setRows] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [onlyWithChoice, setOnlyWithChoice] = useState(false);
  const [onlyLeaked, setOnlyLeaked] = useState(false);

  useEffect(() => {
    apiFetch<ChatMessage[]>("/api/messages")
      .then(setRows)
      .catch(() => setError("Failed to load chat interactions."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-500 text-sm">Loading…</p>;
  if (error) return <p className="text-red-600 text-sm">{error}</p>;

  let filtered = rows;
  if (search) filtered = filtered.filter((r) => (r.user_email ?? "").toLowerCase().includes(search.toLowerCase()));
  if (onlyWithChoice) filtered = filtered.filter((r) => r.stated_choice_id != null);
  if (onlyLeaked) filtered = filtered.filter((r) => hasLeaked(r.manipulation_leaked));

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <SearchInput value={search} onChange={setSearch} />
        <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={onlyWithChoice}
            onChange={(e) => setOnlyWithChoice(e.target.checked)}
          />
          Only with stated choice
        </label>
        <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={onlyLeaked}
            onChange={(e) => setOnlyLeaked(e.target.checked)}
          />
          Only leaked manipulation
        </label>
      </div>
      <p className="mb-2 text-xs text-gray-400">{filtered.length} messages</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-gray-500">
              <th className="pb-1 pr-4 font-medium">Timestamp</th>
              <th className="pb-1 pr-4 font-medium">Email</th>
              <th className="pb-1 pr-4 font-medium">Question</th>
              <th className="pb-1 pr-4 font-medium">Trigger</th>
              <th className="pb-1 pr-4 font-medium">Stated Choice</th>
              <th className="pb-1 pr-4 font-medium">Wrong?</th>
              <th className="pb-1 font-medium">Leaked?</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.id} className="border-b last:border-0">
                <td className="py-1.5 pr-4 text-gray-500 whitespace-nowrap">{ts(r.created_at)}</td>
                <td className="py-1.5 pr-4">{r.user_email ?? "—"}</td>
                <td className="py-1.5 pr-4 text-gray-500">{r.question_id ?? "—"}</td>
                <td className="py-1.5 pr-4 text-gray-500">{r.trigger ?? "—"}</td>
                <td className="py-1.5 pr-4 font-mono text-xs">{choiceSummary(r.stated_choice_id)}</td>
                <td className="py-1.5 pr-4">
                  {r.answer_incorrectly == null ? "—" : r.answer_incorrectly ? (
                    <span className="text-red-600 font-medium">Yes</span>
                  ) : (
                    <span className="text-green-700">No</span>
                  )}
                </td>
                <td className="py-1.5">
                  {r.manipulation_leaked == null ? "—" : hasLeaked(r.manipulation_leaked) ? (
                    <span className="text-red-600 font-semibold">⚠ Leaked</span>
                  ) : (
                    <span className="text-green-700">No</span>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={7} className="py-4 text-center text-gray-400">No results.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AnalyticsPanelPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("copy");

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

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading analytics…</div>
      </div>
    );
  }
  if (!user) return null;

  const tabs: { key: Tab; label: string }[] = [
    { key: "copy",  label: "Copy Events" },
    { key: "links", label: "Link Clicks" },
    { key: "chat",  label: "Chat Interactions" },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Analytics Panel"
        subtitle="Participant interaction events"
        onDashboard={() => router.push("/dashboard")}
        onLogout={onLogout}
      />

      <div className="page-container">
        <div className="mb-4 flex flex-wrap gap-2">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                activeTab === t.key
                  ? "bg-blue-600 text-white"
                  : "bg-white border text-gray-600 hover:bg-gray-50"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="rounded-lg border bg-white p-4 shadow-sm">
          {activeTab === "copy"  && <CopyEventsTab />}
          {activeTab === "links" && <LinkClicksTab />}
          {activeTab === "chat"  && <ChatInteractionsTab />}
        </div>
      </div>
    </div>
  );
}
