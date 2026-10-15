import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/router";
import { apiFetch } from "../lib/fetcher";
import { selectedStudy, type StudyId, studyPageUrl, studyApiPath } from "../lib/studySelection";
import { invalidateMeCache } from "../lib/auth";

export type Enrollment = { study_id: StudyId; label: string; approved: boolean; available: boolean;
  reason: string | null; status: string; completed_steps: number; total_steps: number; finished: boolean; consent_required: boolean };

export default function StudyShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [studies, setStudies] = useState<Enrollment[] | null>(null);
  const [error, setError] = useState("");
  const [switching, setSwitching] = useState(false);
  const selected = selectedStudy();
  const publicPage = ["/", "/login", "/signup"].includes(router.pathname);
  useEffect(() => {
    if (publicPage) { setStudies(null); return; }
    let cancelled = false;
    async function load() {
      try {
        const result = await apiFetch<{ studies: Enrollment[] }>("/api/studies/catalog");
        if (!cancelled) { setStudies(result.studies); setError(""); }
      } catch { if (!cancelled && selected === "study-2") setError("Unable to check study access. Refresh to try again."); }
    }
    load(); const timer = setInterval(load, 15000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [publicPage, router.asPath, selected]);
  // Preserve the study in every ordinary client-side navigation. URL + tab-local
  // selection avoid a global cookie that would switch another browser tab.
  useEffect(() => {
    const push = router.push.bind(router), replace = router.replace.bind(router);
    function scoped(args: Parameters<typeof router.push>) {
      const [url, as, options] = args;
      return [typeof url === "string" ? studyPageUrl(url) : { ...url, query: { ...(typeof url.query === "object" ? url.query : {}), study: selectedStudy() } }, as, options] as Parameters<typeof router.push>;
    }
    router.push = (...args) => push(...scoped(args));
    router.replace = (...args) => replace(...scoped(args));
    return () => { router.push = push; router.replace = replace; };
  }, [router]);
  if (publicPage) return <>{children}</>;
  const current = studies?.find(s => s.study_id === selected);
  const activeTask = current?.available && (router.pathname.startsWith("/quiz/") || router.pathname === "/survey");
  async function changeStudy(study: Enrollment) {
    if (switching || !study.available) return;
    setSwitching(true); setError("");
    try {
      if (study.study_id === "study-2") await apiFetch(studyApiPath("/api/studies/start", "study-2"), { method: "POST" });
      sessionStorage.setItem("mep.selectedStudy", study.study_id); invalidateMeCache();
      window.location.assign(studyPageUrl(study.consent_required ? "/consent" : "/dashboard", study.study_id));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to open this study."); setSwitching(false); }
  }
  return <>
    {studies && <nav aria-label="Choose study" className="border-b bg-white px-4 py-3 flex flex-wrap items-center gap-3">
      {studies.map(study => <button key={study.study_id} type="button" aria-pressed={study.study_id === selected}
        disabled={switching || activeTask || !study.available} onClick={() => changeStudy(study)}
        className="rounded-lg border px-4 py-2 text-sm disabled:opacity-60 aria-pressed:bg-blue-50 aria-pressed:border-blue-600">
        <strong>{study.label}</strong> · {study.finished ? "Completed" : !study.available ? study.reason : study.total_steps ? `${study.completed_steps} of ${study.total_steps} steps` : "Ready to start"}
      </button>)}
      {activeTask && <span className="text-xs text-gray-600">Return to the dashboard before switching studies.</span>}
    </nav>}
    {error && <p role="alert" className="p-4 text-red-700">{error}</p>}
    {selected === "study-2" && !studies ? <p role="status" className="p-6">Checking Study 2 access…</p> :
      selected === "study-2" && current && !current.available ? <main className="p-6"><h1 className="text-xl font-semibold">Study 2 is locked</h1><p>{current.reason}</p><p>Your saved progress is preserved.</p></main> : children}
  </>;
}
