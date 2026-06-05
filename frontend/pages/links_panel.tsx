// frontend/pages/links_panel.tsx
import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { apiFetch } from "../lib/fetcher";

const PREDEFINED_TAGS = [
  "Statistical Inference & Descriptive Statistics",
  "Conditional Probability",
  "Combinatorics & Counting",
  "Basic Probability",
  "Other",
] as const;

type LinkStatus = "READY" | "NOT_READY" | "NEEDS_REVIEW" | "REJECTED";

type KnowledgeLink = {
  id: string;
  title: string;
  url: string;
  tags: string[];
  description: string;
  status: LinkStatus;
  last_checked?: string;
  last_http_code?: number;
  last_error_type?: string;
  created_at?: string;
  updated_at?: string;
};

type ActiveTab = "all" | "review" | "dead";

function StatusBadge({ status }: { status: LinkStatus }) {
  const cfg: Record<LinkStatus, { label: string; cls: string }> = {
    READY:        { label: "Ready",          cls: "bg-green-100 text-green-800 border-green-200" },
    NOT_READY:    { label: "Not Ready",      cls: "bg-red-100 text-red-800 border-red-200" },
    NEEDS_REVIEW: { label: "Needs Review",   cls: "bg-yellow-100 text-yellow-800 border-yellow-200" },
    REJECTED:     { label: "Rejected",       cls: "bg-gray-100 text-gray-500 border-gray-200" },
  };
  const { label, cls } = cfg[status] ?? cfg.READY;
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${cls}`}>
      {label}
    </span>
  );
}

export default function LinkPanelPage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  // create form
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState<string[]>([]);

  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // list state
  const [links, setLinks] = useState<KnowledgeLink[]>([]);
  const [loadingLinks, setLoadingLinks] = useState(false);
  const [linksError, setLinksError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("all");

  // edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Partial<KnowledgeLink>>({});
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);

  // health check trigger
  const [healthChecking, setHealthChecking] = useState(false);

  // --- auth gate (admin only) ---
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;
        if (!res.user.is_admin) { router.replace("/dashboard"); return; }
        setUser(res.user);
      } catch {
        if (!cancel) router.replace("/login");
      } finally {
        if (!cancel) setChecking(false);
      }
    })();
    return () => { cancel = true; };
  }, []);

  // --- load links ---
  useEffect(() => {
    if (!user) return;
    let cancel = false;
    async function loadLinks() {
      setLoadingLinks(true);
      setLinksError(null);
      try {
        const data = await apiFetch<KnowledgeLink[]>("/api/knowledge-links");
        if (!cancel) setLinks(data);
      } catch (e) {
        console.error(e);
        if (!cancel) setLinksError("Failed to load knowledge links.");
      } finally {
        if (!cancel) setLoadingLinks(false);
      }
    }
    loadLinks();
    return () => { cancel = true; };
  }, [user]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading admin links panel…</div>
      </div>
    );
  }

  if (!user) return null;

  async function onLogout() {
    try { await logout(); } finally { router.replace("/login"); }
  }

  function isValidUrl(value: string) {
    try { new URL(value); return true; } catch { return false; }
  }

  function selectTag(tag: string, current: string[], set: (v: string[]) => void) {
    set(current.includes(tag) ? [] : [tag]);
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);

    if (!title.trim()) { setMessage("Title is required."); return; }
    if (!url.trim()) { setMessage("URL is required."); return; }
    if (!isValidUrl(url.trim())) { setMessage("Please enter a valid URL."); return; }
    const duplicate = links.find((l) => l.url.trim().toLowerCase() === url.trim().toLowerCase());
    if (duplicate) { setMessage(`This URL is already in the database ("${duplicate.title}").`); return; }
    if (!description.trim()) { setMessage("Description is required."); return; }
    if (tags.length === 0) { setMessage("Please select a tag."); return; }

    setSaving(true);
    try {
      const created = await apiFetch<KnowledgeLink>("/api/knowledge-links", {
        method: "POST",
        body: JSON.stringify({ title: title.trim(), url: url.trim(), description: description.trim(), tags }),
      });
      setLinks((prev) => [created, ...prev]);
      setTitle(""); setUrl(""); setDescription(""); setTags([]);
      setMessage("Knowledge link added.");
    } catch (e) {
      console.error(e);
      setMessage("Failed to add knowledge link.");
    } finally {
      setSaving(false);
    }
  }

  function beginEdit(link: KnowledgeLink) {
    setEditingId(link.id);
    setEditDraft({ ...link, tags: link.tags ?? [] });
  }

  function cancelEdit() { setEditingId(null); setEditDraft({}); }

  async function saveEdit(id: string) {
    if (!editDraft.title?.trim()) { alert("Title is required."); return; }
    if (!editDraft.url?.trim()) { alert("URL is required."); return; }
    if (!isValidUrl(editDraft.url)) { alert("Please enter a valid URL."); return; }
    if (!editDraft.description?.trim()) { alert("Description is required."); return; }
    if (!editDraft.tags || editDraft.tags.length === 0) { alert("Please select a tag."); return; }

    setSavingEdit(true);
    try {
      const updated = await apiFetch<KnowledgeLink>(`/api/knowledge-links/${id}`, {
        method: "PUT",
        body: JSON.stringify({
          title: editDraft.title.trim(),
          url: editDraft.url.trim(),
          description: editDraft.description.trim(),
          tags: editDraft.tags ?? [],
        }),
      });
      setLinks((prev) => prev.map((x) => (x.id === id ? updated : x)));
      cancelEdit();
    } catch (e) {
      console.error(e);
      alert("Failed to update knowledge link.");
    } finally {
      setSavingEdit(false);
    }
  }

  async function deleteLink(id: string) {
    if (!window.confirm("Delete this knowledge link?")) return;
    setDeletingId(id);
    try {
      await apiFetch<void>(`/api/knowledge-links/${id}`, { method: "DELETE" });
      setLinks((prev) => prev.filter((x) => x.id !== id));
    } catch (e) {
      console.error(e);
      alert("Failed to delete knowledge link.");
    } finally {
      setDeletingId(null);
    }
  }

  async function approveLink(id: string) {
    setApprovingId(id);
    try {
      const updated = await apiFetch<KnowledgeLink>(`/api/knowledge-links/${id}/approve`, { method: "POST" });
      setLinks((prev) => prev.map((x) => (x.id === id ? updated : x)));
    } catch (e) {
      console.error(e);
      alert("Failed to approve link.");
    } finally {
      setApprovingId(null);
    }
  }

  async function rejectLink(id: string) {
    if (!window.confirm("Reject this link? It will be tombstoned and never suggested again.")) return;
    setRejectingId(id);
    try {
      const updated = await apiFetch<KnowledgeLink>(`/api/knowledge-links/${id}/reject`, { method: "POST" });
      setLinks((prev) => prev.map((x) => (x.id === id ? updated : x)));
    } catch (e) {
      console.error(e);
      alert("Failed to reject link.");
    } finally {
      setRejectingId(null);
    }
  }

  async function triggerHealthCheck() {
    setHealthChecking(true);
    try {
      await apiFetch("/api/knowledge-links/trigger-health-check", { method: "POST" });
      setMessage("Health check triggered. Refresh in a moment to see updated statuses.");
    } catch (e) {
      console.error(e);
      setMessage("Failed to trigger health check.");
    } finally {
      setHealthChecking(false);
    }
  }

  const filteredLinks = links.filter((l) => {
    if (activeTab === "review") return l.status === "NEEDS_REVIEW";
    if (activeTab === "dead") return l.status === "NOT_READY";
    return true;
  });

  const reviewCount = links.filter((l) => l.status === "NEEDS_REVIEW").length;
  const deadCount = links.filter((l) => l.status === "NOT_READY").length;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="site-header">
        <div className="site-header-inner">
          <div>
            <h1 className="page-title">Knowledge Links Panel</h1>
            <p className="page-subtitle">Manage links the chatbot can use in its answers.</p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={triggerHealthCheck}
              disabled={healthChecking}
              className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
            >
              {healthChecking ? "Checking…" : "Trigger Health Check"}
            </button>
            <button onClick={() => router.push("/dashboard")} className="btn-primary">
              Back to Dashboard
            </button>
            <button onClick={onLogout} className="btn-secondary">Logout</button>
          </div>
        </div>
      </header>

      <div className="page-container">
        <div className="bg-white rounded-xl p-8 shadow-sm border">
          <h2 className="text-xl 2xl:text-2xl font-semibold mb-4">Add Knowledge Link</h2>

          <form onSubmit={onCreate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Title</label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                placeholder="Example: Khan Academy — Probability"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">URL</label>
              {(() => {
                const trimmed = url.trim();
                const isDuplicate = trimmed.length > 0 && isValidUrl(trimmed) &&
                  links.some((l) => l.url.trim().toLowerCase() === trimmed.toLowerCase());
                const isUnique = trimmed.length > 0 && isValidUrl(trimmed) && !isDuplicate;
                return (
                  <>
                    <input
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      className={`w-full rounded-lg border px-3 py-2 text-sm ${
                        isDuplicate
                          ? "border-red-500 bg-red-50 focus:outline-none focus:ring-1 focus:ring-red-500"
                          : isUnique
                          ? "border-green-500 bg-green-50 focus:outline-none focus:ring-1 focus:ring-green-500"
                          : ""
                      }`}
                      placeholder="https://example.com/resource"
                      required
                    />
                    {isDuplicate && <p className="mt-1 text-xs font-medium text-red-600">Link already in the database</p>}
                    {isUnique && <p className="mt-1 text-xs font-medium text-green-600">New link</p>}
                  </>
                );
              })()}
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Brief Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                rows={4}
                placeholder="Describe what this page covers so the chatbot can decide when it is relevant."
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Tag</label>
              <div className="flex flex-wrap gap-2">
                {PREDEFINED_TAGS.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => selectTag(tag, tags, setTags)}
                    className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                      tags.includes(tag)
                        ? "bg-blue-600 text-white border-blue-600"
                        : "bg-white text-gray-600 border-gray-300 hover:border-blue-400"
                    }`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            {message && (
              <div
                role="status"
                className={`rounded-lg px-4 py-3 text-sm font-medium border ${
                  message.toLowerCase().includes("added") || message.toLowerCase().includes("triggered")
                    ? "bg-green-50 text-green-800 border-green-300"
                    : "bg-red-50 text-red-800 border-red-300"
                }`}
              >
                {message}
              </div>
            )}

            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={saving}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {saving ? "Saving…" : "Save knowledge link"}
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => { setTitle(""); setUrl(""); setDescription(""); setTags([]); setMessage(null); }}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-60"
              >
                Clear form
              </button>
            </div>
          </form>
        </div>
      </div>

      <div className="max-w-6xl 2xl:max-w-screen-2xl mx-auto pt-0 px-6 pb-6">
        <div className="bg-white rounded-xl p-8 shadow-sm border">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl 2xl:text-2xl font-semibold">View Knowledge Links</h2>
          </div>

          {/* Tabs */}
          <div className="flex gap-2 mb-4">
            {(["all", "review", "dead"] as ActiveTab[]).map((tab) => {
              const label =
                tab === "all" ? `All (${links.length})` :
                tab === "review" ? `Review Queue${reviewCount > 0 ? ` (${reviewCount})` : ""}` :
                `Dead Links${deadCount > 0 ? ` (${deadCount})` : ""}`;
              return (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`rounded-full px-4 py-1.5 text-sm font-medium border transition-colors ${
                    activeTab === tab
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white text-gray-600 border-gray-300 hover:border-blue-400"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>

          {loadingLinks && <p className="text-sm text-gray-500">Loading knowledge links…</p>}
          {linksError && <p className="text-sm text-red-600 mb-2">{linksError}</p>}

          {!loadingLinks && !linksError && filteredLinks.length === 0 && (
            <p className="text-sm text-gray-500">
              {activeTab === "review" ? "No links awaiting review." :
               activeTab === "dead" ? "No dead links." :
               "No knowledge links yet."}
            </p>
          )}

          {!loadingLinks && filteredLinks.length > 0 && (
            <div className="mt-2 space-y-3">
              {filteredLinks.map((link) => {
                const isEditing = editingId === link.id;

                return (
                  <div key={link.id} className="rounded-lg border px-4 py-3 bg-gray-50">
                    <div className="flex justify-between items-start gap-4">
                      <div className="min-w-0 flex-1">
                        {!isEditing ? (
                          <>
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-sm font-semibold text-gray-900">{link.title}</span>
                              <StatusBadge status={link.status} />
                            </div>

                            <div className="mt-1 text-xs text-blue-700 break-all">
                              <a href={link.url} target="_blank" rel="noreferrer" className="underline">
                                {link.url}
                              </a>
                            </div>

                            <div className="mt-2 text-sm text-gray-700">{link.description}</div>

                            {link.tags.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {link.tags.map((tag) => (
                                  <span key={tag} className="rounded-full bg-blue-100 px-2 py-1 text-xs text-blue-700">
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            )}

                            {link.last_checked && (
                              <div className="mt-1 text-xs text-gray-400">
                                Last checked: {new Date(link.last_checked).toLocaleString()}
                                {link.last_http_code ? ` · HTTP ${link.last_http_code}` : ""}
                                {link.last_error_type ? ` · ${link.last_error_type}` : ""}
                              </div>
                            )}
                          </>
                        ) : (
                          <div className="space-y-3">
                            <div>
                              <label className="block text-xs font-medium mb-1">Title</label>
                              <input
                                value={editDraft.title ?? ""}
                                onChange={(e) => setEditDraft((d) => ({ ...d, title: e.target.value }))}
                                className="w-full rounded border px-2 py-1 text-sm"
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-medium mb-1">URL</label>
                              <input
                                value={editDraft.url ?? ""}
                                onChange={(e) => setEditDraft((d) => ({ ...d, url: e.target.value }))}
                                className="w-full rounded border px-2 py-1 text-sm"
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-medium mb-1">Description</label>
                              <textarea
                                value={editDraft.description ?? ""}
                                onChange={(e) => setEditDraft((d) => ({ ...d, description: e.target.value }))}
                                className="w-full rounded border px-2 py-1 text-sm"
                                rows={4}
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-medium mb-1">Tag</label>
                              <div className="flex flex-wrap gap-2">
                                {PREDEFINED_TAGS.map((tag) => {
                                  const selected = (editDraft.tags ?? []).includes(tag);
                                  return (
                                    <button
                                      key={tag}
                                      type="button"
                                      onClick={() => setEditDraft((d) => ({ ...d, tags: selected ? [] : [tag] }))}
                                      className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                                        selected
                                          ? "bg-blue-600 text-white border-blue-600"
                                          : "bg-white text-gray-600 border-gray-300 hover:border-blue-400"
                                      }`}
                                    >
                                      {tag}
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Action buttons per status */}
                      <div className="flex flex-col items-end gap-2 text-xs shrink-0">
                        {!isEditing ? (
                          <>
                            {link.status === "NEEDS_REVIEW" && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => approveLink(link.id)}
                                  disabled={approvingId === link.id}
                                  className="px-2 py-1 rounded border border-green-400 bg-white text-green-700 hover:bg-green-50 disabled:opacity-60"
                                >
                                  {approvingId === link.id ? "Approving…" : "Approve"}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => rejectLink(link.id)}
                                  disabled={rejectingId === link.id}
                                  className="px-2 py-1 rounded border border-red-300 bg-white text-red-600 hover:bg-red-50 disabled:opacity-60"
                                >
                                  {rejectingId === link.id ? "Rejecting…" : "Reject"}
                                </button>
                              </>
                            )}

                            {link.status === "NOT_READY" && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => rejectLink(link.id)}
                                  disabled={rejectingId === link.id}
                                  className="px-2 py-1 rounded border border-red-300 bg-white text-red-600 hover:bg-red-50 disabled:opacity-60"
                                >
                                  {rejectingId === link.id ? "Rejecting…" : "Reject"}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => deleteLink(link.id)}
                                  disabled={deletingId === link.id}
                                  className="px-2 py-1 rounded border border-gray-300 bg-white text-gray-600 hover:bg-gray-100 disabled:opacity-60"
                                >
                                  {deletingId === link.id ? "Deleting…" : "Delete"}
                                </button>
                              </>
                            )}

                            {link.status === "READY" && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => beginEdit(link)}
                                  className="px-2 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100"
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  onClick={() => deleteLink(link.id)}
                                  disabled={deletingId === link.id}
                                  className="px-2 py-1 rounded border border-red-300 bg-white text-red-600 hover:bg-red-50 disabled:opacity-60"
                                >
                                  {deletingId === link.id ? "Deleting…" : "Delete"}
                                </button>
                              </>
                            )}

                            {link.status === "REJECTED" && (
                              <span className="text-gray-400 italic">Tombstoned</span>
                            )}
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => saveEdit(link.id)}
                              disabled={savingEdit}
                              className="px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                            >
                              {savingEdit ? "Saving…" : "Save"}
                            </button>
                            <button
                              type="button"
                              onClick={cancelEdit}
                              className="px-3 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100"
                            >
                              Cancel
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
