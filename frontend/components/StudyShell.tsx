import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/router";
import { ApiError } from "../lib/fetcher";
import { fetchStudyCatalog } from "../lib/studyCatalog";
import { selectedStudy, rememberStudy, type StudyId, studyPageUrl } from "../lib/studySelection";

export type Enrollment = { study_id: StudyId; label: string; approved: boolean; available: boolean;
  reason: string | null; revoked?: boolean; code_required?: boolean; status: string; completed_steps: number; total_steps: number; finished: boolean; consent_required: boolean };

// Browser-only selection is resolved after hydration, before pages fetch data.
export default function StudyShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [context, setContext] = useState<{ path: string; study: StudyId; enrollment?: Enrollment; error?: string } | null>(null);
  const publicPage = ["/", "/login", "/signup"].includes(router.pathname);
  useEffect(() => {
    if (publicPage || router.isReady === false) return;
    let cancelled = false;
    const study = selectedStudy();
    rememberStudy(study);
    async function load() {
      if (study === "study-1") { setContext({ path: router.asPath, study }); return; }
      try {
        const result = await fetchStudyCatalog();
        const enrollment = result.studies.find(s => s.study_id === study);
        if (!cancelled) setContext({ path: router.asPath, study, enrollment,
          error: enrollment ? undefined : "Unable to check study access. Please try again." });
      } catch (cause) {
        if (cancelled) return;
        if (cause instanceof ApiError && cause.status === 401) { router.replace("/login"); return; }
        // A temporary polling failure must not discard an active question or
        // unsent chat. Every backend operation still enforces current approval.
        setContext(previous => previous?.path === router.asPath && previous.enrollment?.available
          ? previous : { path: router.asPath, study, error: "Unable to check study access. Refresh to try again." });
      }
    }
    void load();
    const timer = study === "study-2" ? setInterval(load, 15000) : undefined;
    return () => { cancelled = true; if (timer) clearInterval(timer); };
  }, [publicPage, router.isReady, router.asPath]);

  useEffect(() => {
    const push = router.push.bind(router), replace = router.replace.bind(router);
    function scoped(args: Parameters<typeof router.push>) {
      const [url, as, options] = args;
      const destination = typeof url === "string" ? studyPageUrl(url) : {
        ...url, query: { ...(typeof url.query === "object" ? url.query : {}),
          study: typeof url.query === "object" && url.query?.study ? url.query.study : selectedStudy() },
      };
      return [destination, typeof as === "string" ? studyPageUrl(as) : as, options] as Parameters<typeof router.push>;
    }
    router.push = (...args) => push(...scoped(args));
    router.replace = (...args) => replace(...scoped(args));
    return () => { router.push = push; router.replace = replace; };
  }, [router]);

  if (publicPage) return <>{children}</>;
  if (!context || context.path !== router.asPath) return <p role="status" className="p-6">Loading your study…</p>;
  if (context.error) return <p role="alert" className="p-6 text-red-700">{context.error}</p>;
  if (context.enrollment && !context.enrollment.available) return <main className="p-6">
    <h1 className="text-xl font-semibold">Study access unavailable</h1>
    <p>{context.enrollment.reason}</p><p>Your saved progress is preserved.</p>
    {/* The code form lives on the Study 1 dashboard. */}
    <a className="mt-4 inline-block text-blue-700 underline" href={studyPageUrl("/dashboard", "study-1")}>{context.enrollment.code_required ? "Enter your access code on the dashboard" : "Return to dashboard"}</a>
  </main>;
  return <div key={context.study} className="contents">{children}</div>;
}
