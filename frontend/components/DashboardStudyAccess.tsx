import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { apiFetch } from "../lib/fetcher";
import { invalidateMeCache, type User } from "../lib/auth";
import { rememberStudy, studyApiPath, studyPageUrl, DEFAULT_ACCESS_POLICY, type StudyAccessPolicy } from "../lib/studySelection";
import type { Enrollment } from "./StudyShell";
import AdminStudySelector from "./AdminStudySelector";

export default function DashboardStudyAccess({ user }: { user: User }) {
  const router = useRouter();
  const [studies, setStudies] = useState<Enrollment[] | null>(null);
  const [policy, setPolicy] = useState<StudyAccessPolicy>(DEFAULT_ACCESS_POLICY);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const current = user.study_id === "study-2" ? "study-2" : "study-1";
  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const result = await apiFetch<{ studies: Enrollment[]; access_policy?: StudyAccessPolicy }>("/api/studies/catalog");
        if (!cancelled) { setStudies(result.studies); setPolicy(result.access_policy ?? DEFAULT_ACCESS_POLICY); setError(""); }
      } catch { if (!cancelled) setError("Study access could not be loaded. Refresh to try again."); }
    }
    void refresh();
    const timer = setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    return () => { cancelled = true; clearInterval(timer); window.removeEventListener("focus", refresh); };
  }, [user.id, user.is_admin]);

  async function enter(study: Enrollment) {
    if (busy || !study.available) return;
    setBusy(true); setError("");
    try {
      if (study.study_id === "study-2") await apiFetch(studyApiPath("/api/studies/start", "study-2"), { method: "POST" });
      invalidateMeCache();
      const navigated = await router.push(studyPageUrl(study.consent_required ? "/consent" : "/dashboard", study.study_id));
      if (navigated) rememberStudy(study.study_id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to continue. Please try again."); }
    finally { setBusy(false); }
  }

  const interview = studies?.find(study => study.study_id === "study-2");
  const showSelector = user.is_admin || !policy.requires_study1_completion;
  return <>
    {showSelector && studies && <AdminStudySelector studies={studies} current={current} busy={busy} onSelect={enter} isAdmin={user.is_admin} policy={policy} />}
    {!showSelector && current === "study-1" && interview?.available && <section aria-labelledby="interview-invitation-title" className="flex flex-col gap-4 rounded-2xl border border-blue-200 bg-blue-50 p-6 sm:flex-row sm:items-center sm:justify-between">
      <div><h2 id="interview-invitation-title" className="text-lg font-semibold text-blue-900">{policy.requires_approval ? "Your interview is available" : "Study 2 is ready"}</h2>
        <p className="mt-1 text-sm text-blue-800">{policy.requires_approval ? "Continue when your researcher asks you to begin. Your saved progress is kept." : "Continue to the next study. Your Study 1 progress is saved."}</p></div>
      <button type="button" disabled={busy} onClick={() => enter(interview)} className="rounded-xl bg-blue-600 px-6 py-3 font-semibold text-white hover:bg-blue-700 disabled:opacity-50">{policy.requires_approval ? "Continue to interview" : "Continue to Study 2"}</button>
    </section>}
    {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</p>}
  </>;
}
