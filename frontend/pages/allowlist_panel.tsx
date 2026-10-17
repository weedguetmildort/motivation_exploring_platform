// frontend/pages/allowlist_panel.tsx
import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { apiFetch } from "../lib/fetcher";

type AllowlistEntry = {
  id: string;
  domain: string;
  added_by: string;
  added_at: string;
};

const BARE_DOMAIN_RE = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/;

function normalizeDomain(raw: string): string {
  let s = raw.trim().toLowerCase();
  // Strip scheme
  s = s.replace(/^https?:\/\//, "");
  // Strip path and query
  s = s.split("/")[0].split("?")[0];
  // Strip leading www.
  if (s.startsWith("www.")) s = s.slice(4);
  // Strip port
  s = s.split(":")[0];
  return s;
}

export default function AllowlistPanelPage() {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  const [entries, setEntries] = useState<AllowlistEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [domainInput, setDomainInput] = useState("");
  const [adding, setAdding] = useState(false);
  const [addMessage, setAddMessage] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);

  const [removingId, setRemovingId] = useState<string | null>(null);

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

  // --- load entries ---
  useEffect(() => {
    if (!user) return;
    let cancel = false;
    (async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const data = await apiFetch<AllowlistEntry[]>("/api/allowlist");
        if (!cancel) setEntries(data);
      } catch (e) {
        console.error(e);
        if (!cancel) setLoadError("Failed to load allowlist.");
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => { cancel = true; };
  }, [user]);

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

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    setAddError(null);
    setAddMessage(null);

    const normalized = normalizeDomain(domainInput);

    if (!BARE_DOMAIN_RE.test(normalized)) {
      setAddError(`"${normalized}" is not a valid bare domain (e.g. khanacademy.org).`);
      return;
    }

    if (entries.some((e) => e.domain === normalized)) {
      setAddError("This domain is already in the allowlist.");
      return;
    }

    setAdding(true);
    try {
      const entry = await apiFetch<AllowlistEntry>("/api/allowlist", {
        method: "POST",
        body: JSON.stringify({ domain: normalized }),
      });
      setEntries((prev) => [entry, ...prev]);
      setDomainInput("");
      setAddMessage(`Added: ${entry.domain}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("409") || msg.toLowerCase().includes("already")) {
        setAddError("This domain is already in the allowlist.");
      } else {
        setAddError("Failed to add domain.");
      }
    } finally {
      setAdding(false);
    }
  }

  async function onRemove(entry: AllowlistEntry) {
    if (!window.confirm(
      `Remove "${entry.domain}" from the allowlist?\n\n` +
      `Links on this domain will fail the credibility check on the next health-check cycle and move to NOT READY.`
    )) return;

    setRemovingId(entry.id);
    try {
      await apiFetch<void>(`/api/allowlist/${entry.id}`, { method: "DELETE" });
      setEntries((prev) => prev.filter((e) => e.id !== entry.id));
    } catch (e) {
      console.error(e);
      alert("Failed to remove domain.");
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="site-header">
        <div className="site-header-inner">
          <div>
            <h1 className="page-title">Trusted Domain Allowlist</h1>
            <p className="page-subtitle">
              Only links whose domain appears here pass the credibility filter used during health checks and discovery.
            </p>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => router.push("/dashboard")} className="btn-primary">
              Back to Dashboard
            </button>
            <button onClick={onLogout} className="btn-secondary">Logout</button>
          </div>
        </div>
      </header>

      <div className="page-container">
        {/* Add domain form */}
        <div className="bg-white rounded-xl p-8 shadow-sm border mb-6">
          <h2 className="text-xl 2xl:text-2xl font-semibold mb-4">Add Trusted Domain</h2>
          <p className="text-sm text-gray-500 mb-4">
            Enter a bare domain (e.g. <code className="bg-gray-100 px-1 rounded">khanacademy.org</code>).
            Subdomains (e.g. <code className="bg-gray-100 px-1 rounded">cs.stanford.edu</code>) will also pass
            if the registrable domain is listed. Schemes, paths, and <code className="bg-gray-100 px-1 rounded">www.</code> are stripped automatically.
          </p>

          <form onSubmit={onAdd} className="flex items-start gap-3">
            <div className="flex-1">
              <input
                value={domainInput}
                onChange={(e) => { setDomainInput(e.target.value); setAddError(null); setAddMessage(null); }}
                className={`w-full rounded-lg border px-3 py-2 text-sm ${addError ? "border-red-400" : ""}`}
                placeholder="khanacademy.org"
              />
              {addError && <p className="mt-1 text-xs text-red-600 font-medium">{addError}</p>}
              {addMessage && <p className="mt-1 text-xs text-green-700 font-medium">{addMessage}</p>}
            </div>
            <button
              type="submit"
              disabled={adding || !domainInput.trim()}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60 shrink-0"
            >
              {adding ? "Adding…" : "Add domain"}
            </button>
          </form>
        </div>

        {/* Domain table */}
        <div className="bg-white rounded-xl p-8 shadow-sm border">
          <h2 className="text-xl 2xl:text-2xl font-semibold mb-4">
            Trusted Domains
            {entries.length > 0 && (
              <span className="ml-2 text-base font-normal text-gray-400">({entries.length})</span>
            )}
          </h2>

          {loading && <p className="text-sm text-gray-500">Loading…</p>}
          {loadError && <p className="text-sm text-red-600">{loadError}</p>}

          {!loading && !loadError && entries.length === 0 && (
            <p className="text-sm text-gray-500">No domains in the allowlist yet. Add one above.</p>
          )}

          {!loading && entries.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    <th className="pb-2 pr-4">Domain</th>
                    <th className="pb-2 pr-4">Added At</th>
                    <th className="pb-2 pr-4">Added By</th>
                    <th className="pb-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {entries.map((entry) => (
                    <tr key={entry.id} className="py-2">
                      <td className="py-2 pr-4 font-mono font-medium text-gray-900">{entry.domain}</td>
                      <td className="py-2 pr-4 text-gray-500">
                        {new Date(entry.added_at).toLocaleString()}
                      </td>
                      <td className="py-2 pr-4 text-gray-500">{entry.added_by}</td>
                      <td className="py-2 text-right">
                        <button
                          type="button"
                          onClick={() => onRemove(entry)}
                          disabled={removingId === entry.id}
                          className="px-2 py-1 rounded border border-red-300 bg-white text-xs text-red-600 hover:bg-red-50 disabled:opacity-60"
                        >
                          {removingId === entry.id ? "Removing…" : "Remove"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
