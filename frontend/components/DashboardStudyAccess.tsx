import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/router";
import { apiFetch } from "../lib/fetcher";
import { fetchStudyCatalog, invalidateStudyCatalog } from "../lib/studyCatalog";
import { invalidateMeCache, type User } from "../lib/auth";
import { rememberStudy, studyApiPath, studyPageUrl, DEFAULT_ACCESS_POLICY, type StudyAccessPolicy } from "../lib/studySelection";
import type { Enrollment } from "./StudyShell";
import AdminStudySelector from "./AdminStudySelector";

export default function DashboardStudyAccess({ user }: { user: User }) {
  const router = useRouter();
  const [studies, setStudies] = useState<Enrollment[] | null>(null);
  const [policy, setPolicy] = useState<StudyAccessPolicy>(DEFAULT_ACCESS_POLICY);
  // Background refreshes must not clear an error from the participant's last action.
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const current = user.study_id === "study-2" ? "study-2" : "study-1";
  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const result = await fetchStudyCatalog();
        if (!cancelled) { setStudies(result.studies); setPolicy(result.access_policy ?? DEFAULT_ACCESS_POLICY); setLoadError(""); }
      } catch { if (!cancelled) setLoadError("Study access could not be loaded. Refresh to try again."); }
    }
    void refresh();
    const timer = setInterval(refresh, 15000);
    // Returning to the tab is an explicit "check now" (e.g. approval during an interview).
    const onFocus = () => { invalidateStudyCatalog(); void refresh(); };
    window.addEventListener("focus", onFocus);
    return () => { cancelled = true; clearInterval(timer); window.removeEventListener("focus", onFocus); };
  }, [user.id, user.is_admin]);

  async function enter(study: Enrollment) {
    if (busy || !study.available) return;
    setBusy(true); setError("");
    try {
      if (study.study_id === "study-2") await apiFetch(studyApiPath("/api/studies/start", "study-2"), { method: "POST" });
      invalidateMeCache(); invalidateStudyCatalog();
      const navigated = await router.push(studyPageUrl(study.consent_required ? "/consent" : "/dashboard", study.study_id));
      if (navigated) rememberStudy(study.study_id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to continue. Please try again."); }
    finally { setBusy(false); }
  }

  async function redeem(event: FormEvent) {
    event.preventDefault();
    if (busy || !code.trim()) return;
    setBusy(true); setError("");
    try {
      const study = await apiFetch<Enrollment>("/api/studies/access-code/redeem", { method: "POST", body: JSON.stringify({ code: code.trim() }) });
      invalidateStudyCatalog();
      setStudies(previous => previous?.map(s => s.study_id === study.study_id ? study : s) ?? previous);
      setCode(""); setBusy(false);
      if (study.available) await enter(study);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to check the access code."); setBusy(false); }
  }

  const interview = studies?.find(study => study.study_id === "study-2");
  // A revoked participant cannot use the code; only the research team can restore access.
  const needsCode = !user.is_admin && policy.requires_approval && !!interview && !interview.available && !interview.approved && !interview.revoked;
  const showSelector = user.is_admin || !policy.requires_study1_completion;
  // Without the selector, a locked Study 2 still needs to say why (e.g. a code
  // was accepted but Study 1 comes first, or access was revoked).
  const lockedNotice = !showSelector && current === "study-1" && !!interview && !interview.available && !needsCode && interview.reason;
  return <>
    {showSelector && studies && <AdminStudySelector studies={studies} current={current} busy={busy} onSelect={enter} isAdmin={user.is_admin} policy={policy} />}
    {!showSelector && current === "study-1" && interview?.available && <section aria-labelledby="interview-invitation-title" className="flex flex-col gap-4 rounded-2xl border border-blue-200 bg-blue-50 p-6 sm:flex-row sm:items-center sm:justify-between">
      <div><h2 id="interview-invitation-title" className="text-lg font-semibold text-blue-900">{policy.requires_approval ? "Your interview is available" : "Study 2 is ready"}</h2>
        <p className="mt-1 text-sm text-blue-800">{policy.requires_approval ? "Continue when your researcher asks you to begin. Your saved progress is kept." : "Continue to the next study. Your Study 1 progress is saved."}</p></div>
      <button type="button" disabled={busy} onClick={() => enter(interview)} className="rounded-xl bg-blue-600 px-6 py-3 font-semibold text-white hover:bg-blue-700 disabled:opacity-50">{policy.requires_approval ? "Continue to interview" : "Continue to Study 2"}</button>
    </section>}
    {lockedNotice && <section aria-labelledby="interview-locked-title" className="rounded-2xl border border-blue-200 bg-blue-50 p-6">
      <h2 id="interview-locked-title" className="text-lg font-semibold text-blue-900">{interview?.approved ? "Study 2 is unlocked" : "Study 2"}</h2>
      <p className="mt-1 text-sm text-blue-800">{interview?.approved ? `${lockedNotice}. Study 2 opens here once you have finished.` : lockedNotice}</p>
    </section>}
    {needsCode && <form onSubmit={redeem} aria-labelledby="access-code-title" className="flex flex-col gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-6">
      <h2 id="access-code-title" className="text-lg font-semibold text-blue-900">Have a Study 2 access code?</h2>
      <p className="text-sm text-blue-800">Your interviewer will give you a code when it is time to begin Study 2. Your saved progress is kept.</p>
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm text-blue-900">Study 2 access code <input value={code} onChange={e => setCode(e.target.value)} autoComplete="off" autoCapitalize="characters"
          maxLength={64} placeholder="XXXX-XXXX" className="ml-1 rounded-lg border px-3 py-2 font-mono uppercase" /></label>
        <button type="submit" disabled={busy || !code.trim()} className="rounded-xl bg-blue-600 px-5 py-2 font-semibold text-white hover:bg-blue-700 disabled:opacity-50">{busy ? "Checking…" : "Unlock Study 2"}</button>
      </div>
    </form>}
    {(error || loadError) && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error || loadError}</p>}
  </>;
}
