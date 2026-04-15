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

type KnowledgeLink = {
  id: string;
  title: string;
  url: string;
  tags: string[];
  description: string;
  active: boolean;
  created_at?: string;
  updated_at?: string;
};

export default function LinkPanelPage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  // create form
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [active, setActive] = useState(true);

  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // list state
  const [links, setLinks] = useState<KnowledgeLink[]>([]);
  const [loadingLinks, setLoadingLinks] = useState(false);
  const [linksError, setLinksError] = useState<string | null>(null);

  // edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Partial<KnowledgeLink>>({});
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // --- auth gate (admin only) ---
  useEffect(() => {
    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;

        if (!res.user.is_admin) {
          window.location.href = "/dashboard";
          return;
        }

        setUser(res.user);
      } catch {
        if (!cancel) window.location.href = "/login";
      } finally {
        if (!cancel) setChecking(false);
      }
    })();

    return () => {
      cancel = true;
    };
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

    return () => {
      cancel = true;
    };
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
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  function isValidUrl(value: string) {
    try {
      new URL(value);
      return true;
    } catch {
      return false;
    }
  }

  function selectTag(tag: string, current: string[], set: (v: string[]) => void) {
    set(current.includes(tag) ? [] : [tag]);
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);

    if (!title.trim()) {
      setMessage("Title is required.");
      return;
    }

    if (!url.trim()) {
      setMessage("URL is required.");
      return;
    }

    if (!isValidUrl(url.trim())) {
      setMessage("Please enter a valid URL.");
      return;
    }

    const duplicate = links.find(
      (l) => l.url.trim().toLowerCase() === url.trim().toLowerCase(),
    );
    if (duplicate) {
      setMessage(`This URL is already in the database ("${duplicate.title}").`);
      return;
    }

    if (!description.trim()) {
      setMessage("Description is required.");
      return;
    }

    if (tags.length === 0) {
      setMessage("Please select a tag.");
      return;
    }

    setSaving(true);

    try {
      const payload = {
        title: title.trim(),
        url: url.trim(),
        description: description.trim(),
        tags,
        active,
      };

      const created = await apiFetch<KnowledgeLink>("/api/knowledge-links", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      setLinks((prev) => [created, ...prev]);

      // reset form
      setTitle("");
      setUrl("");
      setDescription("");
      setTags([]);
      setActive(true);
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
    setEditDraft({
      ...link,
      tags: link.tags ?? [],
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditDraft({});
  }

  async function saveEdit(id: string) {
    if (!editDraft.title?.trim()) {
      alert("Title is required.");
      return;
    }

    if (!editDraft.url?.trim()) {
      alert("URL is required.");
      return;
    }

    if (!isValidUrl(editDraft.url)) {
      alert("Please enter a valid URL.");
      return;
    }

    if (!editDraft.description?.trim()) {
      alert("Description is required.");
      return;
    }

    if (!editDraft.tags || editDraft.tags.length === 0) {
      alert("Please select a tag.");
      return;
    }

    setSavingEdit(true);

    try {
      const payload = {
        title: editDraft.title.trim(),
        url: editDraft.url.trim(),
        description: editDraft.description.trim(),
        tags: editDraft.tags ?? [],
        active: editDraft.active ?? true,
      };

      const updated = await apiFetch<KnowledgeLink>(
        `/api/knowledge-links/${id}`,
        {
          method: "PUT",
          body: JSON.stringify(payload),
        },
      );

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
      await apiFetch<void>(`/api/knowledge-links/${id}`, {
        method: "DELETE",
      });

      setLinks((prev) => prev.filter((x) => x.id !== id));
    } catch (e) {
      console.error(e);
      alert("Failed to delete knowledge link.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="site-header">
        <div className="site-header-inner">
          <div>
            <h1 className="page-title">Knowledge Links Panel</h1>
            <p className="page-subtitle">
              Manage links the chatbot can use in its answers.
            </p>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="btn-primary"
            >
              Back to Dashboard
            </button>
            <button onClick={onLogout} className="btn-secondary">
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="page-container">
        <div className="bg-white rounded-xl p-8 shadow-sm border">
          <h2 className="text-xl 2xl:text-2xl font-semibold mb-4">
            Add Knowledge Link
          </h2>

          <form onSubmit={onCreate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Title</label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                placeholder="Example: Student Refund Policy"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">URL</label>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                placeholder="https://example.com/refund-policy"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Brief Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                rows={4}
                placeholder="Describe what this page is about so the chatbot can decide when it is relevant."
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Tags</label>
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

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
              />
              Active
            </label>

            {message && (
              <div
                role="status"
                className={`rounded-lg px-4 py-3 text-sm font-medium border ${
                  message.toLowerCase().includes("added")
                    ? "bg-green-50 text-green-800 border-green-300"
                    : "bg-red-50 text-red-800 border-red-300"
                }`}
              >
                {message}
              </div>
            )}

            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save knowledge link"}
            </button>
          </form>
        </div>
      </div>

      <div className="max-w-6xl 2xl:max-w-screen-2xl mx-auto pt-0 px-6 pb-6">
        <div className="bg-white rounded-xl p-8 shadow-sm border">
          <h2 className="text-xl 2xl:text-2xl font-semibold mb-2">
            View Knowledge Links
          </h2>

          {loadingLinks && (
            <p className="text-sm text-gray-500">Loading knowledge links…</p>
          )}

          {linksError && (
            <p className="text-sm text-red-600 mb-2">{linksError}</p>
          )}

          {!loadingLinks && !linksError && links.length === 0 && (
            <p className="text-sm text-gray-500">No knowledge links yet.</p>
          )}

          {!loadingLinks && links.length > 0 && (
            <div className="mt-4 space-y-3">
              {links.map((link) => {
                const isEditing = editingId === link.id;

                return (
                  <div
                    key={link.id}
                    className="rounded-lg border px-4 py-3 bg-gray-50"
                  >
                    <div className="flex justify-between items-start gap-4">
                      <div className="min-w-0 flex-1">
                        {!isEditing ? (
                          <>
                            <div className="text-sm font-semibold text-gray-900">
                              {link.title}
                            </div>

                            <div className="mt-1 text-xs text-blue-700 break-all">
                              <a
                                href={link.url}
                                target="_blank"
                                rel="noreferrer"
                                className="underline"
                              >
                                {link.url}
                              </a>
                            </div>

                            <div className="mt-2 text-sm text-gray-700">
                              {link.description}
                            </div>

                            {link.tags.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {link.tags.map((tag) => (
                                  <span
                                    key={tag}
                                    className="rounded-full bg-blue-100 px-2 py-1 text-xs text-blue-700"
                                  >
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            )}

                            <div className="mt-2 text-xs text-gray-500">
                              Status:{" "}
                              <span className="font-medium">
                                {link.active ? "Active" : "Inactive"}
                              </span>
                            </div>
                          </>
                        ) : (
                          <div className="space-y-3">
                            <div>
                              <label className="block text-xs font-medium mb-1">
                                Title
                              </label>
                              <input
                                value={editDraft.title ?? ""}
                                onChange={(e) =>
                                  setEditDraft((d) => ({
                                    ...d,
                                    title: e.target.value,
                                  }))
                                }
                                className="w-full rounded border px-2 py-1 text-sm"
                              />
                            </div>

                            <div>
                              <label className="block text-xs font-medium mb-1">
                                URL
                              </label>
                              <input
                                value={editDraft.url ?? ""}
                                onChange={(e) =>
                                  setEditDraft((d) => ({
                                    ...d,
                                    url: e.target.value,
                                  }))
                                }
                                className="w-full rounded border px-2 py-1 text-sm"
                              />
                            </div>

                            <div>
                              <label className="block text-xs font-medium mb-1">
                                Description
                              </label>
                              <textarea
                                value={editDraft.description ?? ""}
                                onChange={(e) =>
                                  setEditDraft((d) => ({
                                    ...d,
                                    description: e.target.value,
                                  }))
                                }
                                className="w-full rounded border px-2 py-1 text-sm"
                                rows={4}
                              />
                            </div>

                            <div>
                              <label className="block text-xs font-medium mb-1">
                                Tags
                              </label>
                              <div className="flex flex-wrap gap-2">
                                {PREDEFINED_TAGS.map((tag) => {
                                  const selected = (editDraft.tags ?? []).includes(tag);
                                  return (
                                    <button
                                      key={tag}
                                      type="button"
                                      onClick={() =>
                                        setEditDraft((d) => ({
                                          ...d,
                                          tags: selected ? [] : [tag],
                                        }))
                                      }
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

                            <label className="flex items-center gap-2 text-sm">
                              <input
                                type="checkbox"
                                checked={editDraft.active ?? true}
                                onChange={(e) =>
                                  setEditDraft((d) => ({
                                    ...d,
                                    active: e.target.checked,
                                  }))
                                }
                              />
                              Active
                            </label>
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-2 text-xs shrink-0">
                        {!isEditing ? (
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