import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../lib/fetcher";

type AccessCode = { code: string | null; version: number; rotated_at: string | null; rotated_by: string | null };

export default function StudyAccessCodeAdmin() {
  const [current, setCurrent] = useState<AccessCode | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const load = useCallback((signal?: AbortSignal) => {
    setError(""); setLoadFailed(false);
    apiFetch<AccessCode>("/api/studies/access-code", { signal })
      .then(result => { if (!signal?.aborted) setCurrent(result); })
      .catch(cause => {
        if (signal?.aborted) return;
        setError(cause instanceof Error ? cause.message : "Unable to load the access code.");
        setLoadFailed(true);
      });
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);
  async function rotate() {
    setBusy(true); setError("");
    try { setCurrent(await apiFetch<AccessCode>("/api/studies/access-code/rotate", { method: "POST" })); setConfirming(false); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to rotate the access code."); }
    finally { setBusy(false); }
  }
  const hasCode = !!current?.code;
  return <section aria-label="Study 2 access code" className="rounded-xl border bg-white p-4 space-y-3">
    <h2 className="text-lg font-semibold">Study 2 access code</h2>
    <p className="text-sm text-gray-600">Give this code to participants during the interview. Any number of participants can use it until you rotate it. Rotating does not lock out participants who already entered an earlier code.</p>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {/* Without the current code the panel cannot tell generating from rotating, so offer a reload. */}
    {loadFailed && !current && <button type="button" onClick={() => load()} className="rounded border px-3 py-2">Try again</button>}
    {current && (hasCode
      ? <div><p className="font-mono text-3xl tracking-widest" aria-label="Current access code">{current.code}</p>
          <p className="text-xs text-gray-600">Version {current.version}{current.rotated_at ? ` · generated ${new Date(current.rotated_at).toLocaleString()}` : ""}</p></div>
      : <p>No access code yet. Participants cannot unlock Study 2 until you generate one.</p>)}
    {!hasCode ? <button type="button" disabled={busy || !current} onClick={rotate} className="rounded border px-3 py-2">Generate access code</button>
      : confirming ? <div className="flex flex-wrap items-center gap-2"><span className="text-sm">The current code will stop working for new participants.</span>
          <button type="button" disabled={busy} onClick={rotate} className="rounded border border-red-600 px-3 py-2 text-red-700">Confirm rotation</button>
          <button type="button" disabled={busy} onClick={() => setConfirming(false)} className="rounded border px-3 py-2">Cancel</button></div>
      : <button type="button" onClick={() => setConfirming(true)} className="rounded border px-3 py-2">Rotate access code</button>}
  </section>;
}
